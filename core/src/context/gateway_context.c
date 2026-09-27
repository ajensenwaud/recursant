#define _POSIX_C_SOURCE 200809L
#include "recursant/gateway_context.h"
#include "recursant/selector.h"
#include "recursant/interpreter.h"
#include <strings.h>
#include <time.h>
#include <pthread.h>
#include <sys/random.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SCOPES 32
struct scope {
    char task[64], session[64], branch[64], generation[33];
    bool inflight, pinned, owner, private_only;
    rc_endpoint endpoint;char model[129];
    json_t *history, *pending;
    int last_row, evidence_row;
    uint64_t revision, sequence, observed;
    rc_context_key key;rc_interpreter_result interpretation;
};
struct physical {rc_attempt_headers headers;rc_attempt_id id;int scope;bool complete;};
struct rc_gateway_context {
    pthread_mutex_t lock;
    bool active;
    char tenant[64], project[64], auto_alias[64];
    size_t baseline, count, used;
    uint64_t ttl, boot;
    rc_candidate candidates[RC_SELECTOR_MAX_CANDIDATES];
    rc_candidate_quote quotes[RC_SELECTOR_MAX_CANDIDATES];
    rc_candidate_registry *registry;
    struct scope scopes[SCOPES];
    rc_config auth_config;rc_auth_table auth;char *authorization;
    rc_attempt_ledger *ledger;size_t rows_used;
    struct physical rows[RC_ATTEMPT_MAX_ROWS];
    rc_context_registry *contexts;rc_interpreter *worker;
};
static bool keys(json_t *o,const char *allowed) {
    if(!json_is_object(o))return false;
    const char *k;json_t *v;
    json_object_foreach(o,k,v){char b[128];if(strchr(k,'|')||snprintf(b,sizeof b,"|%s|",k)>=(int)sizeof b||!strstr(allowed,b))return false;}
    return true;
}
static const char *token(json_t *o,const char *k,size_t max) {
    json_t *v=json_object_get(o,k);const char *s=json_string_value(v);
    if(!s||!json_string_length(v)||json_string_length(v)>max)return NULL;
    for(size_t i=0;i<json_string_length(v);i++)if((unsigned char)s[i]<33||(unsigned char)s[i]>126)return NULL;
    return s;
}
static bool eq(json_t *o,const char *k,const char *s){const char *v=token(o,k,128);return v&&!strcmp(v,s);}
static bool integer(json_t *o,const char *k,uint64_t max,uint64_t *out) {
    json_t *v=json_object_get(o,k);if(!json_is_integer(v)||json_integer_value(v)<=0||(uint64_t)json_integer_value(v)>max)return false;
    *out=(uint64_t)json_integer_value(v);return true;
}
static bool alias(rc_runtime *rt,const char *s,size_t *out) {
    for(size_t i=0;i<rt->config.alias_count;i++)if(!strcmp(s,rt->config.aliases[i].from)){*out=i;return true;}
    return false;
}
bool rc_gateway_configure(rc_runtime *rt,json_t *o) {
    if(!o)return true;
    if(eq(o,"mode","disabled"))return keys(o,"|mode|");
    if(!keys(o,"|mode||tenant||project||auto_alias||baseline_alias||ttl_ms||candidates||source_key_env|") ||
       (!eq(o,"mode","active")&&!eq(o,"mode","shadow")) || rt->private_key || !rt->source_key)return false;
    const char *tenant=token(o,"tenant",63),*project=token(o,"project",63),*automatic=token(o,"auto_alias",63),*baseline=token(o,"baseline_alias",128);
    if(!tenant||!project||!automatic||!baseline)return false;
    struct rc_gateway_context *g=calloc(1,sizeof *g);if(!g)return false;
    pthread_mutex_init(&g->lock,NULL);rt->gateway=g;
    g->active=eq(o,"mode","active");strcpy(g->tenant,tenant);strcpy(g->project,project);strcpy(g->auto_alias,automatic);
    if(!integer(o,"ttl_ms",180000,&g->ttl)||!alias(rt,baseline,&g->baseline))return false;
    if(!strcmp(automatic,rt->config.private_model)||(rt->config.public_model&&!strcmp(automatic,rt->config.public_model)))return false;
    for(size_t i=0;i<rt->config.alias_count;i++)if(!strcmp(automatic,rt->config.aliases[i].from)||!strcmp(automatic,rt->config.aliases[i].model))return false;
    json_t *list=json_object_get(o,"candidates");g->count=json_array_size(list);
    if(!json_is_array(list)||!g->count||g->count>RC_SELECTOR_MAX_CANDIDATES)return false;
    bool found=false;
    for(size_t i=0;i<g->count;i++) {
        json_t *v=json_array_get(list,i);const char *a=token(v,"alias",128);
        if(!keys(v,"|alias||quality_evidence||qualified_tasks||context_limit||expected_task_cost|")||!a||!token(v,"quality_evidence",128)||!alias(rt,a,&g->candidates[i].alias_index)||!integer(v,"context_limit",100000000,&g->candidates[i].context_limit))return false;
        json_t *tasks=json_object_get(v,"qualified_tasks");if(!json_is_array(tasks)||json_array_size(tasks)>1)return false;
        if(json_array_size(tasks)){json_t *t=json_array_get(tasks,0);if(!json_is_string(t)||json_string_length(t)!=13||strcmp(json_string_value(t),"format_simple"))return false;g->candidates[i].qualified_tasks=1;}
        json_t *cost=json_object_get(v,"expected_task_cost");double d=json_number_value(cost);
        if(!json_is_number(cost)||!isfinite(d)||d<0)return false;
        g->quotes[i]=(rc_candidate_quote){.permitted=true,.expected_task_cost=d};
        if(g->candidates[i].alias_index==g->baseline)found=true;
    }
    if(!found)return false;
    g->registry=rc_candidates_create(1,g->candidates,g->count);return g->registry!=NULL;
}
bool rc_gateway_start(rc_runtime *rt) {
    struct rc_gateway_context *g=rt->gateway;if(!g)return true;
    if(getrandom(&g->boot,sizeof g->boot,0)!=sizeof g->boot)return false;
    g->auth_config.project_count=1;g->auth.cfg=&g->auth_config;g->auth.tokens=&rt->auth_key;
    g->authorization=malloc(strlen(rt->auth_key)+8);if(!g->authorization)return false;
    sprintf(g->authorization,"Bearer %s",rt->auth_key);
    g->ledger=rc_attempt_create(&g->auth,RC_ATTEMPT_MAX_ROWS,180000);
    g->contexts=rc_context_create(SCOPES,180000);
    char url[2049];size_t n=strlen(rt->config.private_url);while(n&&rt->config.private_url[n-1]=='/')n--;
    if(snprintf(url,sizeof url,"%.*s/chat/completions",(int)n,rt->config.private_url)>=(int)sizeof url)return false;
    rc_interpreter_config cfg={.enabled=true,.url=url,.model=rt->config.private_model,.max_tokens=4096,.deadline_ms=180000,.structured_output=true};
    g->worker=rc_interpreter_create(&cfg);
    return g->ledger&&g->contexts&&g->worker;
}
void rc_gateway_destroy(rc_runtime *rt) {
    struct rc_gateway_context *g=rt->gateway;if(!g)return;
    rc_interpreter_destroy(g->worker);rc_context_destroy(g->contexts);rc_attempt_destroy(g->ledger);
    for(size_t i=0;i<g->used;i++){json_decref(g->scopes[i].history);json_decref(g->scopes[i].pending);}
    free(g->authorization);rc_candidates_destroy(g->registry);pthread_mutex_destroy(&g->lock);free(g);rt->gateway=NULL;
}
static unsigned ingest(rc_runtime *,json_t *);
unsigned rc_gateway_event(rc_runtime *rt,const char *path,json_t *body,json_t **out) {
    struct rc_gateway_context *g=rt->gateway;if(!g)return 404;
    if(!strcmp(path,"/v1/context")){
        unsigned status=ingest(rt,body);
        if(status==202){*out=json_pack("{s:s}","status","accepted");if(!*out)return 500;}
        return status;
    }
    if(strcmp(path,"/v1/context/open"))return 404;
    const char *task=token(body,"task_id",63),*session=token(body,"session_id",63),*branch=token(body,"branch",63);
    if(!keys(body,"|task_id||session_id||branch|")||!task||!session||!branch)return 400;
    pthread_mutex_lock(&g->lock);
    for(size_t i=0;i<g->used;i++)if(!strcmp(g->scopes[i].task,task)&&!strcmp(g->scopes[i].session,session)&&!strcmp(g->scopes[i].branch,branch)){pthread_mutex_unlock(&g->lock);return 409;}
    if(g->used==SCOPES){pthread_mutex_unlock(&g->lock);return 503;}
    struct scope *s=&g->scopes[g->used++];strcpy(s->task,task);strcpy(s->session,session);strcpy(s->branch,branch);
    snprintf(s->generation,sizeof s->generation,"%016llx%016llx",(unsigned long long)g->boot,(unsigned long long)g->used);
    s->last_row=-1;s->evidence_row=-1;
    strcpy(s->key.tenant,g->tenant);strcpy(s->key.project,g->project);strcpy(s->key.task_generation,s->generation);strcpy(s->key.branch,s->branch);strcpy(s->key.step,"trajectory");strcpy(s->key.attempt,"aggregate");
    *out=json_pack("{s:s,s:s,s:s,s:s}","task_id",task,"session_id",session,"branch",branch,"generation",s->generation);
    pthread_mutex_unlock(&g->lock);return *out?201:500;
}
bool rc_gateway_auto(rc_runtime *rt,const char *model,rc_endpoint *endpoint,const char **physical) {
    struct rc_gateway_context *g=rt->gateway;if(!g||strcmp(model,g->auto_alias))return false;
    rc_alias *a=&rt->config.aliases[g->baseline];*endpoint=a->endpoint;*physical=a->model;return true;
}
static uint64_t now_ms(void) {
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
}
void rc_gateway_header(rc_gateway_headers *h,const char *name,const char *value) {
    rc_attempt_header(&h->invocation,name,value);
    char *out=NULL;size_t cap=0;
    if(!strcasecmp(name,"X-Recursant-generation")){out=h->generation;cap=sizeof h->generation;}
    if(!strcasecmp(name,"X-Recursant-branch")){out=h->branch;cap=sizeof h->branch;}
    if(!out)return;
    if(out[0]||!value||!value[0]||strlen(value)>=cap){h->invalid=true;return;}
    for(const char *s=value;*s;s++)if((unsigned char)*s<33||(unsigned char)*s>126){h->invalid=true;return;}
    strcpy(out,value);
}
static int scope_find(struct rc_gateway_context *g,const char *generation,const char *branch) {
    for(size_t i=0;i<g->used;i++)if(!strcmp(g->scopes[i].generation,generation)&&!strcmp(g->scopes[i].branch,branch))return (int)i;
    return -1;
}
static bool same_headers(const rc_attempt_headers *a,const rc_attempt_headers *b) {
    if(a->invalid||b->invalid||a->mask!=31||b->mask!=31)return false;
    for(size_t i=0;i<5;i++)if(strcmp(a->values[i],b->values[i]))return false;
    return true;
}
static bool exact(struct rc_gateway_context *g,int row,uint64_t now) {
    if(row<0||(size_t)row>=g->rows_used)return false;
    struct physical *r=&g->rows[row];rc_attempt_view v;
    return rc_attempt_get(g->ledger,g->authorization,&r->headers,r->id,now,&v)&&v.exact&&v.count_known&&v.physical_count==1;
}
static void poll_locked(struct rc_gateway_context *g,uint64_t now) {
    rc_interpreter_result result;
    for(unsigned i=0;i<RC_INTERPRETER_CAPACITY&&rc_interpreter_poll(g->worker,&result);i++) {
        int slot=scope_find(g,result.key.task_generation,result.key.branch);if(slot<0)continue;
        struct scope *s=&g->scopes[slot];
        if(result.status!=RC_INTERPRETER_VALID||s->revision!=result.revision||!exact(g,s->evidence_row,now))continue;
        if(rc_context_interpret(g->contexts,&s->key,result.revision,now,result.next_action)==RC_CONTEXT_OK)s->interpretation=result;
    }
}
void rc_gateway_poll(rc_runtime *rt) {
    struct rc_gateway_context *g=rt->gateway;if(!g)return;
    pthread_mutex_lock(&g->lock);poll_locked(g,now_ms());pthread_mutex_unlock(&g->lock);
}
static unsigned ingest(rc_runtime *rt,json_t *body) {
    struct rc_gateway_context *g=rt->gateway;
    const char *generation=token(body,"generation",32),*branch=token(body,"branch",63);uint64_t revision,sequence;
    if(!keys(body,"|generation||branch||revision||event|")||!generation||!branch||!integer(body,"revision",9007199254740991ULL,&revision))return 400;
    pthread_mutex_lock(&g->lock);unsigned status=400;uint64_t now=now_ms();
    int slot=scope_find(g,generation,branch);if(slot<0){status=403;goto done;}
    struct scope *s=&g->scopes[slot];json_t *event=json_object_get(body,"event");
    if(revision>s->revision){s->evidence_row=-1;memset(&s->interpretation,0,sizeof s->interpretation);}
    if(!keys(event,"|schema||kind||task_id||session_id||turn_id||api_request_id||attempt||sequence||dropped||upstream_gaps||association||routing_eligible||association_scope||physical_routing_eligible||physical_attempt_uniqueness||stream_association||text||text_truncated|"))goto done;
    if(!eq(event,"schema","recursant.context.v1")||!eq(event,"task_id",s->task)||!eq(event,"session_id",s->session)) {status=403;goto done;}
    json_t *drops=json_object_get(event,"dropped");
    if(!json_is_integer(drops)||json_integer_value(drops)!=0||eq(event,"kind","invalidation")) {rc_attempt_lost(g->ledger);status=409;goto done;}
    if(!integer(event,"sequence",9007199254740991ULL,&sequence)||revision<=s->revision||sequence<=s->sequence){status=409;goto done;}
    if(!eq(event,"kind","response")||!eq(event,"upstream_gaps","unknown")||!eq(event,"association","exact")||!json_is_true(json_object_get(event,"routing_eligible"))||!eq(event,"association_scope","middleware_invocation")||!json_is_false(json_object_get(event,"physical_routing_eligible"))||!eq(event,"physical_attempt_uniqueness","unproven")||!eq(event,"stream_association","unsupported"))goto done;
    static const char *names[]={"task_id","session_id","turn_id","api_request_id","attempt"};
    rc_attempt_headers h={.mask=31};
    for(size_t i=0;i<5;i++){const char *v=token(event,names[i],128);if(!v)goto done;strcpy(h.values[i],v);}
    int row=-1;
    for(size_t i=0;i<g->rows_used;i++)if(same_headers(&h,&g->rows[i].headers)){
        if(row!=-1){status=409;goto done;}row=(int)i;
    }
    if(row<0||g->rows[row].scope!=slot){status=403;goto done;}
    if(s->inflight||!g->rows[row].complete||row!=s->last_row){status=409;goto done;}
    json_t *text=json_object_get(event,"text"),*truncated=json_object_get(event,"text_truncated");
    if(!keys(text,"|assistant_plan||reasoning|")||!keys(truncated,"|assistant_plan||reasoning|")||!json_object_size(text)||json_object_size(text)!=json_object_size(truncated))goto done;
    rc_interpreter_input in={.key=s->key,.revision=revision};const char *k;json_t *v;
    json_object_foreach(text,k,v){
        if(!json_is_string(v)||!json_string_length(v)||json_string_length(v)>1024||strlen(json_string_value(v))!=json_string_length(v)||!json_is_false(json_object_get(truncated,k)))goto done;
        rc_interpreter_evidence *e=&in.evidence[in.evidence_count++];strcpy(e->id,k);strcpy(e->source,"model_claim");strcpy(e->text,json_string_value(v));
    }
    /* Source text never leaves the configured private interpreter. Its M2
     * placement restriction also survives as scope authority, not advisory TTL. */
    if(rc_dispatch_gate&&rt->compliance_enabled){
        json_t *messages=json_array(),*probe=json_object();
        bool built=messages&&probe;
        for(size_t i=0;built&&i<in.evidence_count;i++){
            json_t *m=json_pack("{s:s,s:s}","role","user","content",in.evidence[i].text);
            if(!m||json_array_append_new(messages,m))built=false;
        }
        if(built&&(json_object_set_new(probe,"model",json_string(rt->config.private_model))||json_object_set(probe,"messages",messages)))built=false;
        rc_endpoint placement=RC_ENDPOINT_PUBLIC;
        if(!built||rc_dispatch_gate(rt,probe,&placement)||placement!=RC_ENDPOINT_PUBLIC)s->private_only=true;
        json_decref(messages);json_decref(probe);
    }
    rc_attempt_source_complete(g->ledger,g->authorization,&h,now);
    if(!exact(g,row,now)){status=409;goto done;}
    if(rc_context_put(g->contexts,&s->key,revision,now,g->ttl,"authorized source response",false)!=RC_CONTEXT_OK){status=409;goto done;}
    s->revision=revision;s->sequence=sequence;s->observed=now;s->evidence_row=row;memset(&s->interpretation,0,sizeof s->interpretation);
    status=rc_interpreter_try_submit(g->worker,&in)?202:503;
done:
    pthread_mutex_unlock(&g->lock);return status;
}
static bool plain_message(json_t *m) {
    json_t *v=json_object_get(m,"content");
    return keys(m,"|role||content|")&&json_object_size(m)==2&&json_is_string(v)&&json_string_length(v)==strlen(json_string_value(v));
}
static bool replayable(struct scope *s,json_t *body) {
    if(!keys(body,"|model||messages||max_tokens||temperature||top_p||stream|"))return false;
    json_t *stream=json_object_get(body,"stream");if(stream&&!json_is_false(stream))return false;
    uint64_t output;if(!integer(body,"max_tokens",100000,&output))return false;
    json_t *messages=json_object_get(body,"messages");size_t n=json_array_size(messages),prior=json_array_size(s->history);
    if(!json_is_array(messages)||!n||n>256||n<=prior)return false;
    for(size_t i=0;i<n;i++){
        json_t *m=json_array_get(messages,i);if(!plain_message(m))return false;
        if(i<prior){if(!json_equal(m,json_array_get(s->history,i)))return false;}
        else if(!eq(m,"role","user") && !(i==0&&!s->owner&&eq(m,"role","system")))return false;
    }
    char *serialized=json_dumps(messages,JSON_COMPACT);if(!serialized)return false;
    bool bounded=strlen(serialized)<=32768;free(serialized);return bounded;
}
unsigned rc_gateway_prepare(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint *endpoint,rc_gateway_ticket *ticket) {
    struct rc_gateway_context *g=rt->gateway;ticket->scope=-1;ticket->row=-1;
    if(!g)return rc_dispatch_gate&&rc_dispatch_gate(rt,body,endpoint)?403:0;
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();unsigned status=0;struct scope *s=NULL;
    poll_locked(g,now);
    if(g->rows_used==RC_ATTEMPT_MAX_ROWS||h->invocation.invalid||h->invocation.mask!=31)rc_attempt_lost(g->ledger);
    if(automatic&&(h->generation[0]||h->branch[0]||h->invalid)) {
        int slot=scope_find(g,h->generation,h->branch);
        if(h->invalid||slot<0){status=403;goto done;}
        s=&g->scopes[slot];
        if(strcmp(s->task,h->invocation.values[0])||strcmp(s->session,h->invocation.values[1])){status=403;goto done;}
        if(s->inflight){status=409;goto done;}
        ticket->scope=slot;
        if(!replayable(s,body))s->pinned=true;
        if(s->pinned&&s->owner){*endpoint=s->endpoint;if(json_object_set_new(body,"model",json_string(s->model))){status=500;goto done;}}
        else {
            rc_context_snapshot snapshot;bool usable=rc_context_get(g->contexts,&s->key,now,&snapshot)==RC_CONTEXT_OK&&snapshot.has_interpretation&&snapshot.revision==s->interpretation.revision&&exact(g,s->evidence_row,now)&&s->evidence_row==s->last_row;
            for(size_t i=0;i<g->rows_used;i++)if(same_headers(&h->invocation,&g->rows[i].headers))usable=false;
            char *wire=json_dumps(body,JSON_COMPACT);uint64_t tokens=wire?strlen(wire):0;free(wire);
            json_t *max=json_object_get(body,"max_tokens");if(json_is_integer(max)&&json_integer_value(max)>0&&json_integer_value(max)<=100000)tokens+=(uint64_t)json_integer_value(max);else usable=false;
            uint64_t task=usable&&!strcmp(s->interpretation.next_action,"format_result")&&!strcmp(s->interpretation.difficulty_band,"simple")&&!strcmp(s->interpretation.coverage,"partial")?1:0;
            rc_selection_request req={.registry_version=1,.baseline_alias=g->baseline,.continuity=RC_CONTINUITY_REPLAYABLE,.context_usable=usable&&!s->pinned,.now=now,.context_observed_at=s->observed,.context_expires_at=usable?snapshot.expires_at:0,.task_class=task,.context_tokens=tokens?tokens:1};
            rc_candidate_quote quotes[RC_SELECTOR_MAX_CANDIDATES];bool baseline_permitted=false;
            for(size_t i=0;i<g->count;i++){
                quotes[i]=g->quotes[i];rc_alias *a=&rt->config.aliases[g->candidates[i].alias_index];
                json_t *probe=json_deep_copy(body);rc_endpoint ep=a->endpoint;
                if(!probe||json_object_set_new(probe,"model",json_string(a->model))){json_decref(probe);status=500;goto done;}
                quotes[i].permitted=(!s->private_only||ep==RC_ENDPOINT_PRIVATE)&&
                    (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
                if(g->candidates[i].alias_index==g->baseline)baseline_permitted=quotes[i].permitted;
                json_decref(probe);
            }
            /* A baseline placement veto belongs to final M2, not to inferred
             * context. Do not ask the downshift selector to invent recovery. */
            rc_selection selected={.alias_index=g->baseline};
            if(baseline_permitted&&rc_select(g->registry,quotes,g->count,&req,&selected)!=RC_SELECT_OK){status=403;goto done;}
            if(g->active){rc_alias *a=&rt->config.aliases[selected.alias_index];*endpoint=a->endpoint;if(json_object_set_new(body,"model",json_string(a->model))){status=500;goto done;}}
        }
    }
    if(s&&s->private_only){
        *endpoint=RC_ENDPOINT_PRIVATE;
        if(json_object_set_new(body,"model",json_string(rt->config.private_model))){status=500;goto done;}
    }
    if(rc_dispatch_gate&&rc_dispatch_gate(rt,body,endpoint)){status=403;goto done;}
    const char *model=json_string_value(json_object_get(body,"model"));
    if(s){
        if(!model||strlen(model)>128){status=403;goto done;}
        if(s->pinned&&s->owner&&(*endpoint!=s->endpoint||strcmp(model,s->model))){status=403;goto done;}
        s->endpoint=*endpoint;strcpy(s->model,model);s->owner=true;s->inflight=true;
        if(s->pinned){json_decref(s->history);s->history=NULL;}
        else {s->pending=json_deep_copy(json_object_get(body,"messages"));if(!s->pending)s->pinned=true;}
    }
    rc_attempt_result recorded=rc_attempt_begin(g->ledger,g->authorization,&h->invocation,now,&ticket->id);ticket->begun=true;
    if(recorded==RC_ATTEMPT_TRACKED&&g->rows_used<RC_ATTEMPT_MAX_ROWS){
        ticket->row=(int)g->rows_used;g->rows[g->rows_used++]=(struct physical){.headers=h->invocation,.id=ticket->id,.scope=ticket->scope};
    }
    if(s)s->last_row=ticket->row;
done:
    pthread_mutex_unlock(&g->lock);return status;
}
void rc_gateway_finish(rc_runtime *rt,rc_gateway_ticket *ticket,bool complete,bool sse,const char *response,size_t length) {
    struct rc_gateway_context *g=rt->gateway;if(!g||!ticket->begun)return;
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();
    rc_attempt_finish(g->ledger,ticket->id,complete,now);
    if(ticket->row>=0)g->rows[ticket->row].complete=complete;
    if(ticket->scope>=0){
        struct scope *s=&g->scopes[ticket->scope];s->inflight=false;
        json_error_t error;json_t *root=complete&&!sse&&response&&length?json_loadb(response,length,JSON_REJECT_DUPLICATES,&error):NULL;
        json_t *choices=json_object_get(root,"choices"),*choice=json_array_get(choices,0),*message=json_object_get(choice,"message");
        bool safe=keys(root,"|id||object||created||model||choices||usage|")&&json_array_size(choices)==1&&keys(choice,"|index||message||finish_reason|")&&eq(choice,"finish_reason","stop")&&plain_message(message)&&eq(message,"role","assistant");
        if(!safe||!s->pending||json_array_append(s->pending,message))s->pinned=true;
        if(!s->pinned){json_decref(s->history);s->history=s->pending;s->pending=NULL;}
        json_decref(s->pending);s->pending=NULL;json_decref(root);
    }
    ticket->begun=false;pthread_mutex_unlock(&g->lock);
}
