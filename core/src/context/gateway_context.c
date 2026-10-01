#define _POSIX_C_SOURCE 200809L
#include "recursant/tool_boundary.h"
#include "recursant/gateway_context.h"
#include "recursant/selector.h"
#include "recursant/interpreter.h"
#include "recursant/cost.h"
#include "recursant/signals.h"
#include "recursant/judge.h"
#include <strings.h>
#include <time.h>
#include <pthread.h>
#include <sys/random.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Registered (header) scopes keep their original cap; the rest of the table
 * holds request-stream sessions, which are never registered or closed. */
#define EXPLICIT_SCOPES 32
#define SCOPES 160
#define HINTS 64
#define HINT_TTL_MS 600000u
/* Native request-profile requirements (operator-declared destination
 * capabilities; bit positions continue RC_TOOL_CAP_*). */
#define RC_REQ_STREAM_TOOLS UINT32_C(8)
#define RC_REQ_NESTED_SCHEMAS UINT32_C(16)
#define RC_CAP_BITS 5u
#define RC_EFFORT_MAX 8u
#define RC_EFFORT_BYTES 64u
#define RC_TOOLS_MAX 64u
#define RC_TOOLS_MAX_BYTES 65536u
#define RC_SCHEMA_MAX_DEPTH 24u
#define RC_SCHEMA_MAX_NODES 16384u
struct scope {
    char task[64], session[64], branch[64], generation[33];
    bool inflight, pinned, owner, private_only;
    rc_endpoint endpoint;char model[129];
    json_t *history, *pending, *pending_tools, *observed_calls;
    bool callback_seen[RC_TOOL_MAX_CALLS];
    rc_tool_boundary *boundary;
    uint32_t requirements;
    bool pending_parallel;
    json_t *pending_choice;
    int last_row, evidence_row;
    bool open;
    uint64_t revision, sequence, observed, active;
    rc_context_key key;rc_interpreter_result interpretation;
    /* S3 cost evidence: provider usage of the last completed turn, served by
     * usage_model; usage_messages = that request's messages + the reply. */
    rc_usage_observation usage;size_t usage_messages,request_messages;char usage_model[129];
    /* S4: physically completed turns in this scope (signal input only). */
    uint64_t turns;
    /* Sticky request contract: exact projection of the scope's first request
     * (tools, tool_choice, parallel_tool_calls, reasoning_effort and, for
     * profile scopes, stream_options). Any later difference pins. */
    json_t *contract;bool profile;char effort[RC_EFFORT_BYTES+1];
    /* Request-stream session (context.sessions "request"): created from an
     * unregistered automatic request, found again by its conversation opening
     * (anchor) and, when the harness sends it, X-Recursant-session-id (ident).
     * Never addressable by generation/branch. delegated = another session
     * handed this conversation out (subagent). */
    bool implicit,delegated;uint64_t anchor;char ident[RC_ATTEMPT_TOKEN_SIZE];size_t seen_messages;
    /* Orchestrator: one of this session's pending tool calls handed work to a
     * subagent. Its next step integrates and reviews that work: no downshift
     * class for that step (offline replay 2026-10-01: gpt-4.1-mini repeated
     * gpt-4.1's move on 1 of 24 such steps). Cleared after that step. */
    bool awaiting_delegates;
};
/* Advisory harness telemetry: session -> role. Bounded, expiring, never
 * continuity or placement authority. */
struct hint {char session[RC_ATTEMPT_TOKEN_SIZE];uint64_t at;bool delegated,set;};
/* Mirror row slots never move: scopes and tickets hold indices. A slot is only
 * freed when settled, expired, not referenced by any open scope, and no live
 * row shares its full key (same tombstone horizon as the ledger). */
