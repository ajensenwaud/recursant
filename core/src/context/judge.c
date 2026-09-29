#define _POSIX_C_SOURCE 200809L
#include "recursant/judge.h"
#include <curl/curl.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *role(const json_t *m) { return json_string_value(json_object_get(m,"role")); }
static json_t *clipped(const char *s, size_t n) {
    if (!s) return json_string("");
    if (n<=RC_JUDGE_TEXT_CLIP) return json_stringn(s,n);
    /* Clip at the head and tail; json_stringn rejects a split UTF-8 sequence,
     * so back off to a character boundary. */
    size_t head=RC_JUDGE_TEXT_CLIP/2, tail=RC_JUDGE_TEXT_CLIP/2;
    while (head && ((unsigned char)s[head]&0xC0)==0x80) --head;
    size_t start=n-tail;
    while (start<n && ((unsigned char)s[start]&0xC0)==0x80) ++start;
    size_t len=head+15+(n-start);
    char *buf=malloc(len+1); if (!buf) return NULL;
    memcpy(buf,s,head); memcpy(buf+head," ...[clipped]. ",15); memcpy(buf+head+15,s+start,n-start);
    json_t *v=json_stringn(buf,len); free(buf); return v;
}
static json_t *questions(void) {
    return json_pack("{s:{s:s,s:s,s:{s:s,s:s}},s:{s:s,s:s,s:[s,s,s]}}",
        "next_step","type","choice","instructions",
        "Given the coding agent's task and its most recent tool activity, what kind of step does the agent need to take next?",
        "criteria",
        "routine","Mechanical continuation: write or read a file, run tests, fix arguments, report results, with no new algorithmic reasoning",
        "hard","Needs real reasoning: design the solution, diagnose a failing test or traceback, or fix a logic bug",
        "difficulty","type","score","instructions","How much reasoning does the agent's next step require?",
        "criteria","Trivial mechanical step","Moderate reasoning","Hard reasoning");
}
char *rc_judge_request(const json_t *body, const char *model) {
    json_t *messages=json_object_get(body,"messages");
    size_t n=json_array_size(messages);
    if (!model || !json_is_array(messages) || !n || n>256) return NULL;
    const json_t *last=json_array_get(messages,n-1);
    if (!role(last) || strcmp(role(last),"tool")) return NULL;
    const char *task=NULL; size_t task_len=0, assistants=0;
    for (size_t i=0;i<n;i++) {
        const json_t *m=json_array_get(messages,i); const char *r=role(m);
        if (!r) return NULL;
        if (!strcmp(r,"assistant")) ++assistants;
        if (!task && !strcmp(r,"user") && json_is_string(json_object_get(m,"content"))) {
            task=json_string_value(json_object_get(m,"content")); task_len=json_string_length(json_object_get(m,"content"));
        }
    }
    if (!assistants) return NULL;
    json_t *recent=json_array(), *state=NULL, *root=NULL; char *out=NULL;
    if (!recent) return NULL;
    size_t from=n>RC_JUDGE_RECENT?n-RC_JUDGE_RECENT:0;
    for (size_t i=from;i<n;i++) {
        const json_t *m=json_array_get(messages,i); const char *r=role(m);
        if (!strcmp(r,"assistant")) {
            json_t *calls=json_object_get(m,"tool_calls");
            for (size_t k=0;k<json_array_size(calls)&&k<4;k++) {
                json_t *f=json_object_get(json_array_get(calls,k),"function");
                json_t *args=json_object_get(f,"arguments");
                json_t *e=json_pack("{s:s?,s:o}","tool_call",json_string_value(json_object_get(f,"name")),
                    "arguments",clipped(json_string_value(args),json_string_length(args)));
                if (!e || json_array_append_new(recent,e)) goto done;
            }
        } else if (!strcmp(r,"tool")) {
            json_t *c=json_object_get(m,"content");
            json_t *e=json_pack("{s:o}","tool_result",clipped(json_string_value(c),json_string_length(c)));
            if (!e || json_array_append_new(recent,e)) goto done;
        }
    }
    json_t *task_text=task?json_stringn(task,task_len>1500?1500:task_len):json_string("");
    if (!task_text) task_text=json_string("");  /* split UTF-8 at the cut: drop, never repair */
    state=json_pack("{s:o,s:I,s:O}","task",task_text,"turn",(json_int_t)assistants+1,"recent",recent);
    if (!state) goto done;
    root=json_pack("{s:s,s:O,s:o}","model",model,"state",state,"questions",questions());
    if (!root) goto done;
    char *s=json_dumps(state,JSON_COMPACT);
    bool small=s&&strlen(s)<=RC_JUDGE_STATE_BYTES; free(s);
    if (small) out=json_dumps(root,JSON_COMPACT);
done:
    json_decref(recent); json_decref(state); json_decref(root);
    return out;
}
static bool prob(const json_t *v, double lo, double hi, double *out) {
    if (!json_is_number(v)) return false;
    double d=json_number_value(v);
    if (!isfinite(d) || d<lo || d>hi) return false;
    *out=d; return true;
}
bool rc_judge_parse(const char *text, size_t length, rc_judge_result *out) {
    json_t *root=json_loadb(text,length,JSON_REJECT_DUPLICATES,NULL);
    json_t *answers=json_object_get(root,"answers");
    json_t *step=json_object_get(answers,"next_step"), *diff=json_object_get(answers,"difficulty");
    json_t *probs=json_object_get(step,"probabilities");
    rc_judge_result r={.ok=true};
    bool ok=json_is_object(root) && json_is_object(answers) &&
        json_is_string(json_object_get(step,"type")) && !strcmp(json_string_value(json_object_get(step,"type")),"choice") &&
        json_is_object(probs) && json_object_size(probs)==2 &&
        prob(json_object_get(probs,"routine"),0,1,&r.routine) && json_is_number(json_object_get(probs,"hard")) &&
        json_is_string(json_object_get(diff,"type")) && !strcmp(json_string_value(json_object_get(diff,"type")),"score") &&
        prob(json_object_get(diff,"score"),0,2,&r.difficulty);
    json_decref(root);
    if (ok) { r.attempted=out->attempted; r.latency_ms=out->latency_ms; *out=r; }
    return ok;
}
struct buffer { char bytes[65536]; size_t len; bool overflow; };
static size_t sink(char *data, size_t size, size_t count, void *arg) {
    struct buffer *b=arg; size_t n=size*count;
    if (n>sizeof b->bytes-b->len) { b->overflow=true; return 0; }
    memcpy(b->bytes+b->len,data,n); b->len+=n; return n;
}
static unsigned long long ms_now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (unsigned long long)t.tv_sec*1000ULL+(unsigned long long)t.tv_nsec/1000000ULL;
}
rc_judge_result rc_judge_ask(const rc_judge_config *cfg, const json_t *body) {
    rc_judge_result r={.ok=false};
    if (!cfg || !cfg->enabled || !cfg->key) return r;
    char *request=rc_judge_request(body,cfg->model);
    if (!request) return r;
    r.attempted=true;
    CURL *easy=curl_easy_init(); struct curl_slist *hs=NULL; char *auth=malloc(strlen(cfg->key)+23);
    struct buffer *b=calloc(1,sizeof *b);
    unsigned long long start=ms_now();
    if (!easy || !auth || !b) goto done;
    sprintf(auth,"Authorization: Bearer %s",cfg->key);
    hs=curl_slist_append(hs,"Content-Type: application/json");
    if (hs) hs=curl_slist_append(hs,auth);
    if (!hs) goto done;
#define SET(o,v) do { if (curl_easy_setopt(easy,o,v)!=CURLE_OK) goto done; } while (0)
    SET(CURLOPT_URL,cfg->url); SET(CURLOPT_POSTFIELDS,request); SET(CURLOPT_HTTPHEADER,hs);
    SET(CURLOPT_NOSIGNAL,1L); SET(CURLOPT_FOLLOWLOCATION,0L); SET(CURLOPT_PROXY,"");
    SET(CURLOPT_NETRC,CURL_NETRC_IGNORED); SET(CURLOPT_PROTOCOLS_STR,"http,https");
    SET(CURLOPT_TIMEOUT_MS,(long)cfg->timeout_ms); SET(CURLOPT_CONNECTTIMEOUT_MS,(long)cfg->timeout_ms);
    SET(CURLOPT_WRITEFUNCTION,sink); SET(CURLOPT_WRITEDATA,b);
#undef SET
    long code=0;
    if (curl_easy_perform(easy)==CURLE_OK && curl_easy_getinfo(easy,CURLINFO_RESPONSE_CODE,&code)==CURLE_OK &&
        code==200 && !b->overflow) (void)rc_judge_parse(b->bytes,b->len,&r);
done:
    r.latency_ms=(unsigned)(ms_now()-start);
    if (easy) curl_easy_cleanup(easy);
    curl_slist_free_all(hs);
    if (auth) { memset(auth,0,strlen(auth)); free(auth); }
    free(b); free(request);
    return r;
}
bool rc_judge_routine(const rc_judge_config *cfg, const rc_judge_result *r) {
    return cfg && r && r->ok && r->routine>=cfg->routine_min && r->difficulty<=cfg->difficulty_max;
}
