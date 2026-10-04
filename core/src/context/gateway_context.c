#define _POSIX_C_SOURCE 200809L
#include "recursant/tool_boundary.h"
#include "recursant/gateway_context.h"
#include "recursant/selector.h"
#include "recursant/interpreter.h"
#include "recursant/cost.h"
#include "recursant/signals.h"
#include "recursant/judge.h"
#include "recursant/efficiency.h"
#include "recursant/prompt.h"
#include "recursant/classifier.h"
#include <strings.h>
#include <time.h>
#include <pthread.h>
#include <sys/random.h>
#include <math.h>
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Registered (header) scopes keep their original cap; the rest of the table
 * holds request-stream sessions, which are never registered or closed. */
#define EXPLICIT_SCOPES 32
#define SCOPES 160
#define HINTS 64
#define HINT_TTL_MS 600000u
/* Harness data labels ("restricted" sessions). Never expire or get evicted:
 * a full table refuses new labels (503) instead of forgetting an old one. */
#define LABELS 256
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
#define HOUSEKEEPING_MARKERS 8u
#define HOUSEKEEPING_MARKER_BYTES 256u
#define JUDGE_BREAKER_FAILURES 3u
/* Pinned Hermes (fb67154): agent/title_generator.py _TITLE_PROMPT_TEMPLATE
 * (system message) and agent/context_compressor.py _build_summary_prompt
 * (single user message). */
static const char *const hermes_markers[]={"You name chat sessions.","You are a summarization agent creating a context checkpoint."};
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
    /* A provider reported a context overflow on a candidate with this
     * context_limit: later turns need a larger window. */
    uint64_t context_floor;
    /* Reasoning field family the router added to the current request (0 =
     * none); removed again if the request fails over. */
    int reasoning_added;
    /* context.budgets: spend (USD) and dispatches in this session. */
    double spent;uint64_t requests;
};
/* Advisory harness telemetry: session -> role. Bounded, expiring, never
 * continuity or placement authority. */
struct hint {char session[RC_ATTEMPT_TOKEN_SIZE];uint64_t at;bool delegated,set;};
/* Mirror row slots never move: scopes and tickets hold indices. A slot is only
 * freed when settled, expired, not referenced by any open scope, and no live
 * row shares its full key (same tombstone horizon as the ledger). */
