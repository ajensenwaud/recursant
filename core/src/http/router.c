#define _POSIX_C_SOURCE 200809L
#include "recursant/runtime.h"
#include "recursant/gateway_context.h"
#include "recursant/classifier.h"
#include "recursant/provider_adapter.h"
#include <microhttpd.h>
#include <curl/curl.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include <errno.h>

#define QUEUE_SIZE 65536
static volatile sig_atomic_t stopping;
typedef struct {
    rc_runtime *runtime;
    char *body; size_t used; bool replied; unsigned rejection;
    pthread_t worker; bool started;
    pthread_mutex_t lock; pthread_cond_t changed;
    bool finished; /* Gateway ticket finalized exactly once. */
    unsigned char queue[QUEUE_SIZE]; size_t head,count;
    bool done,cancel,headers,failed,sse;
    long status; char *payload; rc_endpoint endpoint; size_t provider;
    int downstream_fd; /* Owned duplicate; valid until worker has joined. */
    struct timespec deadline;
    rc_gateway_ticket ticket;
    char observation[65536];size_t observed;bool observation_overflow;
    rc_response_observer *stream_observation;
    bool strict_stream; /* resolved provider's adapter lacks OpenRouter accounting */
    uint64_t retry_after_ms; /* upstream Retry-After (seconds form), capped */
    char error[4096];size_t error_len;bool error_overflow; /* upstream error body; never logged */
} request;
static void stop_server(int sig){(void)sig;stopping=1;}
static enum MHD_Result reply(struct MHD_Connection *c,unsigned status,const char *text,const char *type){
    struct MHD_Response *r=MHD_create_response_from_buffer(strlen(text),(void*)text,MHD_RESPMEM_MUST_COPY);
    if(!r)return MHD_NO;
    MHD_add_response_header(r,"Content-Type",type);
    enum MHD_Result result=MHD_queue_response(c,status,r);MHD_destroy_response(r);return result;
}
static enum MHD_Result error_reply(struct MHD_Connection *c,unsigned code){return reply(c,code,"{\"error\":{\"message\":\"request failed\"}}","application/json");}
static int progress(void *ctx,curl_off_t a,curl_off_t b,curl_off_t d,curl_off_t e){
    (void)a;(void)b;(void)d;(void)e;request *r=ctx;
    /* While MHD waits for upstream data, detect unambiguous transport errors.
     * Receive EOF is only FIN: a valid HTTP client may SHUT_WR and keep reading.
     * An idle graceful close is indistinguishable and remains deadline-bounded.
     * Peek only: never consume pipelined bytes or inject SSE heartbeat bytes. */
    char byte;ssize_t n=recv(r->downstream_fd,&byte,1,MSG_PEEK|MSG_DONTWAIT);
    bool disconnected=n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR;
    pthread_mutex_lock(&r->lock);
    if(disconnected){r->cancel=true;pthread_cond_broadcast(&r->changed);}
    bool cancel=r->cancel;pthread_mutex_unlock(&r->lock);return cancel;
}
static size_t header(char *data,size_t size,size_t nmemb,void *ctx){
    request *r=ctx;size_t n=size*nmemb;
    pthread_mutex_lock(&r->lock);
    if(n>5&&!memcmp(data,"HTTP/",5)){
        char *space=memchr(data,' ',n);r->status=space?strtol(space+1,NULL,10):0;
    }
    if(n>12&&n<64&&!strncasecmp(data,"Retry-After:",12)){
        char tmp[64];memcpy(tmp,data+12,n-12);tmp[n-12]=0;char *end;long seconds=strtol(tmp,&end,10);
        while(*end==' '||*end=='\r'||*end=='\n')end++;
        if(!*end&&seconds>0)r->retry_after_ms=seconds>60?60000:(uint64_t)seconds*1000;
    }
    if(n>=19&&!strncasecmp(data,"Content-Type:",13) && n<256){char tmp[256];memcpy(tmp,data,n);tmp[n]=0;r->sse=strstr(tmp,"text/event-stream")!=NULL;}
    if(n==2&&data[0]=='\r'&&data[1]=='\n'&&r->status>=200){r->headers=true;pthread_cond_broadcast(&r->changed);}
    pthread_mutex_unlock(&r->lock);return n;
}
static size_t receive(char *data,size_t size,size_t nmemb,void *ctx){
    request *r=ctx;size_t n=size*nmemb,offset=0;
    pthread_mutex_lock(&r->lock);
    if(r->status<200||r->status>=300){
        /* Keep a bounded error body for classification; a larger one aborts. */
        size_t room=sizeof r->error-1-r->error_len;
        if(n>room){r->error_overflow=true;pthread_mutex_unlock(&r->lock);return 0;}
        memcpy(r->error+r->error_len,data,n);r->error_len+=n;r->error[r->error_len]=0;
        pthread_mutex_unlock(&r->lock);return n;
    }
    if(r->ticket.begun&&r->ticket.scope>=0){
        if(r->sse){
            if(!r->stream_observation&&!r->observation_overflow){
                r->stream_observation=calloc(1,sizeof *r->stream_observation);
                if(!r->stream_observation)r->observation_overflow=true;
                else {r->stream_observation->strict_openai=r->strict_stream;r->stream_observation->drop_reasoning=rc_gateway_drop_reasoning(r->runtime);}
            }
            if(r->stream_observation)rc_response_observer_feed(r->stream_observation,data,n);
        }
        else if(n>sizeof r->observation-r->observed)r->observation_overflow=true;
        else if(!r->observation_overflow){memcpy(r->observation+r->observed,data,n);r->observed+=n;}
    }
    while(offset<n&&!r->cancel){
        while(r->count==QUEUE_SIZE&&!r->cancel)if(pthread_cond_timedwait(&r->changed,&r->lock,&r->deadline)!=0)r->cancel=true;
        if(r->cancel)break;
        size_t tail=(r->head+r->count)%QUEUE_SIZE,take=QUEUE_SIZE-tail;
        if(take>QUEUE_SIZE-r->count)take=QUEUE_SIZE-r->count;
        if(take>n-offset)take=n-offset;
        memcpy(r->queue+tail,data+offset,take);r->count+=take;offset+=take;pthread_cond_broadcast(&r->changed);
    }
    pthread_mutex_unlock(&r->lock);return offset;
}
static void *upstream(void *ctx){
    request *r=ctx;rc_runtime *rt=r->runtime;
    /* Dispatch identity is the resolved provider, never the trust class. */
    const char *base=rt->config.providers[r->provider].url;
    const char *key=rt->provider_keys[r->provider];
    size_t len=strlen(base);while(len&&base[len-1]=='/')len--;
    char *url=malloc(len+32),*auth=NULL;CURL *curl=curl_easy_init();struct curl_slist *hs=NULL;CURLcode result=CURLE_FAILED_INIT;
    if(url&&curl){snprintf(url,len+32,"%.*s/chat/completions",(int)len,base);
        hs=curl_slist_append(hs,"Content-Type: application/json");hs=curl_slist_append(hs,"Expect:");
        if(key){auth=malloc(strlen(key)+24);if(!auth)goto end;snprintf(auth,strlen(key)+24,"Authorization: Bearer %s",key);hs=curl_slist_append(hs,auth);}
        curl_easy_setopt(curl,CURLOPT_URL,url);curl_easy_setopt(curl,CURLOPT_POSTFIELDS,r->payload);
        curl_easy_setopt(curl,CURLOPT_HTTPHEADER,hs);curl_easy_setopt(curl,CURLOPT_WRITEFUNCTION,receive);curl_easy_setopt(curl,CURLOPT_WRITEDATA,r);
        curl_easy_setopt(curl,CURLOPT_HEADERFUNCTION,header);curl_easy_setopt(curl,CURLOPT_HEADERDATA,r);
        curl_easy_setopt(curl,CURLOPT_FOLLOWLOCATION,0L);curl_easy_setopt(curl,CURLOPT_SSL_VERIFYPEER,1L);curl_easy_setopt(curl,CURLOPT_SSL_VERIFYHOST,2L);
        curl_easy_setopt(curl,CURLOPT_PROTOCOLS_STR,"http,https");curl_easy_setopt(curl,CURLOPT_PROXY,"");
        curl_easy_setopt(curl,CURLOPT_TIMEOUT,(long)rt->request_timeout_seconds);curl_easy_setopt(curl,CURLOPT_CONNECTTIMEOUT,(long)rt->request_timeout_seconds);
        curl_easy_setopt(curl,CURLOPT_NOSIGNAL,1L);curl_easy_setopt(curl,CURLOPT_NOPROGRESS,0L);curl_easy_setopt(curl,CURLOPT_XFERINFOFUNCTION,progress);curl_easy_setopt(curl,CURLOPT_XFERINFODATA,r);
        result=curl_easy_perform(curl);
        long upstream_status=0;
        curl_easy_getinfo(curl,CURLINFO_RESPONSE_CODE,&upstream_status);
        if(result!=CURLE_OK || upstream_status<200 || upstream_status>=300)
            fprintf(stderr,"upstream_http=%ld curl_code=%d\n",upstream_status,(int)result);
    }
end:
    curl_easy_cleanup(curl);curl_slist_free_all(hs);free(url);free(auth);
    pthread_mutex_lock(&r->lock);r->failed=result!=CURLE_OK;r->done=true;pthread_cond_broadcast(&r->changed);pthread_mutex_unlock(&r->lock);return NULL;
}
static ssize_t read_response(void *ctx,uint64_t pos,char *buf,size_t max){
    (void)pos;request *r=ctx;pthread_mutex_lock(&r->lock);
    while(!r->count&&!r->done&&!r->cancel)if(pthread_cond_timedwait(&r->changed,&r->lock,&r->deadline)!=0)r->cancel=true;
    if(!r->count){ssize_t n=(r->failed||r->cancel)?MHD_CONTENT_READER_END_WITH_ERROR:MHD_CONTENT_READER_END_OF_STREAM;pthread_mutex_unlock(&r->lock);
        /* The response is fully delivered to the transport (or terminally
         * failed): the scoped exchange is over. Finalize here so the next
         * scoped request observes the cleared inflight fence and the true
         * pin/ownership status instead of a stale 409 during teardown. */
        rc_gateway_finish(r->runtime,&r->ticket,!r->failed&&!r->cancel,r->sse,r->observation_overflow?NULL:r->observation,r->observed,r->stream_observation);
        return n;}
    size_t n=QUEUE_SIZE-r->head;if(n>r->count)n=r->count;if(n>max)n=max;
    memcpy(buf,r->queue+r->head,n);r->head=(r->head+n)%QUEUE_SIZE;r->count-=n;pthread_cond_broadcast(&r->changed);pthread_mutex_unlock(&r->lock);return (ssize_t)n;
}
static void completed(void *ctx,struct MHD_Connection *c,void **con_cls,enum MHD_RequestTerminationCode code){
    (void)ctx;(void)c;request *r=*con_cls;if(!r)return;
    pthread_mutex_lock(&r->lock);bool complete=code==MHD_REQUEST_TERMINATED_COMPLETED_OK&&r->started&&r->done&&!r->failed&&!r->cancel&&r->status>=200&&r->status<300&&r->count==0;pthread_mutex_unlock(&r->lock);
    pthread_mutex_lock(&r->lock);r->cancel=true;pthread_cond_broadcast(&r->changed);pthread_mutex_unlock(&r->lock);
    if(r->started)pthread_join(r->worker,NULL);
    rc_gateway_finish(r->runtime,&r->ticket,complete,r->sse,r->observation_overflow?NULL:r->observation,r->observed,r->stream_observation);
    rc_response_observer_release(r->stream_observation);free(r->stream_observation);
    if(r->downstream_fd>=0)close(r->downstream_fd);
    pthread_mutex_destroy(&r->lock);pthread_cond_destroy(&r->changed);free(r->body);free(r->payload);free(r);*con_cls=NULL;
}
static bool route(rc_runtime *rt,const char *model,rc_endpoint *endpoint,const char **physical){
    if(rc_gateway_auto(rt,model,endpoint,physical))return true;
    for(size_t i=0;i<rt->config.alias_count;i++){rc_alias *a=&rt->config.aliases[i];if(!strcmp(model,a->from)||!strcmp(model,a->model)){*endpoint=a->endpoint;*physical=a->model;return true;}}
    if(rt->config.private_model&&!strcmp(model,rt->config.private_model)){*endpoint=RC_ENDPOINT_PRIVATE;*physical=rt->config.private_model;return true;}
    if(rt->config.public_model&&!strcmp(model,rt->config.public_model)){*endpoint=RC_ENDPOINT_PUBLIC;*physical=rt->config.public_model;return true;}return false;
}
static enum MHD_Result collect_header(void *ctx,enum MHD_ValueKind kind,const char *key,const char *value){
    (void)kind;rc_gateway_header(ctx,key,value);return MHD_YES;
}
static enum MHD_Result handle(void *ctx,struct MHD_Connection *c,const char *url,const char *method,const char *version,const char *upload,size_t *upload_size,void **con_cls){
    (void)version;rc_runtime *rt=ctx;request *r=*con_cls;
    if(!r){r=calloc(1,sizeof *r);if(!r)return MHD_NO;r->downstream_fd=-1;r->runtime=rt;pthread_mutex_init(&r->lock,NULL);pthread_cond_init(&r->changed,NULL);clock_gettime(CLOCK_REALTIME,&r->deadline);r->deadline.tv_sec+=rt->request_timeout_seconds;*con_cls=r;return MHD_YES;}
    if(r->replied)return MHD_YES;
    struct timespec now;clock_gettime(CLOCK_REALTIME,&now);
    if(now.tv_sec>r->deadline.tv_sec || (now.tv_sec==r->deadline.tv_sec && now.tv_nsec>=r->deadline.tv_nsec))return MHD_NO;
    const char *auth=MHD_lookup_connection_value(c,MHD_HEADER_KIND,"Authorization");
    bool health=!strcmp(url,"/healthz")&&!strcmp(method,"GET");
    bool context_path=rt->gateway&&(!strcmp(url,"/v1/context")||!strcmp(url,"/v1/context/open")||!strcmp(url,"/v1/context/close")||!strcmp(url,"/v1/context/hint"));
    const char *expected=context_path?rt->source_key:rt->auth_key;
    if(!health && (!auth||!expected||strncmp(auth,"Bearer ",7)||strcmp(auth+7,expected)))r->rejection=401;
    if(*upload_size){
        if(*upload_size>rt->max_body_bytes-r->used)r->rejection=413;
        if(!r->rejection){char *b=realloc(r->body,r->used+*upload_size+1);if(!b)return MHD_NO;r->body=b;memcpy(b+r->used,upload,*upload_size);r->used+=*upload_size;b[r->used]=0;}
        *upload_size=0;return MHD_YES;
    }
    if(r->rejection){r->replied=true;return error_reply(c,r->rejection);}
    if(health){r->replied=true;return reply(c,200,"{\"status\":\"ok\"}","application/json");}
    if(!strcmp(url,"/v1/models")&&!strcmp(method,"GET")){
        r->replied=true;
        json_t *root=json_pack("{s:s,s:[]}","object","list","data");
        if(!root)return error_reply(c,500);
        json_t *list=json_object_get(root,"data");
        for(size_t i=0;i<rt->config.alias_count;i++){
            json_t *entry=json_pack("{s:s,s:s}","id",rt->config.aliases[i].from,"object","model");
            /* append_new consumes entry on both success and failure. */
            if(!entry || json_array_append_new(list,entry)!=0){json_decref(root);return error_reply(c,500);}
        }
        char *s=json_dumps(root,JSON_COMPACT);json_decref(root);
        if(!s)return error_reply(c,500);
        enum MHD_Result result=reply(c,200,s,"application/json");free(s);return result;
    }
    if(context_path&&!strcmp(method,"POST")){
        r->replied=true;json_error_t error;json_t *body=json_loadb(r->body?r->body:"",r->used,JSON_REJECT_DUPLICATES,&error),*out=NULL;
        unsigned status=rc_gateway_event(rt,url,body,&out);json_decref(body);
        char *text=out?json_dumps(out,JSON_COMPACT):NULL;json_decref(out);
        enum MHD_Result result=text?reply(c,status,text,"application/json"):error_reply(c,status);free(text);return result;
    }
    if(strcmp(url,"/v1/chat/completions")||strcmp(method,"POST")){r->replied=true;return error_reply(c,404);}
    r->replied=true;json_error_t je;json_t *body=json_loadb(r->body?r->body:"",r->used,JSON_REJECT_DUPLICATES,&je);
    json_t *m=json_object_get(body,"model");const char *model=json_string_value(m),*physical=NULL;
    if(!json_is_object(body)||!model||strlen(model)!=json_string_length(m)||!route(rt,model,&r->endpoint,&physical)){json_decref(body);return error_reply(c,400);}
    rc_endpoint ignored;const char *ignored_model;bool automatic=rc_gateway_auto(rt,model,&ignored,&ignored_model);
    json_t *rewritten=json_string(physical);
    if(!rewritten || json_object_set_new(body,"model",rewritten)!=0){json_decref(body);return error_reply(c,500);}
    /* M2 hard gate: final provider object, before serialization and any network. */
    rc_gateway_headers headers_in={0};
    if(rt->gateway)MHD_get_connection_values(c,MHD_HEADER_KIND,collect_header,&headers_in);
    struct timespec routing_start,routing_end;clock_gettime(CLOCK_MONOTONIC,&routing_start);
    unsigned denial=rc_gateway_prepare(rt,body,automatic,&headers_in,&r->endpoint,&r->ticket);
    clock_gettime(CLOCK_MONOTONIC,&routing_end);
    long long routing_us=(long long)(routing_end.tv_sec-routing_start.tv_sec)*1000000+(routing_end.tv_nsec-routing_start.tv_nsec)/1000;
    if(denial){json_decref(body);return error_reply(c,denial);}
    /* Final (trust, model) after M2/context selects exactly one provider whose
     * trust equals the final M2 trust class; anything else fails closed. */
    if(r->endpoint!=RC_ENDPOINT_PRIVATE&&r->endpoint!=RC_ENDPOINT_PUBLIC){json_decref(body);return error_reply(c,403);}
    const union MHD_ConnectionInfo *info=MHD_get_connection_info(c,MHD_CONNECTION_INFO_CONNECTION_FD);
    if(!info || (r->downstream_fd=dup(info->connect_fd))<0){json_decref(body);return error_reply(c,503);}
    rc_gateway_shadow(rt,body,automatic,&headers_in,r->endpoint,&r->ticket);
    /* context.health: a failure that reached no client byte (error status or
     * no response headers) may be retried on a failover target. */
    long status=0;bool sse=false;
    for(unsigned attempt=0;;attempt++){
        r->provider=rc_runtime_dispatch_provider(rt,r->endpoint,json_string_value(json_object_get(body,"model")));
        if(r->provider==RC_PROVIDER_NONE){json_decref(body);return error_reply(c,403);}
        /* The stream observer accepts only the dialect of the adapter that will
         * produce it; unknown adapters get the strict OpenAI shape. */
        const rc_provider_adapter *adapter=rc_provider_adapter_find(rt->config.providers[r->provider].adapter);
        r->strict_stream=!adapter||!adapter->accepts_openrouter_accounting;
        free(r->payload);r->payload=json_dumps(body,JSON_COMPACT);if(!r->payload){json_decref(body);return error_reply(c,500);}
        if(pthread_create(&r->worker,NULL,upstream,r)){json_decref(body);return error_reply(c,503);}
        r->started=true;
        pthread_mutex_lock(&r->lock);while(!r->headers&&!r->done&&!r->cancel)if(pthread_cond_timedwait(&r->changed,&r->lock,&r->deadline)!=0)r->cancel=true;
        /* A 400 may report a context-window overflow: read its (bounded) body. */
        if(!r->cancel&&r->headers&&r->status==400)while(!r->done&&!r->cancel)if(pthread_cond_timedwait(&r->changed,&r->lock,&r->deadline)!=0)r->cancel=true;
        status=r->status;bool cancel=r->cancel,headers=r->headers;sse=r->sse;uint64_t retry_after=r->retry_after_ms;
        bool overflow=headers&&status==400&&!r->error_overflow&&rc_provider_context_overflow(r->error,r->error_len);
        pthread_mutex_unlock(&r->lock);
        if(!cancel&&headers&&status>=200&&status<300)break;
        /* A cancelled exchange (client gone, deadline) says nothing about the
         * destination and is never retried. */
        if(cancel){json_decref(body);return error_reply(c,502);}
        /* A context overflow is the request's size, not the destination's health. */
        if(!overflow)rc_gateway_outcome(rt,r->endpoint,json_string_value(json_object_get(body,"model")),headers?status:0,retry_after);
        bool retryable=overflow||!headers||status==401||status==404||status==408||status==429||status>=500;
        if(!retryable||attempt>=rc_gateway_max_retries(rt)||!rc_gateway_failover(rt,body,automatic,&headers_in,&r->endpoint,&r->ticket,headers?status:0,overflow)){json_decref(body);return error_reply(c,502);}
        pthread_join(r->worker,NULL);r->started=false;
        pthread_mutex_lock(&r->lock);r->status=0;r->headers=r->done=r->failed=r->sse=false;r->retry_after_ms=0;r->head=r->count=0;r->error_len=0;r->error_overflow=false;pthread_mutex_unlock(&r->lock);
    }
    rc_gateway_outcome(rt,r->endpoint,json_string_value(json_object_get(body,"model")),status,0);
    const char *used=json_string_value(json_object_get(body,"model"));char model_used[129];snprintf(model_used,sizeof model_used,"%s",used?used:"");
    json_decref(body);
    struct MHD_Response *response=MHD_create_response_from_callback(MHD_SIZE_UNKNOWN,16384,read_response,r,NULL);if(!response)return MHD_NO;
    MHD_add_response_header(response,"Content-Type",sse?"text/event-stream":"application/json");
    if(rc_gateway_decision_headers(rt)){
        /* Model names and decision labels only: no content. */
        char number[32];
        MHD_add_response_header(response,"X-Recursant-Model",model_used);
        if(r->ticket.reason)MHD_add_response_header(response,"X-Recursant-Decision",r->ticket.reason);
        if(r->ticket.chosen[0])MHD_add_response_header(response,"X-Recursant-Chosen",r->ticket.chosen);
        if(r->ticket.decision[0])MHD_add_response_header(response,"X-Recursant-Decision-Id",r->ticket.decision);
        if(r->ticket.costed){snprintf(number,sizeof number,"%.6f",r->ticket.cost);MHD_add_response_header(response,"X-Recursant-Cost-USD",number);}
        snprintf(number,sizeof number,"%lld",routing_us>0?routing_us:0);MHD_add_response_header(response,"X-Recursant-Routing-Us",number);
    }
    enum MHD_Result result=MHD_queue_response(c,(unsigned)status,response);MHD_destroy_response(response);return result;
}
int rc_router_serve(rc_runtime *rt){
    if(!rc_gateway_start(rt))return 1;
    struct sockaddr_in bind_addr={.sin_family=AF_INET,.sin_port=htons((uint16_t)rt->config.listen_port)};
    if(inet_pton(AF_INET,rt->config.listen_host,&bind_addr.sin_addr)!=1)return 1;
    signal(SIGTERM,stop_server);signal(SIGINT,stop_server);signal(SIGPIPE,SIG_IGN);
    struct MHD_Daemon *daemon=MHD_start_daemon(MHD_USE_INTERNAL_POLLING_THREAD|MHD_USE_THREAD_PER_CONNECTION, (uint16_t)rt->config.listen_port,NULL,NULL,handle,rt,
        MHD_OPTION_SOCK_ADDR,&bind_addr,MHD_OPTION_CONNECTION_LIMIT,rt->max_connections,
        MHD_OPTION_CONNECTION_TIMEOUT,rt->request_timeout_seconds,MHD_OPTION_CONNECTION_MEMORY_LIMIT,(size_t)32768,
        MHD_OPTION_NOTIFY_COMPLETED,completed,NULL,MHD_OPTION_END);
    if(!daemon)return 1;
    while(!stopping){rc_gateway_poll(rt);struct timespec t={0,100000000};nanosleep(&t,NULL);}MHD_stop_daemon(daemon);return 0;
}

int main(int argc,char **argv) {
    if((argc!=3 && argc!=4) || (strcmp(argv[1],"serve") && strcmp(argv[1],"validate")) ||
       (argc==4 && strcmp(argv[3],"--test-mode"))) {
        fputs("usage: recursant {serve|validate} CONFIG [--test-mode]\n",stderr);
        return 2;
    }
    if(curl_global_init(CURL_GLOBAL_DEFAULT)!=CURLE_OK)return 1;
    rc_runtime runtime;char error[128];
    rc_dispatch_gate=rc_compliance_gate;
    if(!rc_runtime_load(argv[2],argc==4,&runtime,error,sizeof error)) {
        fprintf(stderr,"%s\n",error);curl_global_cleanup();return 1;
    }
    int result=0;
    if(!rc_compliance_init(&runtime)) {
        fputs("invalid compliance policy\n",stderr);
        rc_runtime_free(&runtime);curl_global_cleanup();return 1;
    }
    if(!strcmp(argv[1],"serve"))result=rc_router_serve(&runtime);
    else puts("configuration valid");
    rc_runtime_free(&runtime);curl_global_cleanup();return result;
}
