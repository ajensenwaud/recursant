#include "recursant/prompt.h"
#include "recursant/encoder.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *const rc_prompt_names[RC_PROMPT_DENSE]={
    "bias","log_chars","log_lines","log_tokens","code_frac","digit_frac","ops_frac","question"};

struct rc_prompt_vocab {
    size_t mask, count;   /* open addressing, capacity mask+1 (power of two) */
    char (*keys)[RC_PROMPT_TOKEN_MAX+1];
    double *weights;
    uint32_t *slots;      /* 0 empty, else entry index + 1 */
};

static uint64_t hash(const char *s, size_t n) {
    uint64_t h=UINT64_C(1469598103934665603);
    for(size_t i=0;i<n;i++){h^=(unsigned char)s[i];h*=UINT64_C(1099511628211);}
    return h;
}
static long lookup(const rc_prompt_vocab *v, const char *s, size_t n) {
    if(!v||!v->count)return -1;
    for(size_t i=hash(s,n)&v->mask;;i=(i+1)&v->mask){
        uint32_t e=v->slots[i];if(!e)return -1;
        if(!strncmp(v->keys[e-1],s,n)&&!v->keys[e-1][n])return (long)(e-1);
    }
}
static bool weight(json_t *v, double *out) {
    if(!json_is_number(v))return false;
    double w=json_number_value(v);
    if(!isfinite(w)||fabs(w)>100)return false;
    *out=w;return true;
}
static bool token_ok(const char *k) {
    size_t n=strlen(k);
    if(!n||n>RC_PROMPT_TOKEN_MAX)return false;
    for(size_t i=0;i<n;i++)if(!((k[i]>='a'&&k[i]<='z')||(k[i]>='0'&&k[i]<='9')))return false;
    return true;
}
void rc_prompt_destroy(rc_prompt_config *c) {
    if(!c)return;
    rc_encoder_free(c->encoder);c->encoder=NULL;free(c->encoder_weights);c->encoder_weights=NULL;c->encoder_dim=0;
    if(!c->vocab)return;
    free(c->vocab->keys);free(c->vocab->weights);free(c->vocab->slots);free(c->vocab);c->vocab=NULL;
}
static bool encoder_configure(json_t *s, rc_prompt_config *c) {
    if(!json_is_object(s))return false;
    const char *key;json_t *v;
    json_object_foreach(s,key,v)
        if(strcmp(key,"model")&&strcmp(key,"vocab")&&strcmp(key,"threads")&&strcmp(key,"weights"))return false;
    json_t *model=json_object_get(s,"model"),*vocab=json_object_get(s,"vocab"),*threads=json_object_get(s,"threads"),*w=json_object_get(s,"weights");
    if(!json_is_string(model)||!json_is_string(vocab)||!json_is_array(w)||!json_array_size(w))return false;
    if(threads&&(!json_is_integer(threads)||json_integer_value(threads)<1||json_integer_value(threads)>16))return false;
    size_t n=json_array_size(w);
    double *weights=malloc(n*sizeof *weights);if(!weights)return false;
    for(size_t i=0;i<n;i++)if(!weight(json_array_get(w,i),&weights[i])){free(weights);return false;}
    char err[256];
    rc_encoder *enc=rc_encoder_load(json_string_value(model),json_string_value(vocab),threads?(int)json_integer_value(threads):1,err,sizeof err);
    if(!enc){fprintf(stderr,"context.prompt.encoder: %s\n",err);free(weights);return false;}
    if(rc_encoder_dim(enc)!=n){
        fprintf(stderr,"context.prompt.encoder: %zu weights for a %zu-dimensional model\n",n,rc_encoder_dim(enc));
        rc_encoder_free(enc);free(weights);return false;
    }
    c->encoder=enc;c->encoder_weights=weights;c->encoder_dim=n;
    return true;
}
bool rc_prompt_configure(json_t *s, rc_prompt_config *out) {
    if(!json_is_object(s)||!out)return false;
    rc_prompt_config c;memset(&c,0,sizeof c);
    const char *key;json_t *v;
    json_object_foreach(s,key,v)
        if(strcmp(key,"weights")&&strcmp(key,"vocab")&&strcmp(key,"simple_min")&&strcmp(key,"agent_turns")&&strcmp(key,"encoder"))return false;
    json_t *w=json_object_get(s,"weights"),*vocab=json_object_get(s,"vocab"),*min=json_object_get(s,"simple_min"),*agent=json_object_get(s,"agent_turns");
    if(!json_is_object(w)||!json_is_object(vocab)||!json_is_number(min))return false;
    if(agent&&!json_is_boolean(agent))return false;
    c.agent_turns=json_is_true(agent);
    c.simple_min=json_number_value(min);
    if(!(c.simple_min>=0.5&&c.simple_min<=1.0))return false;
    bool have_bias=false;
    json_object_foreach(w,key,v){
        size_t i=0;while(i<RC_PROMPT_DENSE&&strcmp(rc_prompt_names[i],key))i++;
        if(i==RC_PROMPT_DENSE||!weight(v,&c.weights[i]))return false;
        if(i==RC_PROMPT_BIAS)have_bias=true;
    }
    if(!have_bias)return false;
    size_t n=json_object_size(vocab);
    if(n>RC_PROMPT_VOCAB_MAX)return false;
    json_object_foreach(vocab,key,v){double x;if(!token_ok(key)||!weight(v,&x))return false;}
    rc_prompt_vocab *t=calloc(1,sizeof *t);if(!t)return false;
    size_t cap=16;while(cap<2*n)cap<<=1;
    t->mask=cap-1;t->keys=calloc(n?n:1,sizeof *t->keys);t->weights=calloc(n?n:1,sizeof *t->weights);t->slots=calloc(cap,sizeof *t->slots);
    if(!t->keys||!t->weights||!t->slots){c.vocab=t;rc_prompt_destroy(&c);return false;}
    json_object_foreach(vocab,key,v){
        size_t len=strlen(key),e=t->count++;
        memcpy(t->keys[e],key,len+1);weight(v,&t->weights[e]);
        size_t i=hash(key,len)&t->mask;while(t->slots[i])i=(i+1)&t->mask;
        t->slots[i]=(uint32_t)(e+1);
    }
    c.vocab=t;
    json_t *enc=json_object_get(s,"encoder");
    if(enc&&!encoder_configure(enc,&c)){rc_prompt_destroy(&c);return false;}
    c.enabled=true;*out=c;
    return true;
}

