#include "recursant/efficiency.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
#define NEAR(a,b) (fabs((a)-(b))<1e-9)
/* Fixtures are written with ' for " to stay readable. */
static json_t *load(const char *text) {
    size_t n=strlen(text);char *t=malloc(n+1);if(!t)exit(1);memcpy(t,text,n+1);
    for(char *p=t;*p;p++)if(*p=='\'')*p='"';
    json_error_t e;json_t *v=json_loads(t,0,&e);free(t);
    if(!v){fprintf(stderr,"fixture: %s\n",e.text);exit(1);}
    return v;
}
static void features(const char *text,double f[RC_EFF_FEATURES]) {
    json_t *b=load(text);CHECK(rc_efficiency_features(b,f));json_decref(b);
}
static void names(void) {
    CHECK(RC_EFF_FEATURES==17);
    CHECK(!strcmp(rc_efficiency_names[RC_EFF_BIAS],"bias"));
    CHECK(!strcmp(rc_efficiency_names[RC_EFF_LAST_WRITE_FILE],"last_call_write_file"));
    CHECK(!strcmp(rc_efficiency_names[RC_EFF_LAST_DELEGATE_TASK],"last_call_delegate_task"));
    CHECK(!strcmp(rc_efficiency_names[RC_EFF_NO_TOOLS_OFFERED],"no_tools_offered"));
}
static void basic_counts(void) {
    double f[RC_EFF_FEATURES];
    features("{'messages':[{'role':'system','content':'You are an agent.'},{'role':'user','content':'do it'},"
             "{'role':'assistant','content':null,'tool_calls':[{'id':'a','type':'function','function':{'name':'read_file','arguments':'{}'}}]},"
             "{'role':'tool','tool_call_id':'a','content':'hello'}],'tools':[{'type':'function'}]}",f);
    CHECK(f[RC_EFF_BIAS]==1.0);
    CHECK(NEAR(f[RC_EFF_LOG_MESSAGES],log1p(4)));
    CHECK(NEAR(f[RC_EFF_LOG_TOOL_RESULTS],log1p(1)));
    CHECK(NEAR(f[RC_EFF_LOG_LAST_LEN],log1p(5)));
    CHECK(f[RC_EFF_LAST_READ_FILE]==1.0&&f[RC_EFF_LAST_TERMINAL]==0.0&&f[RC_EFF_LAST_WRITE_FILE]==0.0);
    CHECK(f[RC_EFF_LAST_FAILED]==0.0&&f[RC_EFF_FAILS_IN_LAST3]==0.0&&f[RC_EFF_FAILURE_RUN]==0.0);
    CHECK(f[RC_EFF_SUBAGENT]==0.0&&f[RC_EFF_REPEAT_LAST_CALL]==0.0&&f[RC_EFF_NO_TOOLS_OFFERED]==0.0);
}
static void code_points(void) {
    /* 'héllo' is 5 code points, 6 bytes: lengths are Python's len(). */
    double f[RC_EFF_FEATURES];
    features("{'messages':[{'role':'tool','tool_call_id':'a','content':'h\\u00e9llo'}]}",f);
    CHECK(NEAR(f[RC_EFF_LOG_LAST_LEN],log1p(5)));
    CHECK(f[RC_EFF_NO_TOOLS_OFFERED]==1.0);   /* no tools key */
    features("{'messages':[],'tools':[]}",f);
    CHECK(f[RC_EFF_NO_TOOLS_OFFERED]==1.0&&f[RC_EFF_LOG_LAST_LEN]==0.0&&f[RC_EFF_LAST_FAILED]==0.0);
}
static void failures(void) {
    static const char *bad[]={"Traceback (most recent call last): x","3 FAILED","ERROR: no","Error: no",
        "AssertionError","{\\\"exit_code\\\": 2}","{\\\"success\\\": false}","{\\\"error\\\": \\\"boom\\\"}"};
    static const char *good[]={"ok","{\\\"exit_code\\\": 0}","{\\\"error\\\": \\\"\\\"}","{\\\"error\\\": null}","error: lowercase","failed"};
    char buf[512];double f[RC_EFF_FEATURES];
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++){
        snprintf(buf,sizeof buf,"{'messages':[{'role':'tool','tool_call_id':'a','content':\"%s\"}]}",bad[i]);
        for(char *p=buf;*p;p++)if(*p=='\'')*p='"';
        json_error_t e;json_t *b=json_loads(buf,0,&e);CHECK(b);CHECK(rc_efficiency_features(b,f));json_decref(b);
        CHECK(f[RC_EFF_LAST_FAILED]==1.0);
    }
    for(size_t i=0;i<sizeof good/sizeof *good;i++){
        snprintf(buf,sizeof buf,"{'messages':[{'role':'tool','tool_call_id':'a','content':\"%s\"}]}",good[i]);
        for(char *p=buf;*p;p++)if(*p=='\'')*p='"';
        json_error_t e;json_t *b=json_loads(buf,0,&e);CHECK(b);CHECK(rc_efficiency_features(b,f));json_decref(b);
        CHECK(f[RC_EFF_LAST_FAILED]==0.0);
    }
    /* Window and run: results ok, ERROR:, ok, FAILED, ERROR: -> last3 = 2 failures, run = 2. */
    features("{'messages':[{'role':'tool','content':'ok'},{'role':'tool','content':'ERROR: a'},{'role':'tool','content':'ok'},"
             "{'role':'tool','content':'FAILED'},{'role':'tool','content':'ERROR: b'}]}",f);
    CHECK(f[RC_EFF_LAST_FAILED]==1.0&&f[RC_EFF_FAILS_IN_LAST3]==2.0&&f[RC_EFF_FAILURE_RUN]==2.0);
    /* The run is capped at 3. */
    features("{'messages':[{'role':'tool','content':'FAILED'},{'role':'tool','content':'FAILED'},"
             "{'role':'tool','content':'FAILED'},{'role':'tool','content':'FAILED'}]}",f);
    CHECK(f[RC_EFF_FAILURE_RUN]==3.0&&f[RC_EFF_FAILS_IN_LAST3]==3.0);
    /* A marker beyond the scanned prefix does not count. */
    size_t n=RC_EFF_SCAN_BYTES+64;char *big=malloc(n+100);CHECK(big);
    strcpy(big,"{\"messages\":[{\"role\":\"tool\",\"content\":\"");size_t o=strlen(big);
    memset(big+o,'x',RC_EFF_SCAN_BYTES);o+=RC_EFF_SCAN_BYTES;strcpy(big+o,"FAILED\"}]}");
    json_error_t e;json_t *b=json_loads(big,0,&e);free(big);CHECK(b);CHECK(rc_efficiency_features(b,f));json_decref(b);
    CHECK(f[RC_EFF_LAST_FAILED]==0.0);
    /* Non-string tool content counts as an empty result. */
    features("{'messages':[{'role':'tool','content':[{'type':'text','text':'FAILED'}]}]}",f);
    CHECK(f[RC_EFF_LAST_FAILED]==0.0&&NEAR(f[RC_EFF_LOG_TOOL_RESULTS],log1p(1))&&f[RC_EFF_LOG_LAST_LEN]==0.0);
}
static void subagent_and_calls(void) {
    double f[RC_EFF_FEATURES];
    features("{'messages':[{'role':'system','content':'You are a focused SubAgent.'},{'role':'user','content':'x'}]}",f);
    CHECK(f[RC_EFF_SUBAGENT]==1.0);
    /* 'delegat' in the system prompt counts only with a short first user message. */
    features("{'messages':[{'role':'system','content':'Work was DELEGATED to you.'},{'role':'user','content':'short task'}]}",f);
    CHECK(f[RC_EFF_SUBAGENT]==1.0);
    char *longer=malloc(1200);CHECK(longer);
    strcpy(longer,"{\"messages\":[{\"role\":\"system\",\"content\":\"you may delegate\"},{\"role\":\"user\",\"content\":\"");
    size_t o=strlen(longer);memset(longer+o,'u',600);strcpy(longer+o+600,"\"}]}");
    json_error_t e;json_t *b=json_loads(longer,0,&e);free(longer);CHECK(b);CHECK(rc_efficiency_features(b,f));json_decref(b);
    CHECK(f[RC_EFF_SUBAGENT]==0.0);
    /* Last call and repeats, across assistant messages and parallel calls. */
    features("{'messages':[{'role':'assistant','tool_calls':[{'function':{'name':'terminal'}}]},"
             "{'role':'assistant','tool_calls':[{'function':{'name':'patch'}},{'function':{'name':'patch'}}]}]}",f);
    CHECK(f[RC_EFF_LAST_PATCH]==1.0&&f[RC_EFF_LAST_TERMINAL]==0.0&&f[RC_EFF_REPEAT_LAST_CALL]==1.0);
    features("{'messages':[{'role':'assistant','tool_calls':[{'function':{'name':'delegate_task'}}]},"
             "{'role':'assistant','tool_calls':[{'function':{'name':'unknown_tool'}}]}]}",f);
    for(int i=RC_EFF_LAST_TERMINAL;i<RC_EFF_FEATURES;i++)CHECK(f[i]==0.0);
    CHECK(f[RC_EFF_REPEAT_LAST_CALL]==0.0);
    b=load("{'model':'x'}");CHECK(!rc_efficiency_features(b,f));json_decref(b);
}
static void configure_and_score(void) {
    rc_efficiency_config c;json_t *s;
    s=load("{'weights':{'bias':0.0},'downshift_min':0.8,'veto_below':0.5}");CHECK(rc_efficiency_configure(s,&c));json_decref(s);
    CHECK(c.enabled&&c.downshift_min==0.8&&c.veto_below==0.5);
    json_t *b=load("{'messages':[{'role':'tool','content':'ok'}]}");
    CHECK(NEAR(rc_efficiency_score(&c,b),0.5));
    s=load("{'weights':{'bias':1.0,'log_tool_results':2.0},'downshift_min':0.9}");CHECK(rc_efficiency_configure(s,&c));json_decref(s);
    CHECK(c.veto_below==0.0);
    CHECK(NEAR(rc_efficiency_score(&c,b),1.0/(1.0+exp(-(1.0+2.0*log1p(1))))));
    json_decref(b);
    b=load("{'model':'x'}");CHECK(rc_efficiency_score(&c,b)<0);json_decref(b);
    static const char *bad[]={
        "{'weights':{'last_failed':1},'downshift_min':0.8}",              /* no bias */
        "{'weights':{'bias':1,'mystery':1},'downshift_min':0.8}",         /* unknown feature */
        "{'weights':{'bias':'1'},'downshift_min':0.8}",                   /* not a number */
        "{'weights':{'bias':101},'downshift_min':0.8}",                   /* out of range */
        "{'weights':{'bias':1},'downshift_min':0.4}",
        "{'weights':{'bias':1},'downshift_min':1.1}",
        "{'weights':{'bias':1}}",
        "{'weights':{'bias':1},'downshift_min':0.8,'veto_below':0.9}",    /* veto above add */
        "{'weights':{'bias':1},'downshift_min':0.8,'veto_below':-0.1}",
        "{'weights':{'bias':1},'downshift_min':0.8,'extra':1}",
        "{'weights':[1],'downshift_min':0.8}",
        "[]"};
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++){s=load(bad[i]);CHECK(!rc_efficiency_configure(s,&c));json_decref(s);}
}
int main(void) {
    names();
    basic_counts();
    code_points();
    failures();
    subagent_and_calls();
    configure_and_score();
    puts("efficiency tests passed");
    return 0;
}
