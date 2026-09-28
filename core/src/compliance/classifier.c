#define PCRE2_CODE_UNIT_WIDTH 8
#include <pcre2.h>
#include "recursant/classifier.h"
#include "recursant/provider_adapter.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_RULES 32
#define MAX_PATTERN_BYTES 2048
#define MAX_DEPTH 32
#define MAX_NODES 4096
#define MAX_SCAN_BYTES (2U*1024U*1024U)
#define MAX_MATCHES 32768
#define PCRE_BUDGET (2U*1024U*1024U)

typedef struct { size_t used,limit; } budget;
typedef union { max_align_t alignment; size_t size; } allocation;
static void *bounded_alloc(PCRE2_SIZE n,void *ctx) {
    budget *b=ctx;
    if(n>b->limit-b->used || n>SIZE_MAX-sizeof(allocation))return NULL;
    allocation *a=malloc(sizeof *a+n);if(!a)return NULL;
    a->size=n;b->used+=n;return a+1;
}
static void bounded_free(void *ptr,void *ctx) {
    if(!ptr)return;
    allocation *a=(allocation *)ptr-1;budget *b=ctx;b->used-=a->size;free(a);
}
struct rc_compliance_policy {
    budget memory;
    pcre2_code *rules[MAX_RULES+1];
    size_t count;
};
typedef enum { CLEAN, PATTERN, UNKNOWN, REGEX_ERROR, UNSCANNED } verdict;
typedef struct {
    const struct rc_compliance_policy *policy;
    pcre2_match_data *md;
    pcre2_match_context *mc;
    size_t nodes,bytes,matches;
} scanner;

bool rc_compliance_init(rc_runtime *r) {
    if(!r->compliance_enabled)return true;
    if(r->compliance_policy)return false;
    if(!r->content_scanning)
        fprintf(stderr,"compliance_content_scanning=disabled WARNING: regex/PII text scanning is OFF (temporary operator switch); structural M2 checks remain\n");
    size_t count=json_array_size(r->patterns);
    if(count>MAX_RULES)return false;
    struct rc_compliance_policy *p=calloc(1,sizeof *p);
    if(!p)return false;
    r->compliance_policy=p;p->memory.limit=8U*1024U*1024U;
    pcre2_general_context *gc=pcre2_general_context_create(bounded_alloc,bounded_free,&p->memory);
    pcre2_compile_context *cc=gc?pcre2_compile_context_create(gc):NULL;
    if(!cc){pcre2_general_context_free(gc);return false;}
    pcre2_set_parens_nest_limit(cc,64);
    bool ok=true;
    for(size_t i=0;i<=count;i++) {
        const char *pattern=i?json_string_value(json_array_get(r->patterns,i-1)):
            "[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\\.[A-Za-z0-9-]+)+";
        size_t len=i?json_string_length(json_array_get(r->patterns,i-1)):strlen(pattern);
        if(!pattern || !len || len>MAX_PATTERN_BYTES || memchr(pattern,0,len)){ok=false;break;}
        int error;PCRE2_SIZE offset;
        pcre2_code *rule=pcre2_compile((PCRE2_SPTR)pattern,len,0,&error,&offset,cc);
        if(!rule){ok=false;break;}p->rules[p->count++]=rule;
    }
    pcre2_compile_context_free(cc);pcre2_general_context_free(gc);return ok;
}
void rc_compliance_free(rc_runtime *r) {
    struct rc_compliance_policy *p=r->compliance_policy;
    if(!p)return;
    for(size_t i=0;i<p->count;i++)pcre2_code_free(p->rules[i]);
    free(p);r->compliance_policy=NULL;
}