static bool alnum(unsigned char ch){return (ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9');}
size_t rc_prompt_dense(const char *text, size_t n, double f[RC_PROMPT_DENSE]) {
    if(n>RC_PROMPT_TEXT_MAX)n=RC_PROMPT_TEXT_MAX;
    size_t lines=0,code=0,digits=0,ops=0,tokens=0;bool question=false,in=false;
    for(size_t i=0;i<n;i++){
        unsigned char ch=(unsigned char)text[i];
        if(ch=='\n')lines++;
        if(ch=='?')question=true;
        if(ch>='0'&&ch<='9')digits++;
        if(ch&&strchr("{}[]()=;_`\\#<>",ch))code++;
        if(ch&&strchr("+-*/^%",ch))ops++;
        bool a=alnum(ch);if(a&&!in)tokens++;in=a;
    }
    double d=n?(double)n:1.0;
    f[RC_PROMPT_BIAS]=1.0;f[RC_PROMPT_LOG_CHARS]=log1p((double)n);f[RC_PROMPT_LOG_LINES]=log1p((double)lines);
    f[RC_PROMPT_LOG_TOKENS]=log1p((double)tokens);f[RC_PROMPT_CODE_FRAC]=n?(double)code/d:0.0;
    f[RC_PROMPT_DIGIT_FRAC]=n?(double)digits/d:0.0;f[RC_PROMPT_OPS_FRAC]=n?(double)ops/d:0.0;
    f[RC_PROMPT_QUESTION]=question?1.0:0.0;
    return tokens;
}
double rc_prompt_score_text(const rc_prompt_config *c, const char *text, size_t n) {
    if(!c||!c->enabled||!text)return -1;
    if(n>RC_PROMPT_TEXT_MAX)n=RC_PROMPT_TEXT_MAX;
    double f[RC_PROMPT_DENSE];rc_prompt_dense(text,n,f);
    double z=0;for(size_t i=0;i<RC_PROMPT_DENSE;i++)z+=c->weights[i]*f[i];
    unsigned char seen[(RC_PROMPT_VOCAB_MAX+7)/8];memset(seen,0,sizeof seen);
    char tok[RC_PROMPT_TOKEN_MAX];
    for(size_t i=0;i<n;){
        if(!alnum((unsigned char)text[i])){i++;continue;}
        size_t j=i;while(j<n&&alnum((unsigned char)text[j]))j++;
        size_t len=j-i;
        if(len<=RC_PROMPT_TOKEN_MAX){
            for(size_t k=0;k<len;k++){char ch=text[i+k];tok[k]=(ch>='A'&&ch<='Z')?(char)(ch+32):ch;}
            long e=lookup(c->vocab,tok,len);
            if(e>=0&&!(seen[e/8]&(1u<<(e%8)))){seen[e/8]|=(unsigned char)(1u<<(e%8));z+=c->vocab->weights[e];}
        }
        i=j;
    }
    if(c->encoder){
        float e[1024];
        if(c->encoder_dim>sizeof e/sizeof *e||!rc_encoder_embed(c->encoder,text,n,e))return -1;
        for(size_t i=0;i<c->encoder_dim;i++)z+=c->encoder_weights[i]*(double)e[i];
    }
    return 1.0/(1.0+exp(-z));
}
double rc_prompt_score(const rc_prompt_config *c, const json_t *body) {
    json_t *m=json_object_get(body,"messages");size_t count=json_array_size(m);
    if(!c||!c->enabled||!count)return -1;
    json_t *last=json_array_get(m,count-1);
    const char *role=json_string_value(json_object_get(last,"role"));
    if(!role||strcmp(role,"user"))return -1;
    json_t *content=json_object_get(last,"content");
    if(json_is_string(content))return rc_prompt_score_text(c,json_string_value(content),json_string_length(content));
    if(!json_is_array(content))return -1;
    char *buf=malloc(RC_PROMPT_TEXT_MAX);if(!buf)return -1;
    size_t used=0;bool any=false;size_t i;json_t *part;
    json_array_foreach(content,i,part){
        const char *type=json_string_value(json_object_get(part,"type"));json_t *t=json_object_get(part,"text");
        if(!type||strcmp(type,"text")||!json_is_string(t))continue;
        if(any&&used<RC_PROMPT_TEXT_MAX)buf[used++]='\n';
        size_t len=json_string_length(t);if(len>RC_PROMPT_TEXT_MAX-used)len=RC_PROMPT_TEXT_MAX-used;
        memcpy(buf+used,json_string_value(t),len);used+=len;any=true;
    }
    double p=any?rc_prompt_score_text(c,buf,used):-1;
    free(buf);return p;
}
