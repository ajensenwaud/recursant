#define _POSIX_C_SOURCE 200809L
#include "recursant/runtime.h"
#include "recursant/gateway_context.h"
#include "recursant/classifier.h"
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <arpa/inet.h>

rc_dispatch_gate_fn rc_dispatch_gate = NULL;
static bool keys(json_t *o, const char *allowed) {
    if (!json_is_object(o)) return false;
    const char *k; json_t *v;
    json_object_foreach(o,k,v) {
        char token[128];
        if (strchr(k,'|')) return false;
        if (snprintf(token,sizeof token,"|%s|",k) >= (int)sizeof token || !strstr(allowed,token)) return false;
    }
    return true;
}
static char *text(json_t *o, const char *k) {
    json_t *v=json_object_get(o,k);
    if (!json_is_string(v) || !json_string_length(v) || strlen(json_string_value(v))!=json_string_length(v)) return NULL;
    return strdup(json_string_value(v));
}
static bool eq_text(json_t *o,const char *k,const char *want) {
    json_t *v=json_object_get(o,k);
    return json_is_string(v) && strlen(json_string_value(v))==json_string_length(v) && !strcmp(json_string_value(v),want);
}
static bool secret(json_t *o,const char *k,bool required,char **name,char **value) {
    *name=text(o,k);
    if (!*name) return !required && !json_object_get(o,k);
    for (size_t i=0;(*name)[i];i++) if (!(isalpha((unsigned char)(*name)[i]) || (*name)[i]=='_' || (i && isdigit((unsigned char)(*name)[i])))) return false;
    const char *s=getenv(*name);
    if (!s || !*s || strchr(s,'\r') || strchr(s,'\n')) return false;
    *value=strdup(s); return *value!=NULL;
}
static bool url_ok(const char *s,bool pub,bool test) {
    if (!s || strpbrk(s,"?#") || strstr(s,"@")) return false;
    CURLU *u=curl_url(); char *scheme=NULL,*host=NULL,*user=NULL;
    bool ok=false;
    if (u && curl_url_set(u,CURLUPART_URL,s,0)==CURLUE_OK &&
        curl_url_get(u,CURLUPART_SCHEME,&scheme,0)==CURLUE_OK &&
        curl_url_get(u,CURLUPART_HOST,&host,0)==CURLUE_OK) {
        bool local=!strcmp(host,"127.0.0.1") || !strcmp(host,"[::1]") || !strcmp(host,"localhost");
        ok=(!strcmp(scheme,"https") || (!strcmp(scheme,"http") && (!pub || (test && local)))) &&
           curl_url_get(u,CURLUPART_USER,&user,0)!=CURLUE_OK;
    }
    curl_free(scheme);curl_free(host);curl_free(user);curl_url_cleanup(u);return ok;
}
static bool number(json_t *o,const char *k,size_t def,size_t max,size_t *out) {
    json_t *v=json_object_get(o,k);if(!v){*out=def;return true;}
    if(!json_is_integer(v)||json_integer_value(v)<1||(unsigned long long)json_integer_value(v)>max)return false;
    *out=(size_t)json_integer_value(v);return true;
}
void rc_runtime_free(rc_runtime *r) {
    rc_gateway_destroy(r);
    rc_compliance_free(r);
    rc_config *c=&r->config;
    for(size_t i=0;r->provider_keys&&i<c->provider_count;i++)free(r->provider_keys[i]);
    free(r->provider_keys);
    rc_config_free(c);
    free(r->source_key);free(r->auth_key);free(r->private_key);json_decref(r->patterns);memset(r,0,sizeof *r);
}
size_t rc_runtime_dispatch_provider(const rc_runtime *rt,rc_endpoint trust,const char *model) {
    const rc_config *c=&rt->config;size_t found=RC_PROVIDER_NONE;
    if(!model)return found;
    for(size_t i=0;i<c->alias_count&&found==RC_PROVIDER_NONE;i++)if(!strcmp(c->aliases[i].model,model))found=c->aliases[i].provider;
    if(found==RC_PROVIDER_NONE&&c->has_private_default&&c->private_model&&!strcmp(c->private_model,model))found=c->private_provider;
    /* Legacy public.model without an alias names the implicit "public" provider. */
    if(found==RC_PROVIDER_NONE&&c->public_url&&c->public_model&&!strcmp(c->public_model,model))found=1;
    if(found>=c->provider_count||c->providers[found].trust!=trust)return RC_PROVIDER_NONE;
    return found;
}
/* Named provider form: top-level providers[] plus optional private_default. */
static bool load_registry(json_t *root,json_t *providers,bool test,rc_runtime *r) {
    rc_config *c=&r->config;json_t *v,*o;
    if(json_object_get(root,"private")||json_object_get(root,"public")||!json_is_array(providers)||
       !json_array_size(providers)||json_array_size(providers)>RC_PROVIDER_MAX)return false;
    c->provider_count=json_array_size(providers);
    c->providers=calloc(c->provider_count,sizeof *c->providers);
    r->provider_keys=calloc(c->provider_count,sizeof *r->provider_keys);
    if(!c->providers||!r->provider_keys)return false;
    for(size_t i=0;i<c->provider_count;i++){
        v=json_array_get(providers,i);rc_provider *pr=&c->providers[i];
        if(!keys(v,"|name||trust||url||key_env||adapter|")||!(pr->name=text(v,"name"))||!rc_provider_name_ok(pr->name)||
           !(pr->url=text(v,"url"))||!(pr->adapter=text(v,"adapter"))||!rc_provider_adapter_known(pr->adapter))return false;
        if(eq_text(v,"trust","private"))pr->trust=RC_ENDPOINT_PRIVATE;
        else if(eq_text(v,"trust","public"))pr->trust=RC_ENDPOINT_PUBLIC;
        else return false;
        if(!url_ok(pr->url,pr->trust==RC_ENDPOINT_PUBLIC,test)||
           !secret(v,"key_env",pr->trust==RC_ENDPOINT_PUBLIC,&pr->key_env,&r->provider_keys[i]))return false;
    }
    o=json_object_get(root,"private_default");
    if(!o)return true;
    char *name=NULL;
    if(!keys(o,"|provider||model|")||!(name=text(o,"provider"))||!(c->private_model=text(o,"model"))){free(name);return false;}
    c->private_provider=rc_config_find_provider(c,name);free(name);
    if(c->private_provider==RC_PROVIDER_NONE||c->providers[c->private_provider].trust!=RC_ENDPOINT_PRIVATE)return false;
    c->has_private_default=true;
    /* Mirror the M2 redirect target into the private_* fields read by the
     * context interpreter; dispatch itself always goes through providers. */
    rc_provider *pd=&c->providers[c->private_provider];
    return (c->private_url=strdup(pd->url))&&(!pd->key_env||(c->private_key_env=strdup(pd->key_env)))&&
           (!r->provider_keys[c->private_provider]||(r->private_key=strdup(r->provider_keys[c->private_provider])));
}
/* Legacy form: private (+ optional public) map to implicit providers. */
static bool load_legacy(json_t *root,bool test,rc_runtime *r) {
    rc_config *c=&r->config;json_t *o;
    if(json_object_get(root,"private_default"))return false;
    c->provider_count=json_object_get(root,"public")?2:1;
    c->providers=calloc(c->provider_count,sizeof *c->providers);
    r->provider_keys=calloc(c->provider_count,sizeof *r->provider_keys);
    if(!c->providers||!r->provider_keys)return false;
    o=json_object_get(root,"private");
    if(!keys(o,"|url||model||api_key_env|") || !(c->private_url=text(o,"url")) || !(c->private_model=text(o,"model")) || !url_ok(c->private_url,false,test) || !secret(o,"api_key_env",false,&c->private_key_env,&r->private_key))return false;
    o=json_object_get(root,"public");
    if(o){if(!keys(o,"|url||model||api_key_env||adapter|") || !(c->public_url=text(o,"url")) || !url_ok(c->public_url,true,test) || !secret(o,"api_key_env",true,&c->public_key_env,&r->provider_keys[1]))return false;
        if(json_object_get(o,"model") && !(c->public_model=text(o,"model")))return false;}
    rc_provider *pp=&c->providers[0];pp->trust=RC_ENDPOINT_PRIVATE;
    if(!(pp->name=strdup("private"))||!(pp->url=strdup(c->private_url))||!(pp->adapter=strdup("openai-compatible"))||
       (c->private_key_env&&!(pp->key_env=strdup(c->private_key_env)))||(r->private_key&&!(r->provider_keys[0]=strdup(r->private_key))))return false;
    if(c->public_url){
        rc_provider *pu=&c->providers[1];pu->trust=RC_ENDPOINT_PUBLIC;
        if(!(pu->name=strdup("public"))||!(pu->url=strdup(c->public_url))||!(pu->key_env=strdup(c->public_key_env))||
           !(pu->adapter=strdup(rc_provider_legacy_public_adapter(c->public_url))))return false;
        /* Optional explicit adapter overrides the openrouter.ai host mapping. */
        if(json_object_get(o,"adapter")){
            free(pu->adapter);
            if(!(pu->adapter=text(o,"adapter"))||!rc_provider_adapter_known(pu->adapter))return false;
        }
    }
    c->has_private_default=true;c->private_provider=0;return true;
}
bool rc_runtime_load(const char *path,bool test,rc_runtime *r,char *err,size_t n) {
    memset(r,0,sizeof *r);r->test_mode=test;
    json_error_t je;json_t *root=json_load_file(path,JSON_REJECT_DUPLICATES,&je),*o,*v;
    rc_config *c=&r->config;size_t num;
    if(!keys(root,"|listen||private||public||providers||private_default||aliases||auth||limits||compliance||context|"))goto bad;

    o=json_object_get(root,"listen");
    if(!keys(o,"|host||port|") || !(c->listen_host=text(o,"host")) || !json_object_get(o,"port") || !number(o,"port",0,65535,&num))goto bad;
    c->listen_port=(long)num;
    struct in_addr bind_addr;
    if(inet_pton(AF_INET,c->listen_host,&bind_addr)!=1)goto bad;
    json_t *providers=json_object_get(root,"providers");
    bool registry=providers!=NULL;
    if(registry?!load_registry(root,providers,test,r):!load_legacy(root,test,r))goto bad;
    o=json_object_get(root,"auth");char *auth_name=NULL;
    if(!keys(o,"|api_key_env|"))goto bad;
    bool auth_ok=secret(o,"api_key_env",true,&auth_name,&r->auth_key);free(auth_name);if(!auth_ok)goto bad;
    o=json_object_get(root,"aliases");if(!json_is_array(o)||json_array_size(o)>256)goto bad;
    c->alias_count=json_array_size(o);c->aliases=calloc(c->alias_count?c->alias_count:1,sizeof *c->aliases);if(!c->aliases)goto bad;
    for(size_t i=0;i<c->alias_count;i++){
        v=json_array_get(o,i);rc_alias *a=&c->aliases[i];
        if(registry){
            /* Provider form: "provider" only; a legacy "endpoint" key is rejected. */
            char *name=text(v,"provider");
            if(!keys(v,"|from||provider||model|")||!name){free(name);goto bad;}
            a->provider=rc_config_find_provider(c,name);free(name);
            if(a->provider==RC_PROVIDER_NONE)goto bad;
        }else{
            char *endpoint=text(v,"endpoint");
            if(!keys(v,"|from||endpoint||model|")||!endpoint){free(endpoint);goto bad;}
            if(!strcmp(endpoint,"private"))a->provider=0;
            else if(!strcmp(endpoint,"public")&&c->public_url)a->provider=1;
            else{free(endpoint);goto bad;}free(endpoint);
        }
        a->endpoint=c->providers[a->provider].trust;
        if(!(a->from=text(v,"from"))||!(a->model=text(v,"model")))goto bad;
        for(size_t j=0;j<i;j++)if(!strcmp(a->from,c->aliases[j].from))goto bad;
    }
    char verr[160];if(!rc_config_validate_providers(c,verr,sizeof verr))goto bad;
    /* No identifier may resolve differently as an alias or concrete model;
     * a concrete model name identifies exactly one provider. */
    if(c->private_model && c->public_model && !strcmp(c->private_model,c->public_model))goto bad;
    for(size_t i=0;i<c->alias_count;i++) {
        rc_alias *a=&c->aliases[i];
        if(c->private_model && (!strcmp(a->from,c->private_model) || !strcmp(a->model,c->private_model)) &&
           (a->provider!=c->private_provider || strcmp(a->model,c->private_model)))goto bad;
        if(c->public_model && (!strcmp(a->from,c->public_model) || !strcmp(a->model,c->public_model)) &&
           (a->endpoint!=RC_ENDPOINT_PUBLIC || strcmp(a->model,c->public_model)))goto bad;
        for(size_t j=0;j<i;j++) {
            rc_alias *b=&c->aliases[j];
            if((!strcmp(a->from,b->model)||!strcmp(a->model,b->from)||!strcmp(a->model,b->model)) &&
               (a->provider!=b->provider || strcmp(a->model,b->model)))goto bad;
        }
    }
    o=json_object_get(root,"limits");if(o&&!keys(o,"|max_body_bytes||max_connections||request_timeout_seconds|"))goto bad;
    if(!number(o,"max_body_bytes",1048576,16777216,&r->max_body_bytes)||!number(o,"max_connections",16,256,&num))goto bad;
    r->max_connections=(unsigned)num;
    if(!number(o,"request_timeout_seconds",60,3600,&num))goto bad;
    r->request_timeout_seconds=(unsigned)num;
    o=json_object_get(root,"compliance");
    r->content_scanning=true;
    if(o){if(!keys(o,"|enabled||public_allowed||patterns||content_scanning||text_mode|"))goto bad;
        v=json_object_get(o,"enabled");if(v&&!json_is_boolean(v))goto bad;r->compliance_enabled=json_is_true(v);
        v=json_object_get(o,"public_allowed");if(v&&!json_is_boolean(v))goto bad;r->public_allowed=json_is_true(v);
        v=json_object_get(o,"content_scanning");if(v&&!json_is_boolean(v))goto bad;if(v)r->content_scanning=json_is_true(v);
        v=json_object_get(o,"text_mode");
        if(v&&!eq_text(o,"text_mode","strict")&&!eq_text(o,"text_mode","agent"))goto bad;
        r->agent_text=v&&eq_text(o,"text_mode","agent");
        v=json_object_get(o,"patterns");if(v&&!json_is_array(v))goto bad;
        if(v){for(size_t i=0;i<json_array_size(v);i++)if(!json_is_string(json_array_get(v,i)))goto bad;r->patterns=json_incref(v);}
    }
    /* M2 redirection must always have a private-trust landing provider. */
    if(r->compliance_enabled&&(!rc_dispatch_gate||!c->has_private_default))goto bad;
    o=json_object_get(root,"context");
    if(o && !eq_text(o,"mode","disabled") && !c->has_private_default)goto bad;
    if(o && json_object_get(o,"source_key_env")){
        char *name=NULL;bool ok=secret(o,"source_key_env",true,&name,&r->source_key);free(name);
        if(!ok||!strcmp(r->source_key,r->auth_key))goto bad;
    }
    if(!rc_gateway_configure(r,o))goto bad;
    json_decref(root);return true;
bad:
    snprintf(err,n,"invalid runtime configuration");json_decref(root);rc_runtime_free(r);return false;
}