static verdict scan(scanner *,json_t *,unsigned);
static verdict text_scan(scanner *s,const char *text,size_t n,unsigned depth) {
    if(depth>MAX_DEPTH || n>MAX_SCAN_BYTES-s->bytes || memchr(text,0,n))return UNKNOWN;
    s->bytes+=n;
    for(size_t i=0;i<s->policy->count;i++) {
        if(++s->matches>MAX_MATCHES)return UNKNOWN;
        int rc=pcre2_match(s->policy->rules[i],(PCRE2_SPTR)text,n,0,0,s->md,s->mc);
        if(rc>=0)return PATTERN;
        if(rc!=PCRE2_ERROR_NOMATCH)return REGEX_ERROR;
    }
    /* Unsupported remote/encoded media: never fetch or classify remotely. */
    if(strstr(text,"http://") || strstr(text,"https://") || strstr(text,"data:") || strstr(text,"file://"))return UNKNOWN;
    size_t i=0;while(i<n && isspace((unsigned char)text[i]))i++;
    if(i<n && (text[i]=='{' || text[i]=='[' || text[i]=='\"')) {
        json_error_t error;json_t *nested=json_loadb(text,n,JSON_REJECT_DUPLICATES|JSON_DECODE_ANY,&error);
        if(!nested)return UNKNOWN;
        verdict result=scan(s,nested,depth+1);json_decref(nested);return result;
    }
    return CLEAN;
}
static verdict scan(scanner *s,json_t *v,unsigned depth) {
    if(depth>MAX_DEPTH || ++s->nodes>MAX_NODES)return UNKNOWN;
    if(json_is_string(v))return text_scan(s,json_string_value(v),json_string_length(v),depth);
    if(json_is_array(v)) {
        size_t i;json_t *child;json_array_foreach(v,i,child){verdict r=scan(s,child,depth+1);if(r!=CLEAN)return r;}
    }
    if(json_is_object(v)) {
        const char *key;json_t *child;json_object_foreach(v,key,child) {
            verdict r=text_scan(s,key,strlen(key),depth+1);if(r!=CLEAN)return r;
            r=scan(s,child,depth+1);if(r!=CLEAN)return r;
        }
    }
    if(json_is_number(v) || json_is_boolean(v) || json_is_null(v)) {
        char *value=json_dumps(v,JSON_COMPACT|JSON_ENCODE_ANY);
        if(!value)return UNKNOWN;
        verdict result=text_scan(s,value,strlen(value),depth);free(value);return result;
    }
    return CLEAN;
}
static bool known_keys(json_t *o,const char *allowed) {
    if(!json_is_object(o))return false;
    const char *k;json_t *v;
    json_object_foreach(o,k,v) {
        char token[128];
        if(!*k || strchr(k,'|') || strlen(k)>120)return false;
        token[0]='|';strcpy(token+1,k);strcat(token,"|");
        if(!strstr(allowed,token))return false;
    }
    return true;
}
static bool function_call(json_t *call) {
    if(!known_keys(call,"|name||arguments|") || !json_is_string(json_object_get(call,"name")))return false;
    json_t *args=json_object_get(call,"arguments");
    if(!json_is_string(args))return false;
    /* Parsing here verifies format only; recursive scan already decoded it. */
    json_error_t error;
    json_t *parsed=json_loadb(json_string_value(args),json_string_length(args),JSON_REJECT_DUPLICATES,&error);
    bool ok=json_is_object(parsed);json_decref(parsed);return ok;
}
static bool function_definition(json_t *f) {
    return known_keys(f,"|name||description||parameters||strict|") && json_is_string(json_object_get(f,"name"));
}
/* controls: the destination adapter's provider-control allowlist, or NULL
 * when a "provider" object is an unknown (uninspectable) field there. */