struct physical {rc_attempt_headers headers;rc_attempt_id id;int scope;bool complete,in_use,settled;uint64_t begun;};
struct outcome {uint64_t window,requests,failures,until;};
enum {EFFORT_NONE,EFFORT_OPENAI,EFFORT_OPENROUTER,EFFORT_VLLM_THINKING};
enum {REASONING_OFF,REASONING_SIGNALS,REASONING_STEPS};
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
    bool drop_reasoning; /* context.reasoning_text "drop" (default "pin") */
    struct hint hints[HINTS];
    struct {char session[RC_ATTEMPT_TOKEN_SIZE];bool set;} labels[LABELS];
    uint32_t cap_known[RC_SELECTOR_MAX_CANDIDATES], cap_supported[RC_SELECTOR_MAX_CANDIDATES];
    /* Capacity-aware placement: candidate max_inflight (0 = unlimited) and the
     * requests currently running on that candidate's model through this router.
     * A full candidate is not offered for cost routing; compliance placement
     * ignores it (private data waits for the private model rather than going
     * public). */
    uint64_t max_inflight[RC_SELECTOR_MAX_CANDIDATES], inflight[RC_SELECTOR_MAX_CANDIDATES];
    /* context.health (absent = off): per-candidate outcomes in a 60 s window
     * and a cooldown deadline. A cooling candidate is not offered for cost
     * routing and an automatic request is moved off it before dispatch or
     * after a failure that reached no client byte (rc_gateway_failover).
     * Never moves a pinned session and never crosses final M2. */
    struct {bool on;uint64_t cooldown_ms,min_requests,max_retries;double ratio;} health;
    struct outcome outcome[RC_SELECTOR_MAX_CANDIDATES];
    /* context.reasoning (default "off"). "signals": a downshifted step asks its
     * destination for the candidate's low effort, an escalated step for its
     * high effort, in the family's own field; never overrides the harness.
     * "steps": every session step on a candidate with a reasoning table gets
     * low on a routine step (the signals classed it tool_followup_ok,
     * final_answer or simple_prompt) and high otherwise (first step,
     * recovery, unclassified), whichever candidate serves it. The operator
     * hands effort to the router: for the openai/openrouter families the
     * harness's reasoning_effort/reasoning fields are replaced. */
    int reasoning;
    bool repeat; /* context.repeat_escalation "on": signals' repeat-loop rule */
    bool phase;  /* context.phase "on": signals' phase rule (read -> baseline) */
    /* context.budgets. Per session: spend from provider usage x the served
     * candidate's price (priced registries); from downshift_at x session_usd
     * cost routing takes the cheapest permitted candidate; at session_usd
     * only zero-price candidates, else 429. Request caps per session and per
     * minute (single client key). Final M2 decides "permitted" as always. */
    struct {double session_usd,downshift_at;uint64_t session_requests,rpm;} budget;
    uint64_t rpm_window,rpm_count;
    bool quiet_headers; /* context.decision_headers "off" */
    /* context.shadow: deterministic sample of eligible routed steps copied to
     * one candidate off the hot path (paired outcome labels for M4). Spend
     * from the shadow's usage x its price, capped at usd_cap. */
    struct {bool on,capped;size_t candidate;double sample,usd_cap,acc,spent;uint64_t max_inflight,inflight;} shadow;
    uint64_t decisions;  /* decision id counter */
    struct {int family;char low[RC_EFFORT_BYTES+1],high[RC_EFFORT_BYTES+1];} efforts_by_signal[RC_SELECTOR_MAX_CANDIDATES];
    /* context.housekeeping: harness auxiliary calls (session titles,
     * compaction summaries) recognised by the opening of their first message
     * and sent to one candidate, without a session. */
    bool housekeeping;size_t housekeeping_candidate;size_t marker_count;char markers[HOUSEKEEPING_MARKERS][HOUSEKEEPING_MARKER_BYTES+1];
    /* Judge circuit breaker: JUDGE_BREAKER_FAILURES consecutive unusable
     * answers stop asking for judge.breaker_ms (default 30 s). */
    uint64_t judge_breaker_ms,judge_open_until;unsigned judge_failures;
    char efforts[RC_SELECTOR_MAX_CANDIDATES][RC_EFFORT_MAX][RC_EFFORT_BYTES+1];size_t effort_count[RC_SELECTOR_MAX_CANDIDATES];
    rc_candidate_registry *registry;
    struct scope scopes[SCOPES];
    rc_config auth_config;rc_auth_table auth;char *authorization;
    rc_attempt_ledger *ledger;size_t rows_used;
    struct physical rows[RC_ATTEMPT_MAX_ROWS];
    rc_context_registry *contexts;rc_interpreter *worker;
    /* Optional synchronous per-turn judge (context.judge). Advisory only. */
    rc_judge_config judge;
    /* Optional efficiency model (context.efficiency). Advisory only, local. */
    rc_efficiency_config efficiency;
    /* Optional prompt classifier (context.prompt): fresh user questions. */
    rc_prompt_config prompt;
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
    if(!keys(o,"|mode||tenant||project||auto_alias||baseline_alias||ttl_ms||attempt_ttl_ms||expected_output_tokens||signals||sessions||reasoning_text||reasoning||repeat_escalation||phase||judge||efficiency||prompt||health||housekeeping||budgets||decision_headers||shadow||candidates||source_key_env|") ||
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
    if(json_object_get(o,"reasoning_text")&&!eq(o,"reasoning_text","drop")&&!eq(o,"reasoning_text","pin"))return false;
    g->drop_reasoning=eq(o,"reasoning_text","drop");
    if(json_object_get(o,"reasoning")&&!eq(o,"reasoning","signals")&&!eq(o,"reasoning","steps")&&!eq(o,"reasoning","off"))return false;
    g->reasoning=eq(o,"reasoning","signals")?REASONING_SIGNALS:eq(o,"reasoning","steps")?REASONING_STEPS:REASONING_OFF;
    if(g->reasoning&&!g->signals)return false;
    if(json_object_get(o,"repeat_escalation")&&!eq(o,"repeat_escalation","on")&&!eq(o,"repeat_escalation","off"))return false;
    g->repeat=eq(o,"repeat_escalation","on");
    if(json_object_get(o,"phase")&&!eq(o,"phase","on")&&!eq(o,"phase","off"))return false;
    g->phase=eq(o,"phase","on");
    if(g->phase&&!g->signals)return false;
    if(json_object_get(o,"decision_headers")&&!eq(o,"decision_headers","on")&&!eq(o,"decision_headers","off"))return false;
    g->quiet_headers=eq(o,"decision_headers","off");
    if(g->repeat&&!g->signals)return false;
    json_t *health=json_object_get(o,"health");
    if(health){
        json_t *ratio=json_object_get(health,"failure_ratio"),*retries=json_object_get(health,"max_retries");
        g->health.on=true;g->health.cooldown_ms=5000;g->health.min_requests=5;g->health.max_retries=2;g->health.ratio=0.5;
        if(!keys(health,"|cooldown_ms||failure_ratio||min_requests||max_retries|")||
           (json_object_get(health,"cooldown_ms")&&!integer(health,"cooldown_ms",600000,&g->health.cooldown_ms))||
           (json_object_get(health,"min_requests")&&!integer(health,"min_requests",1000,&g->health.min_requests))||
           (ratio&&(!json_is_number(ratio)||json_number_value(ratio)<=0||json_number_value(ratio)>1))||
           (retries&&(!json_is_integer(retries)||json_integer_value(retries)<0||json_integer_value(retries)>4)))return false;
        if(ratio)g->health.ratio=json_number_value(ratio);
        if(retries)g->health.max_retries=(uint64_t)json_integer_value(retries);
    }
    /* context.judge: {provider, model, url, timeout_ms, routine_min,
     * difficulty_max}. Public-trust provider (its resolved key is borrowed);
     * requires signals on. Absent = off. */
    json_t *judge=json_object_get(o,"judge");
    if(judge){
        const char *provider=token(judge,"provider",63),*jmodel=token(judge,"model",128);
        json_t *url=json_object_get(judge,"url"),*t=json_object_get(judge,"timeout_ms"),*rm=json_object_get(judge,"routine_min"),*dm=json_object_get(judge,"difficulty_max");
        json_t *breaker=json_object_get(judge,"breaker_ms");g->judge_breaker_ms=30000;
        if(breaker&&(!integer(judge,"breaker_ms",600000,&g->judge_breaker_ms)||g->judge_breaker_ms<100))return false;
        if(!keys(judge,"|provider||model||url||timeout_ms||routine_min||difficulty_max||breaker_ms|")||!provider||!jmodel||!g->signals||
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
    /* context.efficiency: {weights, downshift_min, veto_below}. Requires
     * signals on. Absent = off. */
    json_t *efficiency=json_object_get(o,"efficiency");
    if(efficiency&&(!g->signals||!rc_efficiency_configure(efficiency,&g->efficiency)))return false;
    /* context.prompt: {weights, vocab, simple_min[, agent_turns]}. Requires
     * signals on. Absent = off. */
    json_t *prompt=json_object_get(o,"prompt");
    if(prompt&&(!g->signals||!rc_prompt_configure(prompt,&g->prompt)))return false;
    if(!strcmp(automatic,rt->config.private_model)||(rt->config.public_model&&!strcmp(automatic,rt->config.public_model)))return false;
    for(size_t i=0;i<rt->config.alias_count;i++)if(!strcmp(automatic,rt->config.aliases[i].from)||!strcmp(automatic,rt->config.aliases[i].model))return false;
    json_t *list=json_object_get(o,"candidates");g->count=json_array_size(list);
    if(!json_is_array(list)||!g->count||g->count>RC_SELECTOR_MAX_CANDIDATES)return false;
    bool found=false;
    for(size_t i=0;i<g->count;i++) {
        json_t *v=json_array_get(list,i);const char *a=token(v,"alias",128);
        if(!keys(v,"|alias||quality_evidence||qualified_tasks||escalation||context_limit||expected_task_cost||price||capabilities||max_inflight||reasoning|")||!a||!token(v,"quality_evidence",128)||!alias(rt,a,&g->candidates[i].alias_index)||!integer(v,"context_limit",100000000,&g->candidates[i].context_limit))return false;
        if(json_object_get(v,"max_inflight")&&!integer(v,"max_inflight",1024,&g->max_inflight[i]))return false;
        /* reasoning: {family, low, high}. "vllm-thinking" (private only) sets
         * chat_template_kwargs.enable_thinking; "openai" reasoning_effort;
         * "openrouter" reasoning.effort, with at least one token. */
        json_t *effort=json_object_get(v,"reasoning");
        if(effort){
            const char *family=token(effort,"family",32);int f=EFFORT_NONE;
            if(family&&!strcmp(family,"openai"))f=EFFORT_OPENAI;
            else if(family&&!strcmp(family,"openrouter"))f=EFFORT_OPENROUTER;
            else if(family&&!strcmp(family,"vllm-thinking"))f=EFFORT_VLLM_THINKING;
            if(!f)return false;
            g->efforts_by_signal[i].family=f;
            if(f==EFFORT_VLLM_THINKING){
                /* Thinking switch: "low"/"high" are "on" or "off". Defaults:
                 * low "off" (routine steps answer faster without thinking),
                 * high "on" (recovery steps think). */
                if(!keys(effort,"|family||low||high|")||rt->config.aliases[g->candidates[i].alias_index].endpoint!=RC_ENDPOINT_PRIVATE)return false;
                static const char *const sides[2]={"low","high"};
                for(int k=0;k<2;k++){
                    json_t *v=json_object_get(effort,sides[k]);const char *t=json_string_value(v);
                    if(v&&(!t||(strcmp(t,"on")&&strcmp(t,"off"))))return false;
                    strcpy(k?g->efforts_by_signal[i].high:g->efforts_by_signal[i].low,t?t:(k?"on":"off"));
                }
            }else{
                if(!keys(effort,"|family||low||high|"))return false;
                const char *low=token(effort,"low",RC_EFFORT_BYTES),*high=token(effort,"high",RC_EFFORT_BYTES);
                if((json_object_get(effort,"low")&&!low)||(json_object_get(effort,"high")&&!high)||(!low&&!high))return false;
                if(low)strcpy(g->efforts_by_signal[i].low,low);
                if(high)strcpy(g->efforts_by_signal[i].high,high);
            }
        }
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
        json_t *tasks=json_object_get(v,"qualified_tasks");if(!json_is_array(tasks)||json_array_size(tasks)>5)return false;
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
    json_t *budgets=json_object_get(o,"budgets");
    if(budgets){
        json_t *usd=json_object_get(budgets,"session_usd"),*at=json_object_get(budgets,"downshift_at");
        if(!keys(budgets,"|session_usd||downshift_at||session_requests||requests_per_minute|")||
           (usd&&(!json_is_number(usd)||!(json_number_value(usd)>0)||json_number_value(usd)>1e6||!g->priced))||
           (at&&(!usd||!json_is_number(at)||!(json_number_value(at)>0)||json_number_value(at)>1))||
           (json_object_get(budgets,"session_requests")&&!integer(budgets,"session_requests",1000000,&g->budget.session_requests))||
           (json_object_get(budgets,"requests_per_minute")&&!integer(budgets,"requests_per_minute",1000000,&g->budget.rpm)))return false;
        g->budget.session_usd=usd?json_number_value(usd):0;g->budget.downshift_at=at?json_number_value(at):0.8;
    }
    json_t *shadow=json_object_get(o,"shadow");
    if(shadow){
        const char *a=token(shadow,"alias",128);json_t *sample=json_object_get(shadow,"sample"),*cap=json_object_get(shadow,"usd_cap");size_t index;
        g->shadow.max_inflight=2;
        if(!keys(shadow,"|alias||sample||usd_cap||max_inflight|")||!a||!alias(rt,a,&index)||!g->priced||
           !json_is_number(sample)||!(json_number_value(sample)>0)||json_number_value(sample)>1||
           !json_is_number(cap)||!(json_number_value(cap)>0)||json_number_value(cap)>1e6||
           (json_object_get(shadow,"max_inflight")&&!integer(shadow,"max_inflight",64,&g->shadow.max_inflight)))return false;
        for(g->shadow.candidate=0;g->shadow.candidate<g->count&&g->candidates[g->shadow.candidate].alias_index!=index;g->shadow.candidate++);
        if(g->shadow.candidate==g->count)return false;
        g->shadow.on=true;g->shadow.sample=json_number_value(sample);g->shadow.usd_cap=json_number_value(cap);
    }
    json_t *hk=json_object_get(o,"housekeeping");
    if(hk){
        const char *a=token(hk,"alias",128);json_t *markers=json_object_get(hk,"markers");size_t index;
        if(!keys(hk,"|alias||markers|")||!a||!alias(rt,a,&index))return false;
        for(g->housekeeping_candidate=0;g->housekeeping_candidate<g->count&&g->candidates[g->housekeeping_candidate].alias_index!=index;g->housekeeping_candidate++);
        if(g->housekeeping_candidate==g->count)return false;
        if(markers){
            if(!json_is_array(markers)||!json_array_size(markers)||json_array_size(markers)>HOUSEKEEPING_MARKERS)return false;
            for(size_t m=0;m<json_array_size(markers);m++){
                json_t *v=json_array_get(markers,m);
                if(!json_is_string(v)||!json_string_length(v)||json_string_length(v)>HOUSEKEEPING_MARKER_BYTES||json_string_length(v)!=strlen(json_string_value(v)))return false;
                strcpy(g->markers[g->marker_count++],json_string_value(v));
            }
        }else for(size_t m=0;m<sizeof hermes_markers/sizeof *hermes_markers;m++)strcpy(g->markers[g->marker_count++],hermes_markers[m]);
        g->housekeeping=true;
    }
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
    rc_prompt_destroy(&g->prompt);free(g->authorization);rc_candidates_destroy(g->registry);pthread_mutex_destroy(&g->lock);free(g);rt->gateway=NULL;
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
        /* The harness names a session and, optionally, its role and a data
         * label. A role is advisory: "leaf" marks a delegated subagent, which
         * can make a first turn eligible for a class the operator qualified.
         * A data label is compliance input and only ever restricts: "restricted"
         * keeps the session on private inference from now on, for good. */
        const char *session=token(body,"session_id",RC_ATTEMPT_TOKEN_SIZE-1);
        json_t *role=json_object_get(body,"role"),*data=json_object_get(body,"data");
        bool leaf=eq(body,"role","leaf"),restricted=eq(body,"data","restricted");
        if(!g->implicit)return 404;
        if(!keys(body,"|session_id||role||parent_session_id||data|")||!session||(!role&&!data)||
           (role&&!leaf&&!eq(body,"role","orchestrator"))||(data&&!restricted)||
           (json_object_get(body,"parent_session_id")&&!token(body,"parent_session_id",RC_ATTEMPT_TOKEN_SIZE-1)))return 400;
        pthread_mutex_lock(&g->lock);uint64_t now=now_ms();
        if(restricted){
            size_t free_label=LABELS;bool known=false;
            for(size_t i=0;i<LABELS&&!known;i++){
                if(g->labels[i].set&&!strcmp(g->labels[i].session,session))known=true;
                else if(!g->labels[i].set&&free_label==LABELS)free_label=i;
            }
            if(!known){
                if(free_label==LABELS){pthread_mutex_unlock(&g->lock);return 503;}
                g->labels[free_label].set=true;strcpy(g->labels[free_label].session,session);
            }
            for(int i=0;i<SCOPES;i++)if(g->scopes[i].open&&g->scopes[i].implicit&&!strcmp(g->scopes[i].ident,session))g->scopes[i].private_only=true;
        }
        if(role){
            size_t slot=HINTS,oldest=0;
            for(size_t i=0;i<HINTS;i++){
                if(g->hints[i].set&&!strcmp(g->hints[i].session,session)){slot=i;break;}
                if(!g->hints[i].set){if(slot==HINTS)slot=i;}
                else if(g->hints[i].at<g->hints[oldest].at)oldest=i;
            }
            if(slot==HINTS)slot=oldest;
            g->hints[slot]=(struct hint){.at=now,.delegated=leaf,.set=true};strcpy(g->hints[slot].session,session);
        }
        pthread_mutex_unlock(&g->lock);
        fprintf(stderr,"session_hint role=%s data=%s\n",role?(leaf?"leaf":"orchestrator"):"none",restricted?"restricted":"none");
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
bool rc_gateway_drop_reasoning(const rc_runtime *rt) {
    return rt->gateway&&rt->gateway->drop_reasoning;
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
static bool continues(const struct scope *s,json_t *messages) {
    size_t n=json_array_size(messages),prior=json_array_size(s->history);
    if(s->pinned)return n>s->seen_messages;
    if(s->boundary)return rc_tool_boundary_replay_json(s->boundary,messages)==RC_TOOL_COMPLETE;
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
/* The request names (X-Recursant-session-id) a session the harness labelled
 * restricted. Caller holds the lock. */
static bool labelled(struct rc_gateway_context *g,const rc_gateway_headers *h) {
    if(!(h->invocation.mask&2u)||h->invocation.invalid)return false;
    for(size_t i=0;i<LABELS;i++)if(g->labels[i].set&&!strcmp(g->labels[i].session,h->invocation.values[1]))return true;
    return false;
}
/* Session for an unregistered automatic request. -1 = leave it unscoped (the
 * baseline, as before): nothing usable, the matching session is busy, or the
 * table is full of live sessions. Never rejects a request. */
static int implicit_scope(struct rc_gateway_context *g,json_t *body,const rc_gateway_headers *h,uint64_t now) {
    json_t *messages=json_object_get(body,"messages");uint64_t anchor;bool start;const char *first;
    if(!opening(messages,&anchor,&start,&first))return -1;
    const char *ident=(h->invocation.mask&2u)&&!h->invocation.invalid?h->invocation.values[1]:"";
    if(!start){
        int found=-1;
        for(int i=0;i<SCOPES;i++){
            struct scope *s=&g->scopes[i];
            if(!s->open||!s->implicit||s->anchor!=anchor||strcmp(s->ident,ident)||!continues(s,messages))continue;
            /* Prefer an exact (unpinned) continuation, then the most recent. */
            if(found<0||(g->scopes[found].pinned&&!s->pinned)||(g->scopes[found].pinned==s->pinned&&s->active>g->scopes[found].active))found=i;
        }
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
    /* A restricted label outlives any session object, including one reclaimed
     * while idle and re-adopted mid-conversation. */
    for(size_t i=0;ident[0]&&i<LABELS;i++)if(g->labels[i].set&&!strcmp(g->labels[i].session,ident))s->private_only=true;
    const char *lineage="none";
    if(start){
        for(size_t i=0;ident[0]&&i<HINTS;i++)
            if(g->hints[i].set&&!strcmp(g->hints[i].session,ident)&&now-g->hints[i].at<=HINT_TTL_MS&&g->hints[i].delegated){s->delegated=true;lineage="hint";}
        /* Always matched (also marks the orchestrator awaiting its delegates),
         * even when a hint already identified this session. */
        if(handed_out(g,first)&&!s->delegated){s->delegated=true;lineage="request";}
    }
    fprintf(stderr,"session scope=%d kind=request start=%d delegated=%d lineage=%s%s\n",slot,start,s->delegated,lineage,s->private_only?" data=restricted":"");
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
        json_t *probe=json_copy(body);
        bool ok=probe&&!json_object_set_new(probe,"model",json_string(a->model))&&
            (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
        json_decref(probe);
        double cost=g->costs[i].priced?g->costs[i].price.input_per_mtok:g->costs[i].fixed;
        if(ok&&(best==g->count||cost<best_cost)){best=i;best_cost=cost;}
    }
    return best;
}
/* Candidate serving exactly (trust, model), or -1. */
static int candidate_of(rc_runtime *rt,struct rc_gateway_context *g,rc_endpoint endpoint,const char *model) {
    for(size_t i=0;model&&i<g->count;i++){
        rc_alias *a=&rt->config.aliases[g->candidates[i].alias_index];
        if(a->endpoint==endpoint&&!strcmp(a->model,model))return (int)i;
    }
    return -1;
}
static bool cooling(const struct rc_gateway_context *g,size_t i,uint64_t now) {
    return g->health.on&&g->outcome[i].until>now;
}
static void remove_effort(json_t *,int);
/* Shadow dispatch helpers. Tool names are the harness's schema names (never
 * content); arguments are only hashed. */
static uint64_t fnv(const char *s) {
    uint64_t h=UINT64_C(1469598103934665603);
    for(;*s;s++){h^=(unsigned char)*s;h*=UINT64_C(1099511628211);}
    return h;
}
static void first_call(json_t *message,char name[65],uint64_t *hash) {
    json_t *f=json_object_get(json_array_get(json_object_get(message,"tool_calls"),0),"function");
    const char *n=token(f,"name",64),*a=json_string_value(json_object_get(f,"arguments"));
    strcpy(name,"none");*hash=0;
    if(n){bool plain=true;for(const char *c=n;*c;c++)if(!((*c>='a'&&*c<='z')||(*c>='A'&&*c<='Z')||(*c>='0'&&*c<='9')||*c=='_'||*c=='-'||*c=='.'))plain=false;strcpy(name,plain?n:"other");}
    if(!a)return;
    json_error_t e;json_t *v=json_loads(a,JSON_DECODE_ANY,&e);char *c=v?json_dumps(v,JSON_COMPACT|JSON_SORT_KEYS|JSON_ENCODE_ANY):NULL;
    *hash=fnv(c?c:a);free(c);json_decref(v);
}
struct shadow_job {rc_runtime *rt;char *url,*auth,*payload;char decision[17];size_t candidate;};
struct shadow_reply {char *bytes;size_t length;bool overflow;};
static size_t shadow_write(char *data,size_t size,size_t count,void *arg) {
    struct shadow_reply *b=arg;size_t n=size*count;
    if(b->overflow||b->length+n>262144){b->overflow=true;return n;}
    char *m=realloc(b->bytes,b->length+n+1);if(!m){b->overflow=true;return n;}
    b->bytes=m;memcpy(m+b->length,data,n);b->length+=n;m[b->length]=0;return n;
}
static void *shadow_run(void *arg) {
    struct shadow_job *j=arg;rc_runtime *rt=j->rt;struct rc_gateway_context *g=rt->gateway;
    struct shadow_reply b={0};long status=0;uint64_t start=now_ms();
    CURL *c=curl_easy_init();struct curl_slist *hs=curl_slist_append(NULL,"Content-Type: application/json");
    if(hs)hs=curl_slist_append(hs,"X-Recursant-Shadow: 1");
    if(hs&&j->auth)hs=curl_slist_append(hs,j->auth);
    if(c&&hs){
        curl_easy_setopt(c,CURLOPT_URL,j->url);curl_easy_setopt(c,CURLOPT_POSTFIELDS,j->payload);curl_easy_setopt(c,CURLOPT_HTTPHEADER,hs);
        curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,shadow_write);curl_easy_setopt(c,CURLOPT_WRITEDATA,&b);
        curl_easy_setopt(c,CURLOPT_NOSIGNAL,1L);curl_easy_setopt(c,CURLOPT_FOLLOWLOCATION,0L);curl_easy_setopt(c,CURLOPT_PROXY,"");
        curl_easy_setopt(c,CURLOPT_PROTOCOLS_STR,"http,https");curl_easy_setopt(c,CURLOPT_SSL_VERIFYPEER,1L);curl_easy_setopt(c,CURLOPT_SSL_VERIFYHOST,2L);
        curl_easy_setopt(c,CURLOPT_TIMEOUT,(long)rt->request_timeout_seconds);curl_easy_setopt(c,CURLOPT_CONNECTTIMEOUT,(long)rt->request_timeout_seconds);
        if(curl_easy_perform(c)==CURLE_OK)curl_easy_getinfo(c,CURLINFO_RESPONSE_CODE,&status);
    }
    uint64_t ms=now_ms()-start,prompt=0,completion=0,cached=0;char tool[65]="none",finish[33]="none";uint64_t hash=0;double cost=0;
    json_error_t error;json_t *root=status==200&&!b.overflow&&b.bytes?json_loadb(b.bytes,b.length,0,&error):NULL;
    json_t *usage=json_object_get(root,"usage"),*choice=json_array_get(json_object_get(root,"choices"),0);
    json_t *pt=json_object_get(usage,"prompt_tokens"),*ct=json_object_get(usage,"completion_tokens"),*cd=json_object_get(json_object_get(usage,"prompt_tokens_details"),"cached_tokens");
    if(json_is_integer(pt)&&json_integer_value(pt)>=0)prompt=(uint64_t)json_integer_value(pt);
    if(json_is_integer(ct)&&json_integer_value(ct)>=0)completion=(uint64_t)json_integer_value(ct);
    if(json_is_integer(cd)&&json_integer_value(cd)>=0)cached=(uint64_t)json_integer_value(cd);
    const char *fr=token(choice,"finish_reason",32);if(fr)strcpy(finish,fr);
    first_call(json_object_get(choice,"message"),tool,&hash);
    cost=rc_turn_cost(&g->costs[j->candidate].price,prompt,cached,completion);if(cost<0)cost=0;
    json_decref(root);
    pthread_mutex_lock(&g->lock);if(g->shadow.inflight)g->shadow.inflight--;g->shadow.spent+=cost;pthread_mutex_unlock(&g->lock);
    fprintf(stderr,"shadow id=%s alias=%s status=%ld ms=%llu prompt=%llu completion=%llu cost=%.6f finish=%s tool=%s args=%016llx\n",
        j->decision,rt->config.aliases[g->candidates[j->candidate].alias_index].from,status,(unsigned long long)ms,
        (unsigned long long)prompt,(unsigned long long)completion,cost,finish,tool,(unsigned long long)hash);
    curl_easy_cleanup(c);curl_slist_free_all(hs);free(b.bytes);
    if(j->auth){memset(j->auth,0,strlen(j->auth));free(j->auth);}
    free(j->url);free(j->payload);free(j);return NULL;
}
void rc_gateway_shadow(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint endpoint,rc_gateway_ticket *ticket) {
    struct rc_gateway_context *g=rt->gateway;
    if(!g||!g->shadow.on||!automatic||!g->active||ticket->scope<0)return;
    pthread_mutex_lock(&g->lock);
    struct scope *s=&g->scopes[ticket->scope];
    int from=candidate_of(rt,g,endpoint,json_string_value(json_object_get(body,"model")));
    bool go=!s->pinned&&!s->private_only&&!labelled(g,h)&&from>=0&&(size_t)from!=g->shadow.candidate;
    if(go&&g->shadow.spent>=g->shadow.usd_cap){
        if(!g->shadow.capped){g->shadow.capped=true;fprintf(stderr,"shadow_cap spent=%.6f limit=%.6f\n",g->shadow.spent,g->shadow.usd_cap);}
        go=false;
    }
    if(go&&g->shadow.inflight>=g->shadow.max_inflight)go=false;
    if(go){g->shadow.acc+=g->shadow.sample;if(g->shadow.acc>=1-1e-9)g->shadow.acc-=1;else go=false;}
    struct shadow_job *j=NULL;
    if(go){
        /* The exact final request, as the shadow's own non-streamed request;
         * a field the router added for the primary's family is removed. Final
         * M2 vets the copy on the shadow's own trust class. */
        rc_alias *a=&rt->config.aliases[g->candidates[g->shadow.candidate].alias_index];rc_endpoint ep=a->endpoint;
        json_t *copy=json_deep_copy(body);
        if(copy&&s->reasoning_added)remove_effort(copy,s->reasoning_added);
        bool ok=copy&&!json_object_set_new(copy,"model",json_string(a->model))&&!json_object_set_new(copy,"stream",json_false());
        if(ok){json_object_del(copy,"stream_options");ok=(!rc_dispatch_gate||!rc_dispatch_gate(rt,copy,&ep))&&ep==a->endpoint&&eq(copy,"model",a->model);}
        size_t p=ok?rc_runtime_dispatch_provider(rt,ep,a->model):RC_PROVIDER_NONE;
        if(p!=RC_PROVIDER_NONE&&(j=calloc(1,sizeof *j))){
            const char *base=rt->config.providers[p].url,*key=rt->provider_keys[p];size_t n=strlen(base);while(n&&base[n-1]=='/')n--;
            j->rt=rt;j->candidate=g->shadow.candidate;strcpy(j->decision,ticket->decision);
            j->url=malloc(n+32);j->payload=json_dumps(copy,JSON_COMPACT);j->auth=key?malloc(strlen(key)+24):NULL;
            if(j->url)snprintf(j->url,n+32,"%.*s/chat/completions",(int)n,base);
            if(j->auth)snprintf(j->auth,strlen(key)+24,"Authorization: Bearer %s",key);
            if(!j->url||!j->payload||(key&&!j->auth)){free(j->url);free(j->payload);free(j->auth);free(j);j=NULL;}
        }
        json_decref(copy);
        if(j){g->shadow.inflight++;ticket->shadowed=true;}
    }
    pthread_mutex_unlock(&g->lock);
    if(!j)return;
    pthread_t thread;pthread_attr_t attr;
    bool started=!pthread_attr_init(&attr)&&!pthread_attr_setdetachstate(&attr,PTHREAD_CREATE_DETACHED)&&!pthread_create(&thread,&attr,shadow_run,j);
    pthread_attr_destroy(&attr);
    if(!started){
        pthread_mutex_lock(&g->lock);g->shadow.inflight--;ticket->shadowed=false;pthread_mutex_unlock(&g->lock);
        free(j->url);free(j->payload);free(j->auth);free(j);
    }
}
static bool zero_price(const struct rc_gateway_context *g,size_t i) {
    return g->costs[i].priced&&g->costs[i].price.input_per_mtok==0&&g->costs[i].price.output_per_mtok==0;
}
/* Index of the housekeeping marker that opens this tool-less request's first
 * message, or -1. */
static int housekeeping_marker(const struct rc_gateway_context *g,json_t *body) {
    if(!g->housekeeping||json_object_get(body,"tools"))return -1;
    const char *text=json_string_value(json_object_get(json_array_get(json_object_get(body,"messages"),0),"content"));
    for(size_t i=0;text&&i<g->marker_count;i++)if(!strncmp(text,g->markers[i],strlen(g->markers[i])))return (int)i;
    return -1;
}
/* Housekeeping placement when final M2 permits the housekeeping candidate for
 * this exact request on its own trust class; otherwise the ordinary path. */
static bool housekeeping_place(rc_runtime *rt,struct rc_gateway_context *g,json_t *body,rc_endpoint *endpoint) {
    rc_alias *a=&rt->config.aliases[g->candidates[g->housekeeping_candidate].alias_index];rc_endpoint ep=a->endpoint;
    json_t *probe=json_copy(body);
    bool ok=probe&&!json_object_set_new(probe,"model",json_string(a->model))&&
        (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
    json_decref(probe);
    if(!ok||json_object_set_new(body,"model",json_string(a->model)))return false;
    *endpoint=a->endpoint;return true;
}
/* Adds candidate i's low/high reasoning effort in its family's field unless the
 * request already sets that destination's own control. A harness's OpenAI-style
 * reasoning_effort does not control a vLLM thinking switch (Hermes sends
 * reasoning_effort on every request; ma1-localthink, 2026-10-03, added nothing).
 * override ("steps" mode): the harness's openai/openrouter effort fields are
 * removed first (chat_template_kwargs is never replaced: it may carry other
 * template switches). Returns the family added. */
static int add_effort(struct rc_gateway_context *g,size_t i,json_t *body,bool high,bool override) {
    int f=g->efforts_by_signal[i].family;const char *t=high?g->efforts_by_signal[i].high:g->efforts_by_signal[i].low;
    if(!f||!t[0])return EFFORT_NONE;
    if(override&&f!=EFFORT_VLLM_THINKING){json_object_del(body,"reasoning_effort");json_object_del(body,"reasoning");}
    bool set=f==EFFORT_VLLM_THINKING?json_object_get(body,"chat_template_kwargs")!=NULL:
        json_object_get(body,"reasoning_effort")||json_object_get(body,"reasoning");
    if(set)return EFFORT_NONE;
    int failed=f==EFFORT_VLLM_THINKING?json_object_set_new(body,"chat_template_kwargs",json_pack("{s:b}","enable_thinking",!strcmp(t,"on"))):
        f==EFFORT_OPENAI?json_object_set_new(body,"reasoning_effort",json_string(t)):
        json_object_set_new(body,"reasoning",json_pack("{s:s}","effort",t));
    return failed?EFFORT_NONE:f;
}
static void remove_effort(json_t *body,int family) {
    static const char *const fields[]={NULL,"reasoning_effort","reasoning","chat_template_kwargs"};
    if(family>EFFORT_NONE&&family<=EFFORT_VLLM_THINKING)json_object_del(body,fields[family]);
}
/* Failover target for an automatic request leaving candidate `from`: the
 * baseline when `from` is not the baseline, otherwise the cheapest
 * escalation-qualified candidate (never a cheaper tier the operator has not
 * qualified for recovery). larger_than > 0 (context overflow): the baseline or
 * an escalation candidate whose context_limit exceeds it. It must be healthy,
 * have capacity, declare the session's requirements, satisfy a restricted
 * session, and pass final M2 for this exact request on its own trust class.
 * count = none. */
static size_t failover_target(rc_runtime *rt,struct rc_gateway_context *g,const struct scope *s,bool restricted,json_t *body,size_t from,uint64_t larger_than,uint64_t now) {
    bool from_baseline=g->candidates[from].alias_index==g->baseline;size_t best=g->count;double best_cost=0;
    for(size_t i=0;i<g->count;i++){
        if(i==from||cooling(g,i,now)||(g->max_inflight[i]&&g->inflight[i]>=g->max_inflight[i]))continue;
        bool base=g->candidates[i].alias_index==g->baseline,recovery=(g->candidates[i].qualified_tasks&RC_TASK_RECOVERY)!=0;
        if(larger_than?(g->candidates[i].context_limit<=larger_than||!(base||recovery)):(from_baseline?!recovery:!base))continue;
        rc_alias *a=&rt->config.aliases[g->candidates[i].alias_index];rc_endpoint ep=a->endpoint;
        if(restricted&&ep!=RC_ENDPOINT_PRIVATE)continue;
        if(s&&g->candidates[i].alias_index!=g->baseline&&((g->cap_known[i]&s->requirements)!=s->requirements||
           (g->cap_supported[i]&s->requirements)!=s->requirements||!candidate_effort(g,i,s->effort)))continue;
        json_t *probe=json_copy(body);
        bool ok=probe&&!json_object_set_new(probe,"model",json_string(a->model))&&
            (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
        json_decref(probe);
        double cost=g->costs[i].priced?g->costs[i].price.input_per_mtok:g->costs[i].fixed;
        if(ok&&(best==g->count||cost<best_cost)){best=i;best_cost=cost;}
    }
    return best;
}
/* Move an automatic request off candidate `from` (caller holds the lock).
 * Rewrites body model and endpoint; false when no target exists. */
static bool fail_over(rc_runtime *rt,struct rc_gateway_context *g,struct scope *s,int scope,bool restricted,json_t *body,rc_endpoint *endpoint,size_t from,uint64_t larger_than,const char *cause,uint64_t now) {
    size_t to=failover_target(rt,g,s,restricted,body,from,larger_than,now);
    rc_alias *a=to<g->count?&rt->config.aliases[g->candidates[to].alias_index]:NULL;
    fprintf(stderr,"route_failover scope=%d from=%s to=%s cause=%s\n",scope,rt->config.aliases[g->candidates[from].alias_index].from,a?a->from:"none",cause);
    if(!a||json_object_set_new(body,"model",json_string(a->model)))return false;
    *endpoint=a->endpoint;return true;
}
void rc_gateway_outcome(rc_runtime *rt,rc_endpoint endpoint,const char *model,long status,uint64_t retry_after_ms) {
    struct rc_gateway_context *g=rt->gateway;if(!g||!g->health.on||!model)return;
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();int i=candidate_of(rt,g,endpoint,model);
    if(i>=0){
        struct outcome *o=&g->outcome[i];
        if(!o->requests||now-o->window>=60000){o->window=now;o->requests=0;o->failures=0;}
        o->requests++;
        /* 0 = transport failure. Rate limits, auth, unknown model and
         * timeouts cool down at once; other 5xx only past the failure ratio. */
        bool immediate=!status||status==401||status==404||status==408||status==429;
        if(immediate||status>=500){
            o->failures++;
            if(immediate||(o->requests>=g->health.min_requests&&(double)o->failures>g->health.ratio*(double)o->requests)){
                uint64_t span=retry_after_ms>g->health.cooldown_ms?retry_after_ms:g->health.cooldown_ms;o->until=now+span;
                fprintf(stderr,"health_cooldown candidate=%s status=%ld ms=%llu\n",rt->config.aliases[g->candidates[i].alias_index].from,status,(unsigned long long)span);
            }
        }
    }
    pthread_mutex_unlock(&g->lock);
}
bool rc_gateway_decision_headers(const rc_runtime *rt) {
    return rt->gateway&&!rt->gateway->quiet_headers;
}
unsigned rc_gateway_max_retries(const rc_runtime *rt) {
    return rt->gateway&&rt->gateway->health.on?(unsigned)rt->gateway->health.max_retries:0;
}
bool rc_gateway_failover(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint *endpoint,rc_gateway_ticket *ticket,long status,bool context) {
    struct rc_gateway_context *g=rt->gateway;
    if(!g||!g->health.on||!g->active||!automatic||!ticket->begun||ticket->finished)return false;
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();bool moved=false;
    struct scope *s=ticket->scope>=0?&g->scopes[ticket->scope]:NULL;
    int from=candidate_of(rt,g,*endpoint,json_string_value(json_object_get(body,"model")));
    /* A pinned session may move here (Anders, 2026-10-02): its request is
     * complete and final M2 still vets the target. It stays pinned, now to
     * the target. M2 itself never moves a pinned session. */
    if(from>=0){
        /* The failed destination's reasoning field is not the target's. */
        if(s&&s->reasoning_added){remove_effort(body,s->reasoning_added);s->reasoning_added=EFFORT_NONE;}
        bool restricted=(s&&s->private_only)||(!s&&g->implicit&&labelled(g,h));
        char cause[32];if(context)strcpy(cause,"context");else if(status)snprintf(cause,sizeof cause,"status:%ld",status);else strcpy(cause,"transport");
        uint64_t limit=context?g->candidates[from].context_limit:0;
        moved=fail_over(rt,g,s,ticket->scope,restricted,body,endpoint,(size_t)from,limit,cause,now);
        if(moved&&s&&limit>s->context_floor)s->context_floor=limit;
    }
    if(moved){
        const char *model=json_string_value(json_object_get(body,"model"));
        ticket->reason="failover";ticket->costed=false;
        if(s){s->endpoint=*endpoint;strcpy(s->model,model);}
        if(ticket->capacity>=0&&(size_t)ticket->capacity<g->count&&g->inflight[ticket->capacity])g->inflight[ticket->capacity]--;
        ticket->capacity=-1;int to=candidate_of(rt,g,*endpoint,model);
        if(to>=0)snprintf(ticket->chosen,sizeof ticket->chosen,"%s",rt->config.aliases[g->candidates[to].alias_index].from);
        if(to>=0&&g->max_inflight[to]){g->inflight[to]++;ticket->capacity=to;}
    }
    pthread_mutex_unlock(&g->lock);return moved;
}
static unsigned prepare(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint *endpoint,rc_gateway_ticket *ticket);
/* Probes are shallow copies (json_copy): only their top-level "model" (and the
 * gate's own "provider") ever change. The content scan runs once, here, before
 * the gateway lock; every gate inside prepare reuses it (rc_compliance_memo). */
unsigned rc_gateway_prepare(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint *endpoint,rc_gateway_ticket *ticket) {
    if(rt->gateway&&rc_dispatch_gate==rc_compliance_gate)rc_compliance_memo_begin(rt,body);
    unsigned status=prepare(rt,body,automatic,h,endpoint,ticket);
    rc_compliance_memo_end();
    return status;
}
static unsigned prepare(rc_runtime *rt,json_t *body,bool automatic,const rc_gateway_headers *h,rc_endpoint *endpoint,rc_gateway_ticket *ticket) {
    struct rc_gateway_context *g=rt->gateway;ticket->scope=-1;ticket->row=-1;ticket->capacity=-1;
    if(!g)return rc_dispatch_gate&&rc_dispatch_gate(rt,body,endpoint)?403:0;
    /* Optional judge, asked BEFORE the gateway lock (it blocks up to its
     * timeout). Only for automatic turns the deterministic signals leave
     * unclassified, and only when final M2 already permits public placement
     * of this exact request (the judge provider is public egress). */
    rc_judge_result judged={.ok=false};bool asked=false;
    if(g->judge.enabled&&automatic&&g->active){
        rc_signal_scope one={.completed_turns=1};
        if(!rc_signals_classify(body,&one)&&!rc_signals_recent_failure(body)){
            json_t *probe=json_copy(body);rc_alias *b=&rt->config.aliases[g->baseline];rc_endpoint ep=b->endpoint;
            bool pub=probe&&!json_object_set_new(probe,"model",json_string(b->model))&&
                (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==RC_ENDPOINT_PUBLIC;
            json_decref(probe);
            /* A restricted session's state never goes to the public judge. */
            if(pub&&g->implicit){pthread_mutex_lock(&g->lock);if(labelled(g,h))pub=false;pthread_mutex_unlock(&g->lock);}
            if(pub){
                pthread_mutex_lock(&g->lock);bool open=g->judge_open_until>now_ms();pthread_mutex_unlock(&g->lock);
                if(!open){judged=rc_judge_ask(&g->judge,body);asked=judged.attempted;}
                if(asked){
                    pthread_mutex_lock(&g->lock);
                    if(judged.ok)g->judge_failures=0;
                    else if(++g->judge_failures>=JUDGE_BREAKER_FAILURES){
                        g->judge_failures=0;g->judge_open_until=now_ms()+g->judge_breaker_ms;
                        fprintf(stderr,"judge_breaker state=open failures=%u ms=%llu\n",JUDGE_BREAKER_FAILURES,(unsigned long long)g->judge_breaker_ms);
                    }
                    pthread_mutex_unlock(&g->lock);
                }
            }
        }
    }
    pthread_mutex_lock(&g->lock);uint64_t now=now_ms();unsigned status=0;struct scope *s=NULL;
    poll_locked(g,now);
    snprintf(ticket->decision,sizeof ticket->decision,"%016llx",(unsigned long long)(g->boot^(++g->decisions*UINT64_C(0x9e3779b97f4a7c15))));
    ticket->reason=automatic?"baseline":"fixed";ticket->costed=false;ticket->chosen[0]=0;ticket->shadowed=false;
    if(g->budget.rpm){
        if(!g->rpm_count||now-g->rpm_window>=60000){g->rpm_window=now;g->rpm_count=0;}
        if(g->rpm_count>=g->budget.rpm){fprintf(stderr,"budget_exhausted kind=requests_per_minute limit=%llu\n",(unsigned long long)g->budget.rpm);status=429;goto done;}
        g->rpm_count++;
    }
    double spend=0; /* session spend as a fraction of session_usd */
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
    /* context.reasoning: 1 = low (downshift), 2 = high (escalation), for the
     * selected alias effort_alias only. */
    int effort_step=0;size_t effort_alias=0;int marker=-1;
    if(h->generation[0]||h->branch[0]||h->invalid) {
        slot=scope_find(g,h->generation,h->branch);
        if(h->invalid||slot<0){status=403;goto done;}
        s=&g->scopes[slot];
        if(strcmp(s->task,h->invocation.values[0])||strcmp(s->session,h->invocation.values[1])){status=403;goto done;}
        if(s->inflight){status=409;goto done;}
    }
    /* Housekeeping: never a session (a title call opens with the user's first
     * message and would otherwise be matched against the conversation). A
     * restricted label wins. */
    else if(automatic&&g->active&&(marker=housekeeping_marker(g,body))>=0&&!labelled(g,h)&&housekeeping_place(rt,g,body,endpoint)){
        ticket->reason="housekeeping";
        fprintf(stderr,"route_housekeeping chosen=%s marker=%d\n",rt->config.aliases[g->candidates[g->housekeeping_candidate].alias_index].from,marker);
    }
    else if(g->implicit&&automatic&&(slot=implicit_scope(g,body,h,now))>=0)s=&g->scopes[slot];
    if(s) {
        ticket->scope=slot;s->reasoning_added=EFFORT_NONE;
        if(g->budget.session_requests&&s->requests>=g->budget.session_requests){
            fprintf(stderr,"budget_exhausted scope=%d kind=session_requests limit=%llu\n",slot,(unsigned long long)g->budget.session_requests);status=429;goto done;
        }
        s->requests++;
        if(g->budget.session_usd>0)spend=s->spent/g->budget.session_usd;
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
            rc_tool_status replay=rc_tool_boundary_replay_json(s->boundary,json_object_get(body,"messages"));
            if(replay==RC_TOOL_INCOMPLETE&&!s->implicit){status=409;goto done;}
            if(replay!=RC_TOOL_COMPLETE)s->pinned=true;
            required|=rc_tool_boundary_requirements(s->boundary);
        }else if(!s->pinned&&!replayable(s,body))s->pinned=true;
        s->requirements=required;
        if(automatic&&s->pinned&&s->owner){
            *endpoint=s->endpoint;if(json_object_set_new(body,"model",json_string(s->model))){status=500;goto done;}
            /* A pinned session is never moved, by M3 or by M2: if M2 vetoes
             * its owner for this request, the final gate below rejects. */
            ticket->reason="pin";
            if(g->signals)fprintf(stderr,"route_decision scope=%d mode=%s class=none reason=pin\ndecision_id scope=%d id=%s\n",ticket->scope,g->active?"active":"shadow",ticket->scope,ticket->decision);
        }
        else if(automatic) {
            rc_context_snapshot snapshot;bool usable=rc_context_get(g->contexts,&s->key,now,&snapshot)==RC_CONTEXT_OK&&snapshot.has_interpretation&&snapshot.revision==s->interpretation.revision&&exact(g,s->evidence_row,now)&&s->evidence_row==s->last_row;
            /* S4 structured signal: THIS request's facts, no interpreter wait.
             * Same replay/retry fences as interpreter advice; a pinned scope
             * never receives a class or escalation. */
            bool structural=g->signals&&!s->pinned;
            for(size_t i=0;i<g->rows_used;i++)if(g->rows[i].in_use&&same_headers(&h->invocation,&g->rows[i].headers))usable=structural=false;
            /* Request bytes: legacy registries' raw size and the estimate when
             * no usage is observed yet; a continuing priced session uses observed
             * usage plus the appended messages only, so the whole body is not
             * serialized again (agent requests are hundreds of KiB). */
            bool continuing=g->priced&&s->usage.known&&json_array_size(json_object_get(body,"messages"))>=s->usage_messages;
            uint64_t tokens=0;
            if(!continuing){char *wire=json_dumps(body,JSON_COMPACT);tokens=wire?strlen(wire):0;free(wire);}
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
                if(!last.known&&continuing){char *wire=json_dumps(body,JSON_COMPACT);tokens=wire?strlen(wire):0;free(wire);}
                prompt_est=rc_estimate_prompt_tokens(&last,appended,tokens);tokens=prompt_est;
            }
            if(output_bound(body,&max_tokens)){tokens=tokens>UINT64_MAX-max_tokens?UINT64_MAX:tokens+max_tokens;}else usable=structural=false;
            if(s->context_floor&&tokens<=s->context_floor)tokens=s->context_floor+1;
            output_est=rc_estimate_output_tokens(max_tokens,g->expected_output);
            uint64_t task=usable&&!strcmp(s->interpretation.next_action,"format_result")&&!strcmp(s->interpretation.difficulty_band,"simple")&&!strcmp(s->interpretation.coverage,"partial")?1:0;
            rc_signal_scope facts={.completed_turns=s->turns,.repeat_escalation=g->repeat,.phase=g->phase};
            uint64_t signal=structural?rc_signals_classify(body,&facts):0;
            uint64_t escalation=signal==RC_TASK_RECOVERY?RC_TASK_RECOVERY:0;if(escalation)signal=0;
            /* Judge advice only fills an unclassified structural turn; never
             * a pinned/private-only scope, recovery, or the first turn. */
            const char *judge_verdict=asked?(judged.ok?(rc_judge_routine(&g->judge,&judged)?"routine":"hard"):"unavailable"):NULL;
            if(asked&&structural&&!signal&&!escalation&&s->turns&&!s->private_only&&rc_judge_routine(&g->judge,&judged))signal=RC_TASK_TOOL_FOLLOWUP_OK;
            /* Efficiency model: adds a downshift on an unclassified turn after
             * the first (p >= downshift_min) or removes one the signals or the
             * judge gave (p < veto_below). Never a pinned or private-only
             * scope or a recovery turn; selection and final M2 still decide. */
            if(g->efficiency.enabled&&structural&&!escalation&&!s->private_only){
                double p=rc_efficiency_score(&g->efficiency,body);const char *action="none";
                if(p>=0){
                    action="keep";
                    if(signal&&p<g->efficiency.veto_below){signal=0;action="veto";}
                    else if(!signal&&s->turns&&p>=g->efficiency.downshift_min){signal=RC_TASK_TOOL_FOLLOWUP_OK;action="add";}
                }
                fprintf(stderr,"efficiency scope=%d p=%.3f action=%s\n",ticket->scope,p,action);
            }
            /* Prompt classifier: a fresh user question (chat or single query,
             * or an agent's instruction when agent_turns is on) that the economy
             * tier is predicted to answer. Fills an unclassified turn only;
             * never a pinned or private-only scope or a recovery turn. */
            if(g->prompt.enabled&&structural&&!signal&&!escalation&&!s->private_only){
                bool tools=json_array_size(json_object_get(body,"tools"))>0;
                double p=(!tools||g->prompt.agent_turns)?rc_prompt_score(&g->prompt,body):-1;const char *action="none";
                if(p>=0){action="keep";if(p>=g->prompt.simple_min){signal=RC_TASK_SIMPLE_PROMPT;action="add";}}
                fprintf(stderr,"prompt scope=%d p=%.3f action=%s\n",ticket->scope,p,action);
            }
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
                json_t *probe=json_copy(body);rc_endpoint ep=a->endpoint;
                if(!probe||json_object_set_new(probe,"model",json_string(a->model))){json_decref(probe);status=500;goto done;}
                quotes[i].permitted=(!s->private_only||ep==RC_ENDPOINT_PRIVATE)&&
                    (!rc_dispatch_gate||!rc_dispatch_gate(rt,probe,&ep))&&ep==a->endpoint&&eq(probe,"model",a->model);
                if(g->candidates[i].alias_index==g->baseline)baseline_permitted=quotes[i].permitted;
                else if((g->max_inflight[i]&&g->inflight[i]>=g->max_inflight[i])||cooling(g,i,now))quotes[i].permitted=false;
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
            bool placed=false;const char *placement="compliance";
            if(g->budget.session_usd>0&&spend>=g->budget.downshift_at){
                /* Near the cap: the cheapest permitted candidate that fits; at
                 * the cap, only zero-price ones (none: refused below). */
                size_t to=g->count;
                for(size_t i=0;i<g->count;i++)
                    if(quotes[i].permitted&&g->candidates[i].context_limit>=tokens&&(spend<1||zero_price(g,i))&&
                       (to==g->count||quotes[i].expected_task_cost<quotes[to].expected_task_cost))to=i;
                if(to<g->count){selected.alias_index=g->candidates[to].alias_index;placed=true;placement="budget";}
            }
            size_t base=0;while(base<g->count&&g->candidates[base].alias_index!=g->baseline)base++;
            if(!placed&&baseline_permitted&&base<g->count&&g->candidates[base].context_limit<tokens){
                /* The baseline cannot hold this request: the cheapest permitted
                 * escalation-qualified candidate that can, instead of refusing. */
                size_t to=g->count;
                for(size_t i=0;i<g->count;i++)
                    if(i!=base&&quotes[i].permitted&&(g->candidates[i].qualified_tasks&RC_TASK_RECOVERY)&&g->candidates[i].context_limit>=tokens&&
                       (to==g->count||quotes[i].expected_task_cost<quotes[to].expected_task_cost))to=i;
                if(to<g->count){selected.alias_index=g->candidates[to].alias_index;placed=true;placement="context";}
            }
            if(!placed&&baseline_permitted){if(rc_select(g->registry,quotes,g->count,&req,&selected)!=RC_SELECT_OK&&g->active){status=403;goto done;}}
            else if(!placed){
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
                for(uint64_t bit=1;bit<=RC_TASK_MAX;bit<<=1)if(offered&bit){
                    size_t n=strlen(classes);snprintf(classes+n,sizeof classes-n,"%s%s",n?"+":"",rc_task_name(bit));
                }
                char line[4096];int used=snprintf(line,sizeof line,"route_decision scope=%d mode=%s class=%s reason=%s chosen=%s est_prompt=%llu est_out=%llu costs=",
                    ticket->scope,g->active?"active":"shadow",classes[0]?classes:"none",placed?placement:reasons[selected.reason],rt->config.aliases[selected.alias_index].from,(unsigned long long)prompt_est,(unsigned long long)output_est);
                for(size_t i=0;i<g->count&&used>0&&(size_t)used<sizeof line;i++)
                    used+=snprintf(line+used,sizeof line-(size_t)used,"%s%s:%.9g%s",i?",":"",rt->config.aliases[g->candidates[i].alias_index].from,quotes[i].expected_task_cost,quotes[i].permitted?"":"(denied)");
                /* The id goes on its own line: route_decision's format is
                 * parsed by tests and the benchmark analysers. */
                fprintf(stderr,"%s\ndecision_id scope=%d id=%s\n",line,ticket->scope,ticket->decision);
            }
            if(g->active){
                static const char *names[]={"baseline","cheapest","pin","escalate"};
                ticket->reason=placed?placement:names[selected.reason];
                for(size_t i=0;g->priced&&i<g->count;i++)if(g->candidates[i].alias_index==selected.alias_index){ticket->cost=quotes[i].expected_task_cost;ticket->costed=true;}
            }
            if(g->active){rc_alias *a=&rt->config.aliases[selected.alias_index];*endpoint=a->endpoint;if(json_object_set_new(body,"model",json_string(a->model))){status=500;goto done;}}
            if(g->active&&g->reasoning==REASONING_SIGNALS&&!placed&&!s->pinned){
                effort_step=selected.reason==RC_SELECT_ESCALATE?2:selected.reason==RC_SELECT_CHEAPEST?1:0;effort_alias=selected.alias_index;
            }
            else if(g->active&&g->reasoning==REASONING_STEPS&&!placed&&!s->pinned){
                bool routine=!escalation&&selected.reason!=RC_SELECT_ESCALATE&&(signal&(RC_TASK_TOOL_FOLLOWUP_OK|RC_TASK_FINAL_ANSWER|RC_TASK_SIMPLE_PROMPT));
                effort_step=routine?1:2;effort_alias=selected.alias_index;
            }
        }
    }
    /* Health: an automatic request is not sent to a cooling candidate when a
     * failover target exists (otherwise it goes anyway: cooldown never
     * refuses on its own). Before the requested destination is fixed, so
     * the final checks below treat it like any other selection. */
    bool health_moved=false;
    if(automatic&&g->active&&g->health.on){
        int from=candidate_of(rt,g,*endpoint,json_string_value(json_object_get(body,"model")));
        bool restricted=(s&&s->private_only)||(!s&&g->implicit&&labelled(g,h));
        if(from>=0&&cooling(g,(size_t)from,now)&&fail_over(rt,g,s,ticket->scope,restricted,body,endpoint,(size_t)from,0,"cooldown",now)){ticket->reason="cooldown";ticket->costed=false;health_moved=true;}
    }
    /* Explicit scoped aliases are never silently retargeted by authority.
     * Run final M2, then reject a conflict instead of changing the alias. */
    rc_endpoint requested_endpoint=*endpoint;char requested_model[129]={0};
    if(s){
        const char *requested=json_string_value(json_object_get(body,"model"));
        if(!requested||strlen(requested)>128){status=403;goto done;}
        strcpy(requested_model,requested);
    }
    /* Restricted: the session's own authority, or a harness label on a request
     * that could not be given a session (busy, table full): never public. */
    if((s&&s->private_only)||(!s&&g->implicit&&labelled(g,h))){
        if(!automatic){if(*endpoint!=RC_ENDPOINT_PRIVATE){status=403;goto done;}}
        else {
            *endpoint=RC_ENDPOINT_PRIVATE;
            if(json_object_set_new(body,"model",json_string(rt->config.private_model))){status=500;goto done;}
            ticket->reason="restricted";ticket->costed=false;
        }
    }
    /* Reasoning effort for the step, before the final gate classifies the
     * exact outgoing object (a cooldown move to another alias cancels it). */
    if(s&&effort_step){
        int i=candidate_of(rt,g,*endpoint,json_string_value(json_object_get(body,"model")));
        if(i>=0&&g->candidates[i].alias_index==effort_alias&&(s->reasoning_added=add_effort(g,(size_t)i,body,effort_step==2,g->reasoning==REASONING_STEPS)))
            fprintf(stderr,"route_effort scope=%d chosen=%s effort=%s\n",ticket->scope,rt->config.aliases[effort_alias].from,effort_step==2?"high":"low");
    }
    if(rc_dispatch_gate&&rc_dispatch_gate(rt,body,endpoint)){status=403;goto done;}
    const char *model=json_string_value(json_object_get(body,"model"));
    if(s&&g->budget.session_usd>0&&spend>=1){
        int i=candidate_of(rt,g,*endpoint,model);
        if(i<0||!zero_price(g,(size_t)i)){
            fprintf(stderr,"budget_exhausted scope=%d kind=session_usd spent=%.6f limit=%.6f\n",ticket->scope,s->spent,g->budget.session_usd);status=429;goto done;
        }
    }
    if(s){
        if(!model||strlen(model)>128){status=403;goto done;}
        if((!automatic||(s->requirements&&s->owner))&&(*endpoint!=requested_endpoint||strcmp(model,requested_model))){status=403;goto done;}
        if(!automatic&&s->requirements&&s->owner&&(*endpoint!=s->endpoint||strcmp(model,s->model))){status=403;goto done;}
        if(s->pinned&&s->owner&&!health_moved&&(*endpoint!=s->endpoint||strcmp(model,s->model))){status=403;goto done;}
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
    {int i=candidate_of(rt,g,*endpoint,model);snprintf(ticket->chosen,sizeof ticket->chosen,"%s",i>=0?rt->config.aliases[g->candidates[i].alias_index].from:model?model:"");}
    /* Count every dispatch to a capacity-limited candidate's model, scoped or
     * not and however it was chosen; released in rc_gateway_finish. */
    for(size_t i=0;model&&i<g->count;i++){
        rc_alias *a=&rt->config.aliases[g->candidates[i].alias_index];
        if(g->max_inflight[i]&&a->endpoint==*endpoint&&!strcmp(a->model,model)){g->inflight[i]++;ticket->capacity=(int)i;break;}
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
    if(ticket->capacity>=0&&(size_t)ticket->capacity<g->count&&g->inflight[ticket->capacity])g->inflight[ticket->capacity]--;
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
        /* Budget spend of this exchange (pinned or not), at the served price. */
        if(g->budget.session_usd>0&&complete){
            rc_usage_observation u={0};
            if(sse&&observer&&observer->usage_known&&!observer->failed&&observer->done)
                u=(rc_usage_observation){.known=true,.prompt_tokens=(uint64_t)observer->usage_prompt,.completion_tokens=(uint64_t)observer->usage_completion,.cached_tokens=(uint64_t)observer->usage_cached};
            else if(!sse&&json_is_integer(pt)&&json_integer_value(pt)>=0&&json_is_integer(ct)&&json_integer_value(ct)>=0)
                u=(rc_usage_observation){.known=true,.prompt_tokens=(uint64_t)json_integer_value(pt),.completion_tokens=(uint64_t)json_integer_value(ct),
                    .cached_tokens=json_is_integer(cached)&&json_integer_value(cached)>=0?(uint64_t)json_integer_value(cached):0};
            int i=candidate_of(rt,g,s->endpoint,s->model);
            double c=u.known&&i>=0?rc_turn_cost(&g->costs[i].price,u.prompt_tokens,u.cached_tokens,u.completion_tokens):0;
            if(c>0)s->spent+=c;
        }
        json_t *stream_message=complete&&sse?rc_response_observer_message(observer):NULL;
        bool tool_response=safe&&eq(choice,"finish_reason","tool_calls")&&tool_envelope(root,choice);
        if(sse){
            message=stream_message;
            safe=message!=NULL;
            tool_response=safe&&json_object_get(message,"tool_calls")!=NULL;
        }
        if(ticket->shadowed){
            char name[65];uint64_t hash;first_call(message,name,&hash);int i=candidate_of(rt,g,s->endpoint,s->model);
            const char *fr=sse?(json_object_get(message,"tool_calls")?"tool_calls":"stop"):token(choice,"finish_reason",32);
            fprintf(stderr,"shadow_primary id=%s alias=%s finish=%s tool=%s args=%016llx\n",ticket->decision,
                i>=0?rt->config.aliases[g->candidates[i].alias_index].from:"other",complete&&fr?fr:"none",name,(unsigned long long)hash);
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