struct physical {rc_attempt_headers headers;rc_attempt_id id;int scope;bool complete,in_use,settled;uint64_t begun;};
struct rc_gateway_context {
    pthread_mutex_t lock;
    bool active;
    char tenant[64], project[64], auto_alias[64];
    size_t baseline, count;
    uint64_t ttl, attempt_ttl, boot, generations;
    rc_candidate candidates[RC_SELECTOR_MAX_CANDIDATES];
    rc_candidate_quote quotes[RC_SELECTOR_MAX_CANDIDATES];
    rc_candidate_cost costs[RC_SELECTOR_MAX_CANDIDATES];bool priced;uint64_t expected_output;
    bool signals; /* S4 context.signals: "on" enables the structured-signal class */
    bool implicit; /* context.sessions "request": sessions from the request stream */
    struct hint hints[HINTS];
    uint32_t cap_known[RC_SELECTOR_MAX_CANDIDATES], cap_supported[RC_SELECTOR_MAX_CANDIDATES];
    char efforts[RC_SELECTOR_MAX_CANDIDATES][RC_EFFORT_MAX][RC_EFFORT_BYTES+1];size_t effort_count[RC_SELECTOR_MAX_CANDIDATES];
    rc_candidate_registry *registry;
    struct scope scopes[SCOPES];
    rc_config auth_config;rc_auth_table auth;char *authorization;
    rc_attempt_ledger *ledger;size_t rows_used;
    struct physical rows[RC_ATTEMPT_MAX_ROWS];
    rc_context_registry *contexts;rc_interpreter *worker;
    /* Optional synchronous per-turn judge (context.judge). Advisory only. */
    rc_judge_config judge;
};
static bool keys(json_t *o,const char *allowed) {
    if(!json_is_object(o))return false;
    const char *k;json_t *v;
    json_object_foreach(o,k,v){char b[128];if(!*k||strchr(k,'|')||snprintf(b,sizeof b,"|%s|",k)>=(int)sizeof b||!strstr(allowed,b))return false;}
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
    if(!keys(o,"|mode||tenant||project||auto_alias||baseline_alias||ttl_ms||attempt_ttl_ms||expected_output_tokens||signals||sessions||judge||candidates||source_key_env|") ||
       (!eq(o,"mode","active")&&!eq(o,"mode","shadow")) || rt->private_key || !rt->source_key)return false;
    const char *tenant=token(o,"tenant",63),*project=token(o,"project",63),*automatic=token(o,"auto_alias",63),*baseline=token(o,"baseline_alias",128);
    if(!tenant||!project||!automatic||!baseline)return false;
    struct rc_gateway_context *g=calloc(1,sizeof *g);if(!g)return false;
    pthread_mutex_init(&g->lock,NULL);rt->gateway=g;
    g->active=eq(o,"mode","active");strcpy(g->tenant,tenant);strcpy(g->project,project);strcpy(g->auto_alias,automatic);
    if(!integer(o,"ttl_ms",180000,&g->ttl)||!alias(rt,baseline,&g->baseline))return false;
    g->attempt_ttl=180000;
    if(json_object_get(o,"attempt_ttl_ms")&&!integer(o,"attempt_ttl_ms",180000,&g->attempt_ttl))return false;
    g->expected_output=RC_COST_DEFAULT_OUTPUT_TOKENS;
    if(json_object_get(o,"expected_output_tokens")&&!integer(o,"expected_output_tokens",RC_COST_MAX_OUTPUT_TOKENS,&g->expected_output))return false;
    /* Default off: existing configurations behave exactly as before S4. */
    if(json_object_get(o,"signals")&&!eq(o,"signals","on")&&!eq(o,"signals","off"))return false;
    g->signals=eq(o,"signals","on");
    /* Default "headers": only registered scopes are routed, as before. */
    if(json_object_get(o,"sessions")&&!eq(o,"sessions","request")&&!eq(o,"sessions","headers"))return false;
    g->implicit=eq(o,"sessions","request");
    /* context.judge: {provider, model, url, timeout_ms, routine_min,
     * difficulty_max}. Public-trust provider (its resolved key is borrowed);
     * requires signals on. Absent = off. */
    json_t *judge=json_object_get(o,"judge");
    if(judge){
        const char *provider=token(judge,"provider",63),*jmodel=token(judge,"model",128);
        json_t *url=json_object_get(judge,"url"),*t=json_object_get(judge,"timeout_ms"),*rm=json_object_get(judge,"routine_min"),*dm=json_object_get(judge,"difficulty_max");
        if(!keys(judge,"|provider||model||url||timeout_ms||routine_min||difficulty_max|")||!provider||!jmodel||!g->signals||
           !json_is_string(url)||json_string_length(url)>2048||strncmp(json_string_value(url),rt->test_mode?"http":"https://",rt->test_mode?4:8)||
           !json_is_integer(t)||json_integer_value(t)<50||json_integer_value(t)>2000||
           !json_is_number(rm)||json_number_value(rm)<0.5||json_number_value(rm)>1||
           !json_is_number(dm)||json_number_value(dm)<0||json_number_value(dm)>2)return false;
        size_t p=0;for(;p<rt->config.provider_count&&strcmp(rt->config.providers[p].name,provider);p++);
        if(p==rt->config.provider_count||rt->config.providers[p].trust!=RC_ENDPOINT_PUBLIC||!rt->provider_keys[p])return false;
        g->judge=(rc_judge_config){.enabled=true,.key=rt->provider_keys[p],.timeout_ms=(unsigned)json_integer_value(t),
            .routine_min=json_number_value(rm),.difficulty_max=json_number_value(dm)};
        strcpy(g->judge.url,json_string_value(url));strcpy(g->judge.model,jmodel);
    }
    if(!strcmp(automatic,rt->config.private_model)||(rt->config.public_model&&!strcmp(automatic,rt->config.public_model)))return false;
    for(size_t i=0;i<rt->config.alias_count;i++)if(!strcmp(automatic,rt->config.aliases[i].from)||!strcmp(automatic,rt->config.aliases[i].model))return false;
    json_t *list=json_object_get(o,"candidates");g->count=json_array_size(list);
    if(!json_is_array(list)||!g->count||g->count>RC_SELECTOR_MAX_CANDIDATES)return false;
    bool found=false;
    for(size_t i=0;i<g->count;i++) {
        json_t *v=json_array_get(list,i);const char *a=token(v,"alias",128);
        if(!keys(v,"|alias||quality_evidence||qualified_tasks||escalation||context_limit||expected_task_cost||price||capabilities|")||!a||!token(v,"quality_evidence",128)||!alias(rt,a,&g->candidates[i].alias_index)||!integer(v,"context_limit",100000000,&g->candidates[i].context_limit))return false;
        json_t *caps=json_object_get(v,"capabilities");
        if(caps){
            if(!keys(caps,"|tool_history||function_tools||parallel_tools||stream_tools||nested_tool_schemas||reasoning_effort|"))return false;
            static const char *names[RC_CAP_BITS]={"tool_history","function_tools","parallel_tools","stream_tools","nested_tool_schemas"};
            /* Operator attestation: exact reasoning_effort tokens the
             * destination accepts. Absent = none; empty/duplicate invalid. */
            json_t *efforts=json_object_get(caps,"reasoning_effort");
            if(efforts){
                if(!json_is_array(efforts)||!json_array_size(efforts)||json_array_size(efforts)>RC_EFFORT_MAX)return false;
                for(size_t e=0;e<json_array_size(efforts);e++){
                    json_t *holder=json_pack("{sO}","v",json_array_get(efforts,e));const char *t=holder?token(holder,"v",RC_EFFORT_BYTES):NULL;
                    bool ok=t!=NULL;
                    for(size_t f=0;ok&&f<g->effort_count[i];f++)if(!strcmp(g->efforts[i][f],t))ok=false;
                    if(ok)strcpy(g->efforts[i][g->effort_count[i]++],t);
                    json_decref(holder);if(!ok)return false;
                }
            }
            for(unsigned bit=0;bit<RC_CAP_BITS;bit++){
                json_t *value=json_object_get(caps,names[bit]);if(!value)continue;
                if(!json_is_boolean(value))return false;
                g->cap_known[i]|=1u<<bit;
                if(json_is_true(value))g->cap_supported[i]|=1u<<bit;
            }
        }
        /* Strict frozen names, no duplicates, unknown rejected. */
        json_t *tasks=json_object_get(v,"qualified_tasks");if(!json_is_array(tasks)||json_array_size(tasks)>4)return false;
        for(size_t t=0;t<json_array_size(tasks);t++){
            json_t *name=json_array_get(tasks,t);uint64_t bit;
            if(!json_is_string(name)||json_string_length(name)!=strlen(json_string_value(name))||
               !rc_task_qualifiable(json_string_value(name),&bit)||(g->candidates[i].qualified_tasks&bit))return false;
            g->candidates[i].qualified_tasks|=bit;
        }
        /* Explicit escalation marking = qualification for RECOVERY only. */
        json_t *escalation=json_object_get(v,"escalation");
        if(escalation&&!json_is_boolean(escalation))return false;
        if(json_is_true(escalation))g->candidates[i].qualified_tasks|=RC_TASK_RECOVERY;
        /* Exactly one of legacy expected_task_cost or USD/Mtok price; one
         * registry never mixes units (legacy totals are not comparable). */
        if(!rc_candidate_cost_parse(v,&g->costs[i])||(i&&g->costs[i].priced!=g->costs[0].priced))return false;
        g->priced=g->costs[i].priced;
        g->quotes[i]=(rc_candidate_quote){.permitted=true,.expected_task_cost=g->costs[i].priced?0:g->costs[i].fixed};
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
    g->ledger=rc_attempt_create(&g->auth,RC_ATTEMPT_MAX_ROWS,g->attempt_ttl);
    /* Generations are server-unique (boot entropy + monotonic counter) and an
     * unknown/closed generation is rejected before any registry call, so the
     * registry's closed-generation tombstone only needs to outlive this tick.
     * Spare slots absorb tombstones not yet purged. */
    g->contexts=rc_context_create(RC_CONTEXT_MAX_SLOTS,1);
    char url[2049];size_t n=strlen(rt->config.private_url);while(n&&rt->config.private_url[n-1]=='/')n--;
    if(snprintf(url,sizeof url,"%.*s/chat/completions",(int)n,rt->config.private_url)>=(int)sizeof url)return false;
    rc_interpreter_config cfg={.enabled=true,.url=url,.model=rt->config.private_model,.max_tokens=4096,.deadline_ms=180000,.structured_output=true};
    g->worker=rc_interpreter_create(&cfg);
    return g->ledger&&g->contexts&&g->worker;
}
void rc_gateway_destroy(rc_runtime *rt) {
    struct rc_gateway_context *g=rt->gateway;if(!g)return;
    rc_interpreter_destroy(g->worker);rc_context_destroy(g->contexts);rc_attempt_destroy(g->ledger);
    pthread_mutex_lock(&g->lock);
    for(size_t i=0;i<SCOPES;i++){
        json_decref(g->scopes[i].history);json_decref(g->scopes[i].pending);
        json_decref(g->scopes[i].pending_choice);json_decref(g->scopes[i].pending_tools);json_decref(g->scopes[i].observed_calls);rc_tool_boundary_free(g->scopes[i].boundary);
        json_decref(g->scopes[i].contract);
    }
    pthread_mutex_unlock(&g->lock);
    free(g->authorization);rc_candidates_destroy(g->registry);pthread_mutex_destroy(&g->lock);free(g);rt->gateway=NULL;
}
static unsigned ingest(rc_runtime *,json_t *);
static uint64_t now_ms(void);
static int scope_find(struct rc_gateway_context *,const char *,const char *);
/* Frees all per-scope JSON/boundary state. The generation is never reissued
 * (monotonic counter), so a request still carrying it matches no open scope and
 * is rejected (403) exactly like an unknown scope. Caller holds the lock and
 * guarantees !inflight so no ticket references the slot. */
static void scope_reclaim(struct rc_gateway_context *g,int slot,uint64_t now) {
    struct scope *s=&g->scopes[slot];
    if(!s->implicit)rc_context_close(g->contexts,&s->key,now);
    json_decref(s->history);json_decref(s->pending);json_decref(s->pending_choice);
    json_decref(s->pending_tools);json_decref(s->observed_calls);rc_tool_boundary_free(s->boundary);json_decref(s->contract);
    for(size_t i=0;i<RC_ATTEMPT_MAX_ROWS;i++)if(g->rows[i].in_use&&g->rows[i].scope==slot)g->rows[i].scope=-1;
    memset(s,0,sizeof *s);
}
/* Idle expiry only under slot pressure. The scope must be open, not inflight,
 * have no captured tool boundary awaiting replay, and be idle past the context
 * TTL. M2-derived private_only authority is never timed out; only an explicit
 * authenticated close releases it. */
static int scope_idle(struct rc_gateway_context *g,uint64_t now,bool implicit) {
    int best=-1;
    for(int i=0;i<SCOPES;i++){
        struct scope *s=&g->scopes[i];
        /* A request-stream session is never closed by its harness: an idle one
         * may be abandoned at a tool boundary. It holds no placement authority
         * (M2 re-scans every request), so reclaiming it is always safe: its
         * next request starts a new session at the baseline. */
        if(!s->open||s->implicit!=implicit||s->inflight||now<s->active||now-s->active<=g->ttl)continue;
        if(!implicit&&(s->boundary||s->private_only))continue;
        if(best<0||s->active<g->scopes[best].active)best=i;
    }
    return best;
}
unsigned rc_gateway_event(rc_runtime *rt,const char *path,json_t *body,json_t **out) {
    struct rc_gateway_context *g=rt->gateway;if(!g)return 404;
    if(!strcmp(path,"/v1/context")){
        unsigned status=ingest(rt,body);
        if(status==202){*out=json_pack("{s:s}","status","accepted");if(!*out)return 500;}
        return status;
    }
    if(!strcmp(path,"/v1/context/close")){
        const char *generation=token(body,"generation",32),*branch=token(body,"branch",63);
        if(!keys(body,"|generation||branch|")||!generation||!branch)return 400;
        pthread_mutex_lock(&g->lock);uint64_t now=now_ms();
        int slot=scope_find(g,generation,branch);unsigned status=slot<0?403:g->scopes[slot].inflight?409:200;
        if(status==200)scope_reclaim(g,slot,now);
        pthread_mutex_unlock(&g->lock);
        if(status==200){*out=json_pack("{s:s}","status","closed");if(!*out)return 500;}
        return status;
    }
    if(!strcmp(path,"/v1/context/hint")){
        /* Advisory only: the harness names a session and its role. "leaf" marks
         * a delegated subagent. It can make a first turn eligible for a class
         * the operator qualified; it never moves data or overrides M2. */
        const char *session=token(body,"session_id",RC_ATTEMPT_TOKEN_SIZE-1);
        bool leaf=eq(body,"role","leaf");
        if(!g->implicit)return 404;
        if(!keys(body,"|session_id||role||parent_session_id|")||!session||(!leaf&&!eq(body,"role","orchestrator"))||
           (json_object_get(body,"parent_session_id")&&!token(body,"parent_session_id",RC_ATTEMPT_TOKEN_SIZE-1)))return 400;
        pthread_mutex_lock(&g->lock);uint64_t now=now_ms();size_t slot=HINTS,oldest=0;
        for(size_t i=0;i<HINTS;i++){
            if(g->hints[i].set&&!strcmp(g->hints[i].session,session)){slot=i;break;}
            if(!g->hints[i].set){if(slot==HINTS)slot=i;}
            else if(g->hints[i].at<g->hints[oldest].at)oldest=i;
        }
        if(slot==HINTS)slot=oldest;
        g->hints[slot]=(struct hint){.at=now,.delegated=leaf,.set=true};strcpy(g->hints[slot].session,session);
        pthread_mutex_unlock(&g->lock);
        fprintf(stderr,"session_hint role=%s\n",leaf?"leaf":"orchestrator");
        *out=json_pack("{s:s}","status","accepted");return *out?202:500;
    }
    if(strcmp(path,"/v1/context/open"))return 404;
    const char *task=token(body,"task_id",63),*session=token(body,"session_id",63),*branch=token(body,"branch",63);
    if(!keys(body,"|task_id||session_id||branch|")||!task||!session||!branch)return 400;
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();int slot=-1;
    for(int i=0;i<SCOPES;i++)if(g->scopes[i].open&&!strcmp(g->scopes[i].task,task)&&!strcmp(g->scopes[i].session,session)&&!strcmp(g->scopes[i].branch,branch)){pthread_mutex_unlock(&g->lock);return 409;}
    size_t registered=0;
    for(int i=0;i<SCOPES;i++)if(g->scopes[i].open&&!g->scopes[i].implicit)registered++;
    for(int i=0;registered<EXPLICIT_SCOPES&&i<SCOPES&&slot<0;i++)if(!g->scopes[i].open)slot=i;
    if(slot<0&&(slot=scope_idle(g,now,false))>=0)scope_reclaim(g,slot,now);
    if(slot<0||g->generations==UINT64_MAX){pthread_mutex_unlock(&g->lock);return 503;}
    struct scope *s=&g->scopes[slot];s->open=true;s->active=now;strcpy(s->task,task);strcpy(s->session,session);strcpy(s->branch,branch);
    snprintf(s->generation,sizeof s->generation,"%016llx%016llx",(unsigned long long)g->boot,(unsigned long long)++g->generations);
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
    for(size_t i=0;i<SCOPES;i++)if(g->scopes[i].open&&!g->scopes[i].implicit&&!strcmp(g->scopes[i].generation,generation)&&!strcmp(g->scopes[i].branch,branch))return (int)i;
    return -1;
}
static bool same_headers(const rc_attempt_headers *a,const rc_attempt_headers *b) {
    if(a->invalid||b->invalid||a->mask!=31||b->mask!=31)return false;
    for(size_t i=0;i<5;i++)if(strcmp(a->values[i],b->values[i]))return false;
    return true;
}
/* Returns a free mirror slot, reclaiming under pressure only. A row is freed if
 * settled and expired, if no open scope's last/evidence index names it, and
 * if no live row shares its key. Live and referenced rows are never moved or
 * reused. -1 means capacity is truly exhausted: the caller records loss. */
static int row_slot(struct rc_gateway_context *g,uint64_t now) {
    if(g->rows_used<RC_ATTEMPT_MAX_ROWS)return (int)g->rows_used;
    for(size_t i=0;i<RC_ATTEMPT_MAX_ROWS;i++)if(!g->rows[i].in_use)return (int)i;
    int found=-1;
    for(size_t i=0;i<RC_ATTEMPT_MAX_ROWS;i++){
        struct physical *r=&g->rows[i];
        if(!r->settled||now-r->begun<g->attempt_ttl||now<r->begun)continue;
        bool keep=false;
        for(size_t j=0;!keep&&j<SCOPES;j++)if(g->scopes[j].open&&(g->scopes[j].last_row==(int)i||g->scopes[j].evidence_row==(int)i))keep=true;
        for(size_t j=0;!keep&&j<RC_ATTEMPT_MAX_ROWS;j++){
            struct physical *o=&g->rows[j];
            if(o->in_use&&(now<o->begun||now-o->begun<g->attempt_ttl)&&same_headers(&o->headers,&r->headers))keep=true;
        }
        if(keep)continue;
        memset(r,0,sizeof *r);r->scope=-1;
        if(found<0)found=(int)i;
    }
    return found;
}
static bool exact(struct rc_gateway_context *g,int row,uint64_t now) {
    if(row<0||(size_t)row>=g->rows_used||!g->rows[row].in_use)return false;
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
    bool tool_event=eq(event,"kind","tool");
    const char *event_keys=tool_event?
        "|schema||kind||task_id||session_id||turn_id||api_request_id||attempt||sequence||dropped||upstream_gaps||association||routing_eligible||association_scope||physical_routing_eligible||physical_attempt_uniqueness||tool_call_id||status||text||text_truncated|":
        "|schema||kind||task_id||session_id||turn_id||api_request_id||attempt||sequence||dropped||upstream_gaps||association||routing_eligible||association_scope||physical_routing_eligible||physical_attempt_uniqueness||stream_association||text||text_truncated|";
    if(!keys(event,event_keys))goto done;
    if(!eq(event,"schema","recursant.context.v1")||!eq(event,"task_id",s->task)||!eq(event,"session_id",s->session)) {status=403;goto done;}
    json_t *drops=json_object_get(event,"dropped");
    if(!json_is_integer(drops)||json_integer_value(drops)!=0||eq(event,"kind","invalidation")) {rc_attempt_lost(g->ledger);status=409;goto done;}
    if(!integer(event,"sequence",9007199254740991ULL,&sequence)||revision<=s->revision||sequence<=s->sequence){status=409;goto done;}
    if((!tool_event&&!eq(event,"kind","response"))||!eq(event,"upstream_gaps","unknown")||!eq(event,"association","exact")||!json_is_true(json_object_get(event,"routing_eligible"))||!eq(event,"association_scope","middleware_invocation")||!json_is_false(json_object_get(event,"physical_routing_eligible"))||!eq(event,"physical_attempt_uniqueness","unproven")||(!tool_event&&!eq(event,"stream_association","unsupported")))goto done;
    static const char *names[]={"task_id","session_id","turn_id","api_request_id","attempt"};
    rc_attempt_headers h={.mask=31};
    for(size_t i=0;i<5;i++){const char *v=token(event,names[i],128);if(!v)goto done;strcpy(h.values[i],v);}
    int row=-1;
    for(size_t i=0;i<g->rows_used;i++)if(g->rows[i].in_use&&same_headers(&h,&g->rows[i].headers)){
        if(row!=-1){status=409;goto done;}row=(int)i;
    }
    if(row<0||g->rows[row].scope!=slot){status=403;goto done;}
    if(s->inflight||!g->rows[row].complete||row!=s->last_row){status=409;goto done;}
    size_t callback=RC_TOOL_MAX_CALLS;
    if(tool_event){
        json_t *id=json_object_get(event,"tool_call_id");
        if(!json_is_string(id)||!json_string_length(id)||json_string_length(id)>RC_TOOL_MAX_ID_BYTES||
           !(eq(event,"status","ok")||eq(event,"status","success")||eq(event,"status","error")||eq(event,"status","blocked")||eq(event,"status","cancelled")||eq(event,"status","unknown")))goto done;
        for(size_t i=0;i<json_array_size(s->observed_calls);i++)
            if(json_equal(id,json_object_get(json_array_get(s->observed_calls,i),"id")))callback=i;
        if(!s->boundary||callback==RC_TOOL_MAX_CALLS){status=403;goto done;}
        if(s->callback_seen[callback]){status=409;goto done;}
    }
    json_t *text=json_object_get(event,"text"),*truncated=json_object_get(event,"text_truncated");
    bool metadata_only=!text&&!truncated;
    const char *text_keys=tool_event?"|tool_result|":"|assistant_plan||reasoning|";
    if(!metadata_only&&(!keys(text,text_keys)||!keys(truncated,text_keys)||!json_object_size(text)||json_object_size(text)!=json_object_size(truncated)))goto done;
    rc_interpreter_input in={.key=s->key,.revision=revision};const char *k;json_t *v;
    json_object_foreach(text,k,v){
        if(!json_is_string(v)||!json_string_length(v)||json_string_length(v)>1024||strlen(json_string_value(v))!=json_string_length(v)||!json_is_false(json_object_get(truncated,k)))goto done;
        rc_interpreter_evidence *e=&in.evidence[in.evidence_count++];strcpy(e->id,k);strcpy(e->source,tool_event?"executor":"model_claim");strcpy(e->text,json_string_value(v));
    }
    if(tool_event&&!metadata_only){
        rc_interpreter_evidence *e=&in.evidence[in.evidence_count++];
        strcpy(e->id,"tool_status");strcpy(e->source,"executor");strcpy(e->text,json_string_value(json_object_get(event,"status")));
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
    if(tool_event)s->callback_seen[callback]=true;
    s->revision=revision;s->sequence=sequence;s->observed=now;s->active=now;s->evidence_row=row;memset(&s->interpretation,0,sizeof s->interpretation);
    status=metadata_only?202:(rc_interpreter_try_submit(g->worker,&in)?202:503);
done:
    pthread_mutex_unlock(&g->lock);return status;
}
/* Only named, null optional fields are absent for continuity comparison.
 * Never mutate the caller's request or the forwarded response. */
static bool nullable_keys(json_t *o,const char *ordinary,const char *nullable) {
    if(!json_is_object(o))return false;
    const char *k;json_t *v;
    json_object_foreach(o,k,v){
        char b[128];
        if(!*k||strchr(k,'|')||snprintf(b,sizeof b,"|%s|",k)>=(int)sizeof b)return false;
        if(!strstr(ordinary,b)&&(!strstr(nullable,b)||!json_is_null(v)))return false;
    }
    return true;
}
static bool plain_message(json_t *m) {
    json_t *v=json_object_get(m,"content");
    const char *nullable=eq(m,"role","assistant")?"|refusal||annotations||audio||function_call|":"";
    return nullable_keys(m,"|role||content|",nullable)&&json_is_string(json_object_get(m,"role"))&&json_is_string(v)&&json_string_length(v)==strlen(json_string_value(v));
}
/* Legacy narrow subset: flat primitive object parameters. Anything else is a
 * nested schema, qualified only by requirement RC_REQ_NESTED_SCHEMAS. */
static bool flat_parameters(json_t *p) {
    if(!keys(p,"|type||properties||additionalProperties||required|")||!eq(p,"type","object")||
       !json_is_false(json_object_get(p,"additionalProperties")))return false;
    json_t *props=json_object_get(p,"properties"),*required=json_object_get(p,"required");
    if(!json_is_object(props)||json_object_size(props)>32)return false;
    const char *name;json_t *value;
    json_object_foreach(props,name,value){
        json_t *d=json_object_get(value,"description");
        if(!*name||strlen(name)>64||!keys(value,"|type||description|")||
           !(eq(value,"type","string")||eq(value,"type","integer")||eq(value,"type","number")||eq(value,"type","boolean"))||
           (d&&(!json_is_string(d)||json_string_length(d)>4096)))return false;
    }
    if(required){
        if(!json_is_array(required)||json_array_size(required)>32)return false;
        for(size_t i=0;i<json_array_size(required);i++){
            const char *key=json_string_value(json_array_get(required,i));
            if(!key||!json_object_get(props,key))return false;
            for(size_t j=0;j<i;j++)if(json_equal(json_array_get(required,i),json_array_get(required,j)))return false;
        }
    }
    return true;
}
/* Nested parameters are inert data forwarded verbatim (never executed,
 * resolved or rewritten); only structure is bounded: object root, depth
 * (root = 0) and node count. The caller bounds serialized bytes. */
static bool bounded_tree(json_t *v,unsigned depth,size_t *nodes) {
    if(depth>RC_SCHEMA_MAX_DEPTH||++*nodes>RC_SCHEMA_MAX_NODES)return false;
    if(json_is_object(v)){const char *k;json_t *c;json_object_foreach(v,k,c){(void)k;if(!bounded_tree(c,depth+1,nodes))return false;}}
    else if(json_is_array(v)){size_t i;json_t *c;json_array_foreach(v,i,c)if(!bounded_tree(c,depth+1,nodes))return false;}
    return true;
}
/* Function-definition contract; never strip unknown options. */
static bool tool_definitions(json_t *body,uint32_t *requirements) {
    json_t *tools=json_object_get(body,"tools"),*choice=json_object_get(body,"tool_choice"),*parallel=json_object_get(body,"parallel_tool_calls");
    if(!tools)return !choice&&!parallel;
    if(!json_is_array(tools)||!json_array_size(tools)||json_array_size(tools)>RC_TOOLS_MAX)return false;
    char *wire=json_dumps(tools,JSON_COMPACT);size_t bytes=wire?strlen(wire):SIZE_MAX;free(wire);
    if(bytes>RC_TOOLS_MAX_BYTES)return false;
    /* Beyond the legacy narrow profile (32 tools, 16 KiB, flat schemas) the
     * destination must declare nested_tool_schemas. */
    bool nested=json_array_size(tools)>32||bytes>16384;size_t nodes=0;
    for(size_t i=0;i<json_array_size(tools);i++){
        json_t *t=json_array_get(tools,i),*f=json_object_get(t,"function"),*p=json_object_get(f,"parameters"),*d=json_object_get(f,"description");
        const char *name=token(f,"name",64);
        if(!keys(t,"|type||function|")||!eq(t,"type","function")||!keys(f,"|name||description||parameters|")||!name||
           (d&&(!json_is_string(d)||json_string_length(d)>4096))||
           !json_is_object(p)||!bounded_tree(p,0,&nodes))return false;
        if(!flat_parameters(p))nested=true;
        for(size_t j=0;j<i;j++)if(eq(json_object_get(json_array_get(tools,j),"function"),"name",name))return false;
    }
    if(choice&&!eq(body,"tool_choice","auto")&&!eq(body,"tool_choice","none")&&!eq(body,"tool_choice","required")){
        json_t *f=json_object_get(choice,"function");const char *name=token(f,"name",64);bool found=false;
        if(!keys(choice,"|type||function|")||!eq(choice,"type","function")||!keys(f,"|name|")||!name)return false;
        for(size_t i=0;i<json_array_size(tools);i++)if(eq(json_object_get(json_array_get(tools,i),"function"),"name",name))found=true;
        if(!found)return false;
    }
    if(parallel&&!json_is_boolean(parallel))return false;
    *requirements|=RC_TOOL_CAP_FUNCTIONS;
    if(!json_is_false(parallel))*requirements|=RC_TOOL_CAP_PARALLEL;
    if(json_is_true(json_object_get(body,"stream")))*requirements|=RC_REQ_STREAM_TOOLS;
    if(nested)*requirements|=RC_REQ_NESTED_SCHEMAS;
    return true;
}
/* Output bound: exactly one of max_tokens or max_completion_tokens (the
 * OpenAI successor spelling that pinned Hermes sends), integer 1..100000.
 * Forwarded verbatim; neither spelling is rewritten. */
static bool output_bound(json_t *body,uint64_t *out) {
    json_t *a=json_object_get(body,"max_tokens"),*b=json_object_get(body,"max_completion_tokens");
    if(!!a==!!b)return false;
    json_t *v=a?a:b;
    if(!json_is_integer(v)||json_integer_value(v)<1||json_integer_value(v)>100000)return false;
    *out=(uint64_t)json_integer_value(v);return true;
}
/* effort receives the exact reasoning_effort token ("" when absent). */
static bool request_options(json_t *body,uint32_t *requirements,char effort[RC_EFFORT_BYTES+1]) {
    if(!keys(body,"|model||messages||max_tokens||max_completion_tokens||temperature||top_p||stream||stream_options||tools||tool_choice||parallel_tool_calls||reasoning_effort|"))return false;
    json_t *stream=json_object_get(body,"stream");if(stream&&!json_is_boolean(stream))return false;
    json_t *options=json_object_get(body,"stream_options");
    if(options&&(!json_is_true(stream)||!keys(options,"|include_usage|")||
                 !json_is_boolean(json_object_get(options,"include_usage"))))return false;
    effort[0]=0;
    if(json_object_get(body,"reasoning_effort")){
        const char *e=token(body,"reasoning_effort",RC_EFFORT_BYTES);if(!e)return false;
        strcpy(effort,e);
    }
    uint64_t output;if(!output_bound(body,&output))return false;
    const char *names[]={"temperature","top_p"};
    for(size_t i=0;i<2;i++){
        json_t *v=json_object_get(body,names[i]);double n=json_number_value(v);
        if(v&&(!json_is_number(v)||!isfinite(n)||n<0||n>(i?1:2)))return false;
    }
    return tool_definitions(body,requirements);
}
/* Exact contract projection (deep copies; nothing is normalized). Profile
 * scopes (tools or reasoning_effort) also bind stream_options; plain chat
 * keeps its pre-existing freedom to vary the usage option. NULL = OOM. */
static json_t *contract_projection(json_t *body) {
    json_t *p=json_object();if(!p)return NULL;
    bool profile=json_object_get(body,"tools")||json_object_get(body,"reasoning_effort");
    static const char *fields[]={"tools","tool_choice","parallel_tool_calls","reasoning_effort","stream_options"};
    for(size_t i=0;i<sizeof fields/sizeof *fields;i++){
        json_t *v=json_object_get(body,fields[i]);
        if(!v||(i==4&&!profile))continue;
        json_t *copy=json_deep_copy(v);
        if(!copy||json_object_set_new(p,fields[i],copy)){json_decref(p);return NULL;}
    }
    return p;
}
static bool candidate_effort(const struct rc_gateway_context *g,size_t i,const char *effort) {
    if(!effort[0])return true;
    for(size_t e=0;e<g->effort_count[i];e++)if(!strcmp(g->efforts[i][e],effort))return true;
    return false;
}
static bool replayable(struct scope *s,json_t *body) {
    json_t *messages=json_object_get(body,"messages");size_t n=json_array_size(messages),prior=json_array_size(s->history);
    if(!json_is_array(messages)||!n||n>RC_TOOL_MAX_MESSAGES||n<=prior)return false;
    for(size_t i=0;i<n;i++){
        json_t *m=json_array_get(messages,i);
        if(i<prior&&(s->requirements&RC_TOOL_CAP_HISTORY)){
            if(!json_equal(m,json_array_get(s->history,i)))return false;
            continue;
        }
        if(!plain_message(m))return false;
        if(i<prior){
            json_t *old=json_array_get(s->history,i);
            if(!plain_message(old)||!json_equal(json_object_get(m,"role"),json_object_get(old,"role"))||!json_equal(json_object_get(m,"content"),json_object_get(old,"content")))return false;
        }
        else if(!eq(m,"role","user") && !(i==0&&!s->owner&&eq(m,"role","system")))return false;
    }
    char *serialized=json_dumps(messages,JSON_COMPACT);if(!serialized)return false;
    bool bounded=strlen(serialized)<=RC_TOOL_MAX_BYTES;free(serialized);return bounded;
}
/* Conversation opening: every message up to and including the first user
 * message, hashed (FNV-1a) over its compact sorted serialization. start = no
 * assistant or tool message yet; first = that user message's text or NULL. */
static bool opening(json_t *messages,uint64_t *anchor,bool *start,const char **first) {
    size_t n=json_array_size(messages);
    if(!json_is_array(messages)||!n)return false;
    uint64_t hash=UINT64_C(14695981039346656037);bool user=false;*start=true;*first=NULL;
    for(size_t i=0;i<n;i++){
        json_t *m=json_array_get(messages,i);
        if(eq(m,"role","assistant")||eq(m,"role","tool"))*start=false;
        if(user)continue;
        char *wire=json_is_object(m)?json_dumps(m,JSON_COMPACT|JSON_SORT_KEYS):NULL;
        if(!wire)return false;
        for(const char *c=wire;*c;c++){hash^=(unsigned char)*c;hash*=UINT64_C(1099511628211);}
        free(wire);
        if(eq(m,"role","user")){user=true;*first=json_string_value(json_object_get(m,"content"));}
    }
    *anchor=hash;return true;
}
/* Does this request continue the session's last completed exchange? Exact for
 * live sessions (tool-boundary replay or history prefix); a pinned session
 * has no history left and only needs the conversation to have grown. */
static bool continues(const struct scope *s,json_t *messages,const char *wire,size_t length) {
    size_t n=json_array_size(messages),prior=json_array_size(s->history);
    if(s->pinned)return n>s->seen_messages;
    if(s->boundary)return rc_tool_boundary_replay(s->boundary,wire,length)==RC_TOOL_COMPLETE;
    if(!s->history||n<=prior)return false;
    for(size_t i=0;i<prior;i++)if(!json_equal(json_array_get(messages,i),json_array_get(s->history,i)))return false;
    return true;
}
static bool holds(json_t *v,const char *text,unsigned depth,size_t *nodes) {
    if(depth>8||++*nodes>512)return false;
    if(json_is_string(v))return !strcmp(json_string_value(v),text);
    if(json_is_object(v)){const char *k;json_t *c;json_object_foreach(v,k,c){(void)k;if(holds(c,text,depth+1,nodes))return true;}}
    else if(json_is_array(v)){size_t i;json_t *c;json_array_foreach(v,i,c)if(holds(c,text,depth+1,nodes))return true;}
    return false;
}
/* Request-stream lineage: a new conversation whose first user message equals
 * a string argument of a tool call that another open session is still waiting
 * on was handed out by that session (e.g. a delegate/task tool's goal).
 * Exact equality on a nontrivial string only; advisory like a harness hint. */
static bool handed_out(struct rc_gateway_context *g,const char *first) {
    bool found_any=false;
    if(!first||strlen(first)<16)return false;
    for(int i=0;i<SCOPES;i++){
        struct scope *s=&g->scopes[i];
        if(!s->open||!s->boundary)continue;
        for(size_t c=0;c<json_array_size(s->observed_calls);c++){
            json_t *a=json_object_get(json_object_get(json_array_get(s->observed_calls,c),"function"),"arguments");
            json_t *parsed=json_is_string(a)?json_loadb(json_string_value(a),json_string_length(a),JSON_REJECT_DUPLICATES,NULL):NULL;
            size_t nodes=0;bool found=parsed&&holds(parsed,first,0,&nodes);
            json_decref(parsed);if(found){s->awaiting_delegates=true;found_any=true;}
        }
    }
    return found_any;
}
/* Session for an unregistered automatic request. -1 = leave it unscoped (the
 * baseline, as before): nothing usable, the matching session is busy, or the
 * table is full of live sessions. Never rejects a request. */
static int implicit_scope(struct rc_gateway_context *g,json_t *body,const rc_gateway_headers *h,uint64_t now) {
    json_t *messages=json_object_get(body,"messages");uint64_t anchor;bool start;const char *first;
    if(!opening(messages,&anchor,&start,&first))return -1;
    const char *ident=(h->invocation.mask&2u)&&!h->invocation.invalid?h->invocation.values[1]:"";
    if(!start){
        char *wire=json_dumps(messages,JSON_COMPACT);if(!wire)return -1;
        size_t length=strlen(wire);int found=-1;
        for(int i=0;i<SCOPES;i++){
            struct scope *s=&g->scopes[i];
            if(!s->open||!s->implicit||s->anchor!=anchor||strcmp(s->ident,ident)||!continues(s,messages,wire,length))continue;
            /* Prefer an exact (unpinned) continuation, then the most recent. */
            if(found<0||(g->scopes[found].pinned&&!s->pinned)||(g->scopes[found].pinned==s->pinned&&s->active>g->scopes[found].active))found=i;
        }
        free(wire);
        if(found>=0)return g->scopes[found].inflight?-1:found;
    }
    int slot=-1;size_t used=0;
    for(int i=0;i<SCOPES;i++){
        if(!g->scopes[i].open){if(slot<0)slot=i;}
        else if(g->scopes[i].implicit)used++;
    }
    if(slot<0||used>=SCOPES-EXPLICIT_SCOPES){
        if((slot=scope_idle(g,now,true))<0)return -1;
        scope_reclaim(g,slot,now);
    }
    struct scope *s=&g->scopes[slot];
    s->open=s->implicit=true;s->active=now;s->anchor=anchor;strcpy(s->ident,ident);s->last_row=-1;s->evidence_row=-1;
    const char *lineage="none";
    if(start){
        for(size_t i=0;ident[0]&&i<HINTS;i++)
            if(g->hints[i].set&&!strcmp(g->hints[i].session,ident)&&now-g->hints[i].at<=HINT_TTL_MS&&g->hints[i].delegated){s->delegated=true;lineage="hint";}
        /* Always matched (also marks the orchestrator awaiting its delegates),
         * even when a hint already identified this session. */
        if(handed_out(g,first)&&!s->delegated){s->delegated=true;lineage="request";}
    }
    fprintf(stderr,"session scope=%d kind=request start=%d delegated=%d lineage=%s\n",slot,start,s->delegated,lineage);
    return slot;
}
/* M2 vetoed the destination this session would otherwise use. Cheapest
 * candidate that M2 permits for this exact request and that declares every
 * requirement of the session (in practice a private model); count = none. */
static size_t compliant_candidate(rc_runtime *rt,struct rc_gateway_context *g,const struct scope *s,json_t *body,uint32_t required,const char *effort,uint64_t tokens) {
    size_t best=g->count;double best_cost=0;
    for(size_t i=0;i<g->count;i++){
        rc_alias *a=&rt->config.aliases[g->candidates[i].alias_index];rc_endpoint ep=a->endpoint;
        if((g->cap_known[i]&required)!=required||(g->cap_supported[i]&required)!=required||!candidate_effort(g,i,effort)||
           g->candidates[i].context_limit<tokens||(s->private_only&&ep!=RC_ENDPOINT_PRIVATE))continue;
        json_t *probe=json_deep_copy(body);
        bool ok=probe&&!json_object_set_new(probe,"model",json_string(a->model))&&
            (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
        json_decref(probe);
        double cost=g->costs[i].priced?g->costs[i].price.input_per_mtok:g->costs[i].fixed;
        if(ok&&(best==g->count||cost<best_cost)){best=i;best_cost=cost;}
    }
    return best;
}
unsigned rc_gateway_prepare(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint *endpoint,rc_gateway_ticket *ticket) {
    struct rc_gateway_context *g=rt->gateway;ticket->scope=-1;ticket->row=-1;
    if(!g)return rc_dispatch_gate&&rc_dispatch_gate(rt,body,endpoint)?403:0;
    /* Optional judge, asked BEFORE the gateway lock (it blocks up to its
     * timeout). Only for automatic turns the deterministic signals leave
     * unclassified, and only when final M2 already permits public placement
     * of this exact request (the judge provider is public egress). */
    rc_judge_result judged={.ok=false};bool asked=false;
    if(g->judge.enabled&&automatic&&g->active){
        rc_signal_scope one={1};
        if(!rc_signals_classify(body,&one)&&!rc_signals_recent_failure(body)){
            json_t *probe=json_deep_copy(body);rc_alias *b=&rt->config.aliases[g->baseline];rc_endpoint ep=b->endpoint;
            bool pub=probe&&!json_object_set_new(probe,"model",json_string(b->model))&&
                (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==RC_ENDPOINT_PUBLIC;
            json_decref(probe);
            if(pub){judged=rc_judge_ask(&g->judge,body);asked=judged.attempted;}
        }
    }
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();unsigned status=0;struct scope *s=NULL;
    poll_locked(g,now);
    /* Capacity fence BEFORE selection: an unrecordable next request is a
     * windowed loss covering every row it could duplicate (see attempts.c). */
    int free_row=row_slot(g,now);
    if(free_row<0||!rc_attempt_capacity(g->ledger,now)||h->invocation.invalid||h->invocation.mask!=31)rc_attempt_lost_at(g->ledger,now);
    if(!h->generation[0]&&!h->branch[0]){
        /* Diagnostic identity is only a loss fence, never a fallback join.
         * Even a partial match may denote a registered workflow/branch. */
        for(size_t i=0;i<SCOPES;i++)if(g->scopes[i].open&&!g->scopes[i].implicit&&(!strcmp(g->scopes[i].task,h->invocation.values[0])||!strcmp(g->scopes[i].session,h->invocation.values[1]))){status=403;goto done;}
    }
    int slot=-1;
    if(h->generation[0]||h->branch[0]||h->invalid) {
        slot=scope_find(g,h->generation,h->branch);
        if(h->invalid||slot<0){status=403;goto done;}
        s=&g->scopes[slot];
        if(strcmp(s->task,h->invocation.values[0])||strcmp(s->session,h->invocation.values[1])){status=403;goto done;}
        if(s->inflight){status=409;goto done;}
    }
    else if(g->implicit&&automatic&&(slot=implicit_scope(g,body,h,now))>=0)s=&g->scopes[slot];
    if(s) {
        ticket->scope=slot;
        uint32_t required=s->requirements,own=0;char effort[RC_EFFORT_BYTES+1];
        bool options=request_options(body,&own,effort);
        if(s->implicit)s->seen_messages=json_array_size(json_object_get(body,"messages"));
        if(!options)s->pinned=true;
        else if(!s->pinned){
            /* Sticky contract: the first request fixes the projection. Once
             * the scope or this request carries a native profile feature
             * (streamed tools, nested/large tools, reasoning_effort), any
             * later difference, added or removed field pins permanently.
             * Legacy narrow scopes keep their pre-existing freedom. */
            bool profile=effort[0]||(own&(RC_REQ_STREAM_TOOLS|RC_REQ_NESTED_SCHEMAS));
            json_t *projection=contract_projection(body);
            if(!projection)s->pinned=true;
            else if(!s->contract){s->contract=projection;s->profile=profile;strcpy(s->effort,effort);}
            else{
                if((s->profile||profile)&&(!json_equal(projection,s->contract)||strcmp(effort,s->effort)))s->pinned=true;
                json_decref(projection);
            }
        }
        required|=own;
        if(!s->pinned&&s->boundary){
            char *wire=json_dumps(json_object_get(body,"messages"),JSON_COMPACT);
            rc_tool_status replay=wire?rc_tool_boundary_replay(s->boundary,wire,strlen(wire)):RC_TOOL_NOMEM;free(wire);
            if(replay==RC_TOOL_INCOMPLETE&&!s->implicit){status=409;goto done;}
            if(replay!=RC_TOOL_COMPLETE)s->pinned=true;
            required|=rc_tool_boundary_requirements(s->boundary);
        }else if(!s->pinned&&!replayable(s,body))s->pinned=true;
        s->requirements=required;
        if(automatic&&s->pinned&&s->owner){
            *endpoint=s->endpoint;if(json_object_set_new(body,"model",json_string(s->model))){status=500;goto done;}
            /* A pinned session is never moved, by M3 or by M2: if M2 vetoes
             * its owner for this request, the final gate below rejects. */
            if(g->signals)fprintf(stderr,"route_decision scope=%d mode=%s class=none reason=pin\n",ticket->scope,g->active?"active":"shadow");
        }
        else if(automatic) {
            rc_context_snapshot snapshot;bool usable=rc_context_get(g->contexts,&s->key,now,&snapshot)==RC_CONTEXT_OK&&snapshot.has_interpretation&&snapshot.revision==s->interpretation.revision&&exact(g,s->evidence_row,now)&&s->evidence_row==s->last_row;
            /* S4 structured signal: THIS request's facts, no interpreter wait.
             * Same replay/retry fences as interpreter advice; a pinned scope
             * never receives a class or escalation. */
            bool structural=g->signals&&!s->pinned;
            for(size_t i=0;i<g->rows_used;i++)if(g->rows[i].in_use&&same_headers(&h->invocation,&g->rows[i].headers))usable=structural=false;
            char *wire=json_dumps(body,JSON_COMPACT);uint64_t tokens=wire?strlen(wire):0;free(wire);
            /* Priced registries: ESTIMATED tokens (observed usage + appended
             * bytes/4, else request bytes/4). Legacy registries keep raw bytes. */
            uint64_t prompt_est=0,output_est=0,max_tokens=0;
            if(g->priced){
                json_t *messages=json_object_get(body,"messages");size_t n=json_array_size(messages);
                rc_usage_observation last=s->usage;uint64_t appended=0;
                if(!last.known||n<s->usage_messages)last.known=false;
                for(size_t i=last.known?s->usage_messages:n;i<n;i++){
                    char *m=json_dumps(json_array_get(messages,i),JSON_COMPACT);
                    if(!m){last.known=false;break;}appended+=strlen(m);free(m);
                }
                prompt_est=rc_estimate_prompt_tokens(&last,appended,tokens);tokens=prompt_est;
            }
            if(output_bound(body,&max_tokens)){tokens=tokens>UINT64_MAX-max_tokens?UINT64_MAX:tokens+max_tokens;}else usable=structural=false;
            output_est=rc_estimate_output_tokens(max_tokens,g->expected_output);
            uint64_t task=usable&&!strcmp(s->interpretation.next_action,"format_result")&&!strcmp(s->interpretation.difficulty_band,"simple")&&!strcmp(s->interpretation.coverage,"partial")?1:0;
            rc_signal_scope facts={.completed_turns=s->turns};
            uint64_t signal=structural?rc_signals_classify(body,&facts):0;
            uint64_t escalation=signal==RC_TASK_RECOVERY?RC_TASK_RECOVERY:0;if(escalation)signal=0;
            /* Judge advice only fills an unclassified structural turn; never
             * a pinned/private-only scope, recovery, or the first turn. */
            const char *judge_verdict=asked?(judged.ok?(rc_judge_routine(&g->judge,&judged)?"routine":"hard"):"unavailable"):NULL;
            if(asked&&structural&&!signal&&!escalation&&s->turns&&!s->private_only&&rc_judge_routine(&g->judge,&judged))signal=RC_TASK_TOOL_FOLLOWUP_OK;
            /* First turn of a delegated session (subagent): its own class,
             * used only by candidates the operator qualified for it. */
            if(structural&&!signal&&!escalation&&!s->turns&&s->delegated)signal=RC_TASK_DELEGATED_START;
            /* Integration/review step of an orchestrator: keep the baseline. */
            if(s->awaiting_delegates&&signal&&signal!=RC_TASK_DELEGATED_START){
                signal=0;fprintf(stderr,"route_hold scope=%d reason=delegate_results\n",ticket->scope);
            }
            if(asked)fprintf(stderr,"judge scope=%d verdict=%s routine=%.3f difficulty=%.3f ms=%u\n",ticket->scope,judge_verdict,judged.routine,judged.difficulty,judged.latency_ms);
            rc_selection_request req={.registry_version=1,.baseline_alias=g->baseline,.continuity=RC_CONTINUITY_REPLAYABLE,.context_usable=usable&&!s->pinned,.now=now,.context_observed_at=s->observed,.context_expires_at=usable?snapshot.expires_at:0,.task_class=task,.context_tokens=tokens?tokens:1,
                .signal_class=signal,.escalation_class=escalation};
            rc_candidate_quote quotes[RC_SELECTOR_MAX_CANDIDATES];bool baseline_permitted=false;
            for(size_t i=0;i<g->count;i++){
                quotes[i]=g->quotes[i];rc_alias *a=&rt->config.aliases[g->candidates[i].alias_index];
                if(g->priced){
                    /* Switching penalty: only the current owner keeps a
                     * measured warm prompt cache; every other model pays full
                     * uncached input. */
                    bool owner=s->owner&&s->usage.known&&a->endpoint==s->endpoint&&!strcmp(a->model,s->model)&&!strcmp(s->usage_model,s->model);
                    double c=rc_turn_cost(&g->costs[i].price,prompt_est,rc_cached_input_tokens(owner,&s->usage,prompt_est),output_est);
                    if(c<0){status=500;goto done;}
                    quotes[i].expected_task_cost=c;
                }
                json_t *probe=json_deep_copy(body);rc_endpoint ep=a->endpoint;
                if(!probe||json_object_set_new(probe,"model",json_string(a->model))){json_decref(probe);status=500;goto done;}
                quotes[i].permitted=(!s->private_only||ep==RC_ENDPOINT_PRIVATE)&&
                    (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
                if(g->candidates[i].alias_index==g->baseline)baseline_permitted=quotes[i].permitted;
                /* A destination must declare every scope requirement,
                 * including the exact reasoning_effort token. The baseline
                 * stays usable as owner without declarations. */
                else if((g->cap_known[i]&s->requirements)!=s->requirements||
                        (g->cap_supported[i]&s->requirements)!=s->requirements||
                        !candidate_effort(g,i,s->effort))quotes[i].permitted=false;
                json_decref(probe);
            }
            /* A baseline placement veto belongs to final M2, not to inferred
             * context. Do not ask the downshift selector to invent recovery. */
            rc_selection selected={.alias_index=g->baseline,.reason=RC_SELECT_BASELINE};
            /* Shadow proposal failure has no dispatch authority. Mandatory
             * scope continuity and final M2 below apply in either mode. */
            bool placed=false;
            if(baseline_permitted){if(rc_select(g->registry,quotes,g->count,&req,&selected)!=RC_SELECT_OK&&g->active){status=403;goto done;}}
            else {
                /* M2 vetoes the baseline for this exact request: place it on a
                 * permitted candidate that can continue the session instead of
                 * leaving the final gate to reject a mid-session redirect. */
                size_t to=compliant_candidate(rt,g,s,body,s->requirements,s->effort,tokens);
                if(to<g->count){selected.alias_index=g->candidates[to].alias_index;placed=true;}
            }
            if(g->priced||g->signals){
                /* Evidence only: class names, aliases, estimated tokens and
                 * USD. No content. Classes offered: interpreter [+signal]. */
                static const char *reasons[]={"baseline","cheapest","pin","escalate"};
                uint64_t offered=(req.context_usable?task:0)|signal|escalation;char classes[96]="";
                for(uint64_t bit=1;bit<=RC_TASK_DELEGATED_START;bit<<=1)if(offered&bit){
                    size_t n=strlen(classes);snprintf(classes+n,sizeof classes-n,"%s%s",n?"+":"",rc_task_name(bit));
                }
                char line[4096];int used=snprintf(line,sizeof line,"route_decision scope=%d mode=%s class=%s reason=%s chosen=%s est_prompt=%llu est_out=%llu costs=",
                    ticket->scope,g->active?"active":"shadow",classes[0]?classes:"none",placed?"compliance":reasons[selected.reason],rt->config.aliases[selected.alias_index].from,(unsigned long long)prompt_est,(unsigned long long)output_est);
                for(size_t i=0;i<g->count&&used>0&&(size_t)used<sizeof line;i++)
                    used+=snprintf(line+used,sizeof line-(size_t)used,"%s%s:%.9g%s",i?",":"",rt->config.aliases[g->candidates[i].alias_index].from,quotes[i].expected_task_cost,quotes[i].permitted?"":"(denied)");
                fprintf(stderr,"%s\n",line);
            }
            if(g->active){rc_alias *a=&rt->config.aliases[selected.alias_index];*endpoint=a->endpoint;if(json_object_set_new(body,"model",json_string(a->model))){status=500;goto done;}}
        }
    }
    /* Explicit scoped aliases are never silently retargeted by authority.
     * Run final M2, then reject a conflict instead of changing the alias. */
    rc_endpoint requested_endpoint=*endpoint;char requested_model[129]={0};
    if(s){
        const char *requested=json_string_value(json_object_get(body,"model"));
        if(!requested||strlen(requested)>128){status=403;goto done;}
        strcpy(requested_model,requested);
    }
    if(s&&s->private_only){
        if(!automatic){if(*endpoint!=RC_ENDPOINT_PRIVATE){status=403;goto done;}}
        else {
            *endpoint=RC_ENDPOINT_PRIVATE;
            if(json_object_set_new(body,"model",json_string(rt->config.private_model))){status=500;goto done;}
        }
    }
    if(rc_dispatch_gate&&rc_dispatch_gate(rt,body,endpoint)){status=403;goto done;}
    const char *model=json_string_value(json_object_get(body,"model"));
    if(s){
        if(!model||strlen(model)>128){status=403;goto done;}
        if((!automatic||(s->requirements&&s->owner))&&(*endpoint!=requested_endpoint||strcmp(model,requested_model))){status=403;goto done;}
        if(!automatic&&s->requirements&&s->owner&&(*endpoint!=s->endpoint||strcmp(model,s->model))){status=403;goto done;}
        if(s->pinned&&s->owner&&(*endpoint!=s->endpoint||strcmp(model,s->model))){status=403;goto done;}
        s->endpoint=*endpoint;strcpy(s->model,model);s->owner=true;s->inflight=true;s->active=now;s->awaiting_delegates=false;
        rc_tool_boundary_free(s->boundary);s->boundary=NULL;
        json_decref(s->observed_calls);s->observed_calls=NULL;memset(s->callback_seen,0,sizeof s->callback_seen);
        if(s->pinned){json_decref(s->history);s->history=NULL;}
        else {
            s->pending=json_deep_copy(json_object_get(body,"messages"));
            s->request_messages=json_array_size(json_object_get(body,"messages"));
            json_t *tools=json_object_get(body,"tools");
            s->pending_tools=tools?json_deep_copy(tools):NULL;
            json_t *choice=json_object_get(body,"tool_choice");
            s->pending_choice=choice?json_deep_copy(choice):NULL;
            if(choice&&!s->pending_choice)s->pinned=true;
            s->pending_parallel=!json_is_false(json_object_get(body,"parallel_tool_calls"));
            if(!s->pending||(tools&&!s->pending_tools))s->pinned=true;
        }
    }
    rc_attempt_result recorded=rc_attempt_begin(g->ledger,g->authorization,&h->invocation,now,&ticket->id);ticket->begun=true;
    if(recorded==RC_ATTEMPT_TRACKED&&free_row>=0){
        ticket->row=free_row;g->rows[free_row]=(struct physical){.headers=h->invocation,.id=ticket->id,.scope=ticket->scope,.in_use=true,.begun=now};
        if((size_t)free_row>=g->rows_used)g->rows_used=(size_t)free_row+1;
    }else if(recorded==RC_ATTEMPT_TRACKED)rc_attempt_lost_at(g->ledger,now);
    if(s)s->last_row=ticket->row;
done:
    pthread_mutex_unlock(&g->lock);return status;
}
static bool counters(json_t *o,const char *allowed) {
    if(!keys(o,allowed))return false;
    const char *k;json_t *v;
    json_object_foreach(o,k,v){(void)k;if(!json_is_integer(v)||json_integer_value(v)<0)return false;}
    return true;
}
static bool tool_envelope(json_t *root,json_t *choice) {
    json_t *index=json_object_get(choice,"index"),*created=json_object_get(root,"created"),*usage=json_object_get(root,"usage");
    if(!json_is_integer(index)||json_integer_value(index)!=0)return false;
    if(json_object_get(root,"id")&&!token(root,"id",128))return false;
    if(json_object_get(root,"model")&&!token(root,"model",128))return false;
    if(json_object_get(root,"object")&&!eq(root,"object","chat.completion"))return false;
    if(created&&(!json_is_integer(created)||json_integer_value(created)<0))return false;
    if(!usage||json_is_null(usage))return true;
    if(!keys(usage,"|prompt_tokens||completion_tokens||total_tokens||prompt_tokens_details||completion_tokens_details|"))return false;
    const char *names[]={"prompt_tokens","completion_tokens","total_tokens"};
    for(size_t i=0;i<3;i++){json_t *v=json_object_get(usage,names[i]);if(!json_is_integer(v)||json_integer_value(v)<0)return false;}
    json_t *p=json_object_get(usage,"prompt_tokens_details"),*c=json_object_get(usage,"completion_tokens_details");
    return (!p||json_is_null(p)||counters(p,"|cached_tokens||audio_tokens|"))&&
        (!c||json_is_null(c)||counters(c,"|reasoning_tokens||audio_tokens||accepted_prediction_tokens||rejected_prediction_tokens|"));
}
void rc_gateway_finish(rc_runtime *rt,rc_gateway_ticket *ticket,bool complete,bool sse,const char *response,size_t length,const rc_response_observer *observer) {
    struct rc_gateway_context *g=rt->gateway;if(!g||!ticket->begun||ticket->finished)return;
    pthread_mutex_lock(&g->lock);
    if(ticket->finished){pthread_mutex_unlock(&g->lock);return;}
    ticket->finished=true;uint64_t now=now_ms();
    rc_attempt_finish(g->ledger,ticket->id,complete,now);
    if(ticket->row>=0){g->rows[ticket->row].complete=complete;g->rows[ticket->row].settled=true;}
    if(ticket->scope>=0){
        struct scope *s=&g->scopes[ticket->scope];s->inflight=false;s->active=now;
        if(complete&&s->turns<UINT64_MAX)s->turns++;
        json_error_t error;json_t *root=complete&&!sse&&response&&length?json_loadb(response,length,JSON_REJECT_DUPLICATES,&error):NULL;
        json_t *choices=json_object_get(root,"choices"),*choice=json_array_get(choices,0),*message=json_object_get(choice,"message");
        json_t *fingerprint=json_object_get(root,"system_fingerprint"),*stop=json_object_get(choice,"stop_reason");
        bool safe=nullable_keys(root,"|id||object||created||model||choices||usage||system_fingerprint|",
                                "|service_tier||prompt_logprobs||prompt_token_ids||prompt_text||kv_transfer_params||ec_transfer_params||metrics|")&&
            (!fingerprint||json_is_string(fingerprint))&&json_array_size(choices)==1&&
            nullable_keys(choice,"|index||message||finish_reason||stop_reason|","|logprobs||token_ids||routed_experts|")&&
            (!stop||(json_is_integer(stop)&&json_integer_value(stop)>=0));
        if(s->requirements)safe=safe&&tool_envelope(root,choice);
        /* Cost evidence only (never continuity authority). Nonstream: root
         * usage. Stream: the observer's validated usage tail. */
        json_t *usage=json_object_get(root,"usage"),*details=json_object_get(usage,"prompt_tokens_details");
        json_t *pt=json_object_get(usage,"prompt_tokens"),*ct=json_object_get(usage,"completion_tokens"),*cached=json_object_get(details,"cached_tokens");
        memset(&s->usage,0,sizeof s->usage);s->usage_messages=0;s->usage_model[0]=0;
        if(sse&&complete&&observer&&observer->usage_known&&!observer->failed&&observer->done&&s->request_messages&&!s->pinned){
            s->usage=(rc_usage_observation){.known=true,.prompt_tokens=(uint64_t)observer->usage_prompt,
                .completion_tokens=(uint64_t)observer->usage_completion,.cached_tokens=(uint64_t)observer->usage_cached};
            s->usage_messages=s->request_messages+1;strcpy(s->usage_model,s->model);
        }else if(json_is_integer(pt)&&json_integer_value(pt)>=0&&json_is_integer(ct)&&json_integer_value(ct)>=0&&
           (!cached||(json_is_integer(cached)&&json_integer_value(cached)>=0&&json_integer_value(cached)<=json_integer_value(pt)))&&
           s->request_messages&&!s->pinned){
            s->usage=(rc_usage_observation){.known=true,.prompt_tokens=(uint64_t)json_integer_value(pt),
                .completion_tokens=(uint64_t)json_integer_value(ct),.cached_tokens=cached?(uint64_t)json_integer_value(cached):0};
            s->usage_messages=s->request_messages+1;strcpy(s->usage_model,s->model);
        }
        json_t *stream_message=complete&&sse?rc_response_observer_message(observer):NULL;
        bool tool_response=safe&&eq(choice,"finish_reason","tool_calls")&&tool_envelope(root,choice);
        if(sse){
            message=stream_message;
            safe=message!=NULL;
            tool_response=safe&&json_object_get(message,"tool_calls")!=NULL;
        }
        bool tool=tool_response&&!s->pinned&&s->pending&&s->pending_tools;
        if(tool){
            json_t *calls=json_object_get(message,"tool_calls");
            tool=json_array_size(calls)>0&&(s->pending_parallel||json_array_size(calls)==1)&&
                !(json_is_string(s->pending_choice)&&!strcmp(json_string_value(s->pending_choice),"none"));
            for(size_t i=0;tool&&i<json_array_size(calls);i++){
                const char *name=token(json_object_get(json_array_get(calls,i),"function"),"name",64);bool found=false;
                for(size_t j=0;name&&j<json_array_size(s->pending_tools);j++)
                    if(eq(json_object_get(json_array_get(s->pending_tools,j),"function"),"name",name))found=true;
                if(!found)tool=false;
                if(json_is_object(s->pending_choice)&&(!name||!eq(json_object_get(s->pending_choice,"function"),"name",name)))tool=false;
            }
            char *history=tool?json_dumps(s->pending,JSON_COMPACT):NULL,*assistant=tool?json_dumps(message,JSON_COMPACT):NULL;
            tool=history&&assistant&&rc_tool_boundary_capture(history,strlen(history),assistant,strlen(assistant),&s->boundary)==RC_TOOL_COMPLETE;
            free(history);free(assistant);
            if(tool){
                s->requirements|=rc_tool_boundary_requirements(s->boundary);
                s->observed_calls=json_deep_copy(calls);
                if(!s->observed_calls){tool=false;rc_tool_boundary_free(s->boundary);s->boundary=NULL;}
            }
        }
        /* A failed tool capture must never fall through as plain history. */
        safe=safe&&!tool_response&&(sse||eq(choice,"finish_reason","stop"))&&
            plain_message(message)&&eq(message,"role","assistant");
        if(!tool&&(!safe||!s->pending||json_array_append(s->pending,message)))s->pinned=true;
        if(!s->pinned&&!tool){json_decref(s->history);s->history=s->pending;s->pending=NULL;}
        json_decref(s->pending_choice);s->pending_choice=NULL;
        json_decref(s->pending_tools);s->pending_tools=NULL;
        json_decref(s->pending);s->pending=NULL;json_decref(root);json_decref(stream_message);
    }
    ticket->begun=false;pthread_mutex_unlock(&g->lock);
}