static bool inspectable(json_t *body,const char *controls) {
    if(!known_keys(body,"|model||messages||tools||tool_choice||functions||function_call||temperature||top_p||max_tokens||max_completion_tokens||stream||stream_options||stop||seed||frequency_penalty||presence_penalty||logprobs||top_logprobs||logit_bias||n||user||metadata||response_format||reasoning||reasoning_effort||parallel_tool_calls||provider|"))return false;
    json_t *provider=json_object_get(body,"provider");
    if(provider) {
        if(!controls||!known_keys(provider,controls))return false;
        json_t *fallbacks=json_object_get(provider,"allow_fallbacks");
        if(fallbacks && !json_is_boolean(fallbacks))return false;
    }
    json_t *messages=json_object_get(body,"messages");
    if(!json_is_array(messages))return false;
    size_t i;json_t *message;
    json_array_foreach(messages,i,message) {
        if(!known_keys(message,"|role||content||name||tool_calls||tool_call_id||function_call||refusal|"))return false;
        json_t *legacy=json_object_get(message,"function_call");
        if(legacy && !function_call(legacy))return false;
        json_t *calls=json_object_get(message,"tool_calls");
        if(calls) {
            if(!json_is_array(calls))return false;
            size_t j;json_t *call;json_array_foreach(calls,j,call) {
                const char *type=json_string_value(json_object_get(call,"type"));
                if(!known_keys(call,"|id||type||function|") || !type || strcmp(type,"function") || !function_call(json_object_get(call,"function")))return false;
            }
        }
        json_t *content=json_object_get(message,"content");
        if(content && !json_is_null(content) && !json_is_string(content)) {
            if(!json_is_array(content))return false;
            size_t j;json_t *part;
            json_array_foreach(content,j,part) {
                const char *type=json_string_value(json_object_get(part,"type"));
                if(!known_keys(part,"|type||text|") || !type || strcmp(type,"text") || !json_is_string(json_object_get(part,"text")))return false;
            }
        }
    }
    json_t *tools=json_object_get(body,"tools");
    if(tools) {
        if(!json_is_array(tools))return false;
        json_t *tool;json_array_foreach(tools,i,tool) {
            const char *type=json_string_value(json_object_get(tool,"type"));
            if(!known_keys(tool,"|type||function|") || !type || strcmp(type,"function") || !function_definition(json_object_get(tool,"function")))return false;
        }
    }
    json_t *functions=json_object_get(body,"functions");
    if(functions) {
        if(!json_is_array(functions))return false;
        json_t *f;json_array_foreach(functions,i,f)if(!function_definition(f))return false;
    }
    return true;
}
static verdict classify(const rc_runtime *r,json_t *body,const char *controls) {
    /* Temporary operator switch: content text scanning off means only the
     * structural contract decides (unknown fields, non-text parts, provider
     * controls). UNSCANNED is not CLEAN: it is reported distinctly. */
    if(!r->content_scanning)return inspectable(body,controls)?UNSCANNED:UNKNOWN;
    budget memory={.limit=PCRE_BUDGET};
    pcre2_general_context *gc=pcre2_general_context_create(bounded_alloc,bounded_free,&memory);
    scanner s={.policy=r->compliance_policy};
    s.md=gc?pcre2_match_data_create(1,gc):NULL;
    s.mc=gc?pcre2_match_context_create(gc):NULL;
    verdict result=REGEX_ERROR;
    if(s.md && s.mc) {
        pcre2_set_match_limit(s.mc,10000);pcre2_set_depth_limit(s.mc,100);pcre2_set_heap_limit(s.mc,1024);
        result=scan(&s,body,0);
        if(result==CLEAN && !inspectable(body,controls))result=UNKNOWN;
    }
    pcre2_match_data_free(s.md);pcre2_match_context_free(s.mc);pcre2_general_context_free(gc);
    return result;
}
/* Adapter of the provider that would receive (trust, model); NULL when none
 * resolves (router then fails closed) so no gateway-specific leniency applies. */
static const rc_provider_adapter *destination(const rc_runtime *r,json_t *body,rc_endpoint trust) {
    size_t p=rc_runtime_dispatch_provider(r,trust,json_string_value(json_object_get(body,"model")));
    return p==RC_PROVIDER_NONE?NULL:rc_provider_adapter_find(r->config.providers[p].adapter);
}
int rc_compliance_gate(const rc_runtime *r,json_t *body,rc_endpoint *endpoint) {
    if(!r->compliance_enabled)return 0;
    if(!r->compliance_policy)return 1;
    const rc_provider_adapter *adapter=destination(r,body,*endpoint);
    verdict result=classify(r,body,adapter?adapter->provider_control_keys:NULL);
    const char *reason=!r->public_allowed?"policy":result==PATTERN?"pattern":result==UNKNOWN?"unknown":result==REGEX_ERROR?"regex_error":result==UNSCANNED?"unscanned":"clean";
    bool passes=result==CLEAN||result==UNSCANNED;
    if(!r->public_allowed || !passes) {
        if(*endpoint==RC_ENDPOINT_PUBLIC) {
            *endpoint=RC_ENDPOINT_PRIVATE;
            if(json_object_set_new(body,"model",json_string(r->config.private_model)))return 1;
        }
    } else if(*endpoint==RC_ENDPOINT_PUBLIC&&adapter&&adapter->decorate_request) {
        /* Public egress decoration belongs to the destination adapter (e.g.
         * OpenRouter allow_fallbacks=false). Only controls the adapter lists
         * are inspectable; stronger or unknown restrictions were already
         * rejected above and are never discarded to broaden egress. Private
         * destinations and undecorated adapters send the classified object. */
        json_t *original=json_incref(json_object_get(body,"provider"));
        if(adapter->decorate_request(body)){json_decref(original);return 1;}
        /* The exact final public object must itself pass, including controls. */
        result=classify(r,body,adapter->provider_control_keys);
        if(result!=CLEAN&&result!=UNSCANNED) {
            *endpoint=RC_ENDPOINT_PRIVATE;reason="final_policy";
            int restored=original?json_object_set(body,"provider",original):json_object_del(body,"provider");
            if(restored || json_object_set_new(body,"model",json_string(r->config.private_model))){json_decref(original);return 1;}
        }
        json_decref(original);
    }
    fprintf(stderr,"compliance_reason=%s endpoint=%s\n",reason,*endpoint==RC_ENDPOINT_PUBLIC?"public":"private");
    return 0;
}
