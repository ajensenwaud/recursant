#define _POSIX_C_SOURCE 200809L
#include "recursant/runtime.h"
#include "recursant/classifier.h"
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
    unsigned char queue[QUEUE_SIZE]; size_t head,count;
    bool done,cancel,headers,failed,sse;
    long status; char *payload; rc_endpoint endpoint;
    int downstream_fd; /* Owned duplicate; valid until worker has joined. */
    struct timespec deadline;
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
    if(n>=19&&!strncasecmp(data,"Content-Type:",13) && n<256){char tmp[256];memcpy(tmp,data,n);tmp[n]=0;r->sse=strstr(tmp,"text/event-stream")!=NULL;}
    if(n==2&&data[0]=='\r'&&data[1]=='\n'&&r->status>=200){r->headers=true;pthread_cond_broadcast(&r->changed);}
    pthread_mutex_unlock(&r->lock);return n;
}
static size_t receive(char *data,size_t size,size_t nmemb,void *ctx){
    request *r=ctx;size_t n=size*nmemb,offset=0;
    pthread_mutex_lock(&r->lock);
    if(r->status<200||r->status>=300){pthread_mutex_unlock(&r->lock);return 0;}
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
    const char *base=r->endpoint==RC_ENDPOINT_PUBLIC?rt->config.public_url:rt->config.private_url;
    const char *key=r->endpoint==RC_ENDPOINT_PUBLIC?rt->public_key:rt->private_key;
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
    if(!r->count){ssize_t n=(r->failed||r->cancel)?MHD_CONTENT_READER_END_WITH_ERROR:MHD_CONTENT_READER_END_OF_STREAM;pthread_mutex_unlock(&r->lock);return n;}
    size_t n=QUEUE_SIZE-r->head;if(n>r->count)n=r->count;if(n>max)n=max;
    memcpy(buf,r->queue+r->head,n);r->head=(r->head+n)%QUEUE_SIZE;r->count-=n;pthread_cond_broadcast(&r->changed);pthread_mutex_unlock(&r->lock);return (ssize_t)n;
}
static void completed(void *ctx,struct MHD_Connection *c,void **con_cls,enum MHD_RequestTerminationCode code){
    (void)ctx;(void)c;(void)code;request *r=*con_cls;if(!r)return;
    pthread_mutex_lock(&r->lock);r->cancel=true;pthread_cond_broadcast(&r->changed);pthread_mutex_unlock(&r->lock);
    if(r->started)pthread_join(r->worker,NULL);
    if(r->downstream_fd>=0)close(r->downstream_fd);
    pthread_mutex_destroy(&r->lock);pthread_cond_destroy(&r->changed);free(r->body);free(r->payload);free(r);*con_cls=NULL;
}
static bool route(rc_runtime *rt,const char *model,rc_endpoint *endpoint,const char **physical){
    for(size_t i=0;i<rt->config.alias_count;i++){rc_alias *a=&rt->config.aliases[i];if(!strcmp(model,a->from)||!strcmp(model,a->model)){*endpoint=a->endpoint;*physical=a->model;return true;}}
    if(!strcmp(model,rt->config.private_model)){*endpoint=RC_ENDPOINT_PRIVATE;*physical=rt->config.private_model;return true;}
    if(rt->config.public_model&&!strcmp(model,rt->config.public_model)){*endpoint=RC_ENDPOINT_PUBLIC;*physical=rt->config.public_model;return true;}return false;
}
static enum MHD_Result handle(void *ctx,struct MHD_Connection *c,const char *url,const char *method,const char *version,const char *upload,size_t *upload_size,void **con_cls){
    (void)version;rc_runtime *rt=ctx;request *r=*con_cls;
    if(!r){r=calloc(1,sizeof *r);if(!r)return MHD_NO;r->downstream_fd=-1;r->runtime=rt;pthread_mutex_init(&r->lock,NULL);pthread_cond_init(&r->changed,NULL);clock_gettime(CLOCK_REALTIME,&r->deadline);r->deadline.tv_sec+=rt->request_timeout_seconds;*con_cls=r;return MHD_YES;}
    if(r->replied)return MHD_YES;
    struct timespec now;clock_gettime(CLOCK_REALTIME,&now);
    if(now.tv_sec>r->deadline.tv_sec || (now.tv_sec==r->deadline.tv_sec && now.tv_nsec>=r->deadline.tv_nsec))return MHD_NO;
    const char *auth=MHD_lookup_connection_value(c,MHD_HEADER_KIND,"Authorization");
    bool health=!strcmp(url,"/healthz")&&!strcmp(method,"GET");
    if(!health && (!auth||strncmp(auth,"Bearer ",7)||strcmp(auth+7,rt->auth_key)))r->rejection=401;
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
    if(strcmp(url,"/v1/chat/completions")||strcmp(method,"POST")){r->replied=true;return error_reply(c,404);}
    r->replied=true;json_error_t je;json_t *body=json_loadb(r->body?r->body:"",r->used,JSON_REJECT_DUPLICATES,&je);
    json_t *m=json_object_get(body,"model");const char *model=json_string_value(m),*physical=NULL;
    if(!json_is_object(body)||!model||strlen(model)!=json_string_length(m)||!route(rt,model,&r->endpoint,&physical)){json_decref(body);return error_reply(c,400);}
    json_t *rewritten=json_string(physical);
    if(!rewritten || json_object_set_new(body,"model",rewritten)!=0){json_decref(body);return error_reply(c,500);}
    /* M2 hard gate: final provider object, before serialization and any network. */
    if(rc_dispatch_gate&&rc_dispatch_gate(rt,body,&r->endpoint)){json_decref(body);return error_reply(c,403);}
    if((r->endpoint!=RC_ENDPOINT_PRIVATE&&r->endpoint!=RC_ENDPOINT_PUBLIC)||(r->endpoint==RC_ENDPOINT_PUBLIC&&!rt->config.public_url)){json_decref(body);return error_reply(c,403);}
    r->payload=json_dumps(body,JSON_COMPACT);json_decref(body);if(!r->payload)return error_reply(c,500);
    const union MHD_ConnectionInfo *info=MHD_get_connection_info(c,MHD_CONNECTION_INFO_CONNECTION_FD);
    if(!info || (r->downstream_fd=dup(info->connect_fd))<0)return error_reply(c,503);
    if(pthread_create(&r->worker,NULL,upstream,r))return error_reply(c,503);
    r->started=true;
    pthread_mutex_lock(&r->lock);while(!r->headers&&!r->done&&!r->cancel)if(pthread_cond_timedwait(&r->changed,&r->lock,&r->deadline)!=0)r->cancel=true;
    long status=r->status;bool failed=r->cancel||!r->headers;bool sse=r->sse;pthread_mutex_unlock(&r->lock);
    if(failed||status<200||status>=300)return error_reply(c,502);
    struct MHD_Response *response=MHD_create_response_from_callback(MHD_SIZE_UNKNOWN,16384,read_response,r,NULL);if(!response)return MHD_NO;
    MHD_add_response_header(response,"Content-Type",sse?"text/event-stream":"application/json");
    enum MHD_Result result=MHD_queue_response(c,(unsigned)status,response);MHD_destroy_response(response);return result;
}
int rc_router_serve(rc_runtime *rt){
    struct sockaddr_in bind_addr={.sin_family=AF_INET,.sin_port=htons((uint16_t)rt->config.listen_port)};
    if(inet_pton(AF_INET,rt->config.listen_host,&bind_addr.sin_addr)!=1)return 1;
    signal(SIGTERM,stop_server);signal(SIGINT,stop_server);signal(SIGPIPE,SIG_IGN);
    struct MHD_Daemon *daemon=MHD_start_daemon(MHD_USE_INTERNAL_POLLING_THREAD|MHD_USE_THREAD_PER_CONNECTION, (uint16_t)rt->config.listen_port,NULL,NULL,handle,rt,
        MHD_OPTION_SOCK_ADDR,&bind_addr,MHD_OPTION_CONNECTION_LIMIT,rt->max_connections,
        MHD_OPTION_CONNECTION_TIMEOUT,rt->request_timeout_seconds,MHD_OPTION_CONNECTION_MEMORY_LIMIT,(size_t)32768,
        MHD_OPTION_NOTIFY_COMPLETED,completed,NULL,MHD_OPTION_END);
    if(!daemon)return 1;
    while(!stopping){struct timespec t={0,100000000};nanosleep(&t,NULL);}MHD_stop_daemon(daemon);return 0;
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
