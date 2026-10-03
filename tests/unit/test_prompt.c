#include "recursant/prompt.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
#define NEAR(a,b) (fabs((a)-(b))<1e-9)
static json_t *load(const char *text) {
    size_t n=strlen(text);char *t=malloc(n+1);if(!t)exit(1);memcpy(t,text,n+1);
    for(char *p=t;*p;p++)if(*p=='\'')*p='"';
    json_error_t e;json_t *v=json_loads(t,0,&e);free(t);
    if(!v){fprintf(stderr,"fixture: %s\n",e.text);exit(1);}
    return v;
}
static double sigmoid(double z){return 1.0/(1.0+exp(-z));}
static void dense(void) {
    CHECK(RC_PROMPT_DENSE==8&&!strcmp(rc_prompt_names[RC_PROMPT_QUESTION],"question"));
    double f[RC_PROMPT_DENSE];
    const char *t="What is 2+2?\nx = f(y) / 3_a";
    size_t n=strlen(t);
    size_t tokens=rc_prompt_dense(t,n,f);
    /* tokens: what is 2 2 x f y 3 a -> 9 */
    CHECK(tokens==9);
    CHECK(f[RC_PROMPT_BIAS]==1.0&&NEAR(f[RC_PROMPT_LOG_CHARS],log1p((double)n))&&NEAR(f[RC_PROMPT_LOG_LINES],log1p(1)));
    CHECK(NEAR(f[RC_PROMPT_LOG_TOKENS],log1p(9)));
    CHECK(NEAR(f[RC_PROMPT_CODE_FRAC],4.0/(double)n));      /* = ( ) _ */
    CHECK(NEAR(f[RC_PROMPT_DIGIT_FRAC],3.0/(double)n));     /* 2 2 3 */
    CHECK(NEAR(f[RC_PROMPT_OPS_FRAC],2.0/(double)n));       /* + / */
    CHECK(f[RC_PROMPT_QUESTION]==1.0);
    CHECK(rc_prompt_dense("",0,f)==0&&f[RC_PROMPT_LOG_CHARS]==0.0&&f[RC_PROMPT_CODE_FRAC]==0.0);
}
static void scoring(void) {
    rc_prompt_config c;json_t *s=load("{'weights':{'bias':-1.0,'question':0.5},'vocab':{'capital':2.0,'france':1.0,'prove':-3.0},'simple_min':0.8}");
    CHECK(rc_prompt_configure(s,&c));json_decref(s);
    CHECK(c.enabled&&!c.agent_turns&&c.simple_min==0.8);
    /* Distinct tokens count once; case-folded; non-ASCII separates tokens. */
    const char *t="Capital of FRANCE? capital capital";
    CHECK(NEAR(rc_prompt_score_text(&c,t,strlen(t)),sigmoid(-1.0+0.5+2.0+1.0)));
    const char *u="caf\xc3\xa9prove";   /* cafe + prove, split by the non-ASCII bytes */
    CHECK(NEAR(rc_prompt_score_text(&c,u,strlen(u)),sigmoid(-1.0-3.0)));
    /* Tokens longer than RC_PROMPT_TOKEN_MAX never match. */
    char longtok[64];memset(longtok,'a',40);strcpy(longtok+40," prove");
    CHECK(NEAR(rc_prompt_score_text(&c,longtok,strlen(longtok)),sigmoid(-1.0-3.0)));
    /* Bodies: newest message must be a user message. */
    json_t *b=load("{'messages':[{'role':'system','content':'x'},{'role':'user','content':'prove it'}]}");
    CHECK(NEAR(rc_prompt_score(&c,b),sigmoid(-1.0-3.0)));json_decref(b);
    b=load("{'messages':[{'role':'user','content':[{'type':'text','text':'capital'},{'type':'image_url','image_url':{}},{'type':'text','text':'france'}]}]}");
    CHECK(NEAR(rc_prompt_score(&c,b),sigmoid(-1.0+2.0+1.0)));json_decref(b);
    b=load("{'messages':[{'role':'user','content':'capital'},{'role':'tool','content':'france'}]}");
    CHECK(rc_prompt_score(&c,b)<0);json_decref(b);
    b=load("{'messages':[]}");CHECK(rc_prompt_score(&c,b)<0);json_decref(b);
    b=load("{'messages':[{'role':'user','content':null}]}");CHECK(rc_prompt_score(&c,b)<0);json_decref(b);
    /* Only the first RC_PROMPT_TEXT_MAX bytes are read. */
    size_t n=RC_PROMPT_TEXT_MAX+16;char *big=malloc(n+1);CHECK(big);memset(big,' ',n);memcpy(big+RC_PROMPT_TEXT_MAX+2,"prove",5);big[n]=0;
    double f[RC_PROMPT_DENSE];rc_prompt_dense(big,RC_PROMPT_TEXT_MAX,f);
    CHECK(NEAR(rc_prompt_score_text(&c,big,n),sigmoid(-1.0+0.0)));
    free(big);
    rc_prompt_destroy(&c);
}
static void config(void) {
    static const char *bad[]={
        "{'weights':{'question':1},'vocab':{},'simple_min':0.8}",
        "{'weights':{'bias':1,'mystery':1},'vocab':{},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{'Capital':1},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{'a-b':1},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{'':1},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa':1},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{'a':101},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{'a':'1'},'simple_min':0.8}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.3}",
        "{'weights':{'bias':1},'vocab':{}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'agent_turns':'yes'}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'extra':1}",
        "{'weights':{'bias':1},'vocab':[],'simple_min':0.8}",
        /* Encoder sections: strict shape; a model that cannot load fails the config. */
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':[]}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'vocab':'v','weights':[1]}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'m','weights':[1]}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'m','vocab':'v','weights':[]}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'m','vocab':'v','weights':[101]}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'m','vocab':'v','weights':[1],'threads':0}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'m','vocab':'v','weights':[1],'threads':17}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'m','vocab':'v','weights':[1],'extra':1}}",
        "{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'encoder':{'model':'/nonexistent.onnx','vocab':'/nonexistent.txt','weights':[1]}}",
        "[]"};
    rc_prompt_config c;
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++){json_t *s=load(bad[i]);CHECK(!rc_prompt_configure(s,&c));json_decref(s);}
    json_t *s=load("{'weights':{'bias':1},'vocab':{},'simple_min':0.8,'agent_turns':true}");
    CHECK(rc_prompt_configure(s,&c)&&c.agent_turns);json_decref(s);rc_prompt_destroy(&c);
    /* A large vocabulary loads and every entry is found. */
    json_t *vocab=json_object();char k[16];
    for(int i=0;i<5000;i++){snprintf(k,sizeof k,"t%d",i);json_object_set_new(vocab,k,json_real(0.001*i));}
    s=json_pack("{s:{s:f},s:o,s:f}","weights","bias",0.0,"vocab",vocab,"simple_min",0.6);
    CHECK(rc_prompt_configure(s,&c));json_decref(s);
    CHECK(NEAR(rc_prompt_score_text(&c,"t4999 t1",8),sigmoid(4.999+0.001)));
    rc_prompt_destroy(&c);
}
int main(void) {
    dense();
    scoring();
    config();
    puts("prompt tests passed");
    return 0;
}
