#define _POSIX_C_SOURCE 200809L
#include "recursant/runtime.h"
#include "recursant/gateway_context.h"
#include "recursant/classifier.h"
#include "recursant/identifiers.h"
#include "recursant/netinfo.h"
#include <curl/curl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <arpa/inet.h>

rc_dispatch_gate_fn rc_dispatch_gate = NULL;
bool rc_runtime_secrets_optional = false;
/* Load is single-threaded (startup or CLI): one reason and one missing-secret
 * list for the most recent load. Names only, never values. */
static char reason[192];
static char missing[RC_RUNTIME_MISSING_MAX][64];
static size_t missing_count;
static bool fail(const char *fmt,...) {
    if(reason[0])return false; /* keep the first, most specific reason */
    va_list ap;va_start(ap,fmt);vsnprintf(reason,sizeof reason,fmt,ap);va_end(ap);return false;
}
const char *rc_runtime_missing_secret(size_t i) { return i<missing_count?missing[i]:NULL; }
const char *rc_runtime_load_reason(void) { return reason; }
/* Allowed-keys check that names the section and the first unknown key. */
static bool section(json_t *o,const char *allowed,const char *name) {
    if (!json_is_object(o)) return fail("%s must be an object",name);
    const char *k; json_t *v;
    json_object_foreach(o,k,v) {
        char token[128];
        if (strchr(k,'|') || snprintf(token,sizeof token,"|%s|",k) >= (int)sizeof token || !strstr(allowed,token))
            return fail("%s: unknown key \"%.48s\"",name,k);
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
    if (!*name) return (!required && !json_object_get(o,k)) || fail("%s must name an environment variable",k);
    for (size_t i=0;(*name)[i];i++) if (!(isalpha((unsigned char)(*name)[i]) || (*name)[i]=='_' || (i && isdigit((unsigned char)(*name)[i])))) return fail("%s: \"%.40s\" is not a valid variable name",k,*name);
    const char *s=getenv(*name);
    if (s && (strchr(s,'\r') || strchr(s,'\n'))) return fail("secret %.48s contains a line break",*name);
    if (!s || !*s) {
        if (!rc_runtime_secrets_optional) return fail("secret not set: %.48s",*name);
        /* Structure check only: a distinct placeholder per variable name, so
         * the distinct-keys rules still hold. */
        bool seen=false;
        for (size_t i=0;i<missing_count;i++) if (!strcmp(missing[i],*name)) seen=true;
        if (!seen && missing_count<RC_RUNTIME_MISSING_MAX) snprintf(missing[missing_count++],sizeof missing[0],"%s",*name);
        size_t n=strlen(*name)+8;*value=malloc(n);
        if (*value) snprintf(*value,n,"unset:%s",*name);
        return *value!=NULL || fail("out of memory");
    }
    *value=strdup(s); return *value!=NULL || fail("out of memory");
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
    if(!json_is_integer(v)||json_integer_value(v)<1||(unsigned long long)json_integer_value(v)>max)return fail("%s must be an integer 1..%zu",k,max);
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
    if(json_object_get(root,"private")||json_object_get(root,"public"))return fail("providers cannot be combined with the legacy private/public sections");
    if(!json_is_array(providers)||!json_array_size(providers))return fail("providers must be a non-empty array");
    if(json_array_size(providers)>RC_PROVIDER_MAX)return fail("providers must not exceed %d entries",RC_PROVIDER_MAX);
    c->provider_count=json_array_size(providers);
    c->providers=calloc(c->provider_count,sizeof *c->providers);
    r->provider_keys=calloc(c->provider_count,sizeof *r->provider_keys);
    if(!c->providers||!r->provider_keys)return fail("out of memory");
    for(size_t i=0;i<c->provider_count;i++){
        v=json_array_get(providers,i);rc_provider *pr=&c->providers[i];
        if(!section(v,"|name||trust||url||key_env||adapter|","provider"))return false;
        if(!(pr->name=text(v,"name"))||!rc_provider_name_ok(pr->name))return fail("provider %zu: name must be an ASCII token of at most %d bytes",i+1,RC_PROVIDER_NAME_MAX);
        if(!(pr->url=text(v,"url")))return fail("provider %s: url is required",pr->name);
        if(!(pr->adapter=text(v,"adapter"))||!rc_provider_adapter_known(pr->adapter))return fail("provider %s: adapter must be openai-compatible or openrouter",pr->name);
        if(eq_text(v,"trust","private"))pr->trust=RC_ENDPOINT_PRIVATE;
        else if(eq_text(v,"trust","public"))pr->trust=RC_ENDPOINT_PUBLIC;
        else return fail("provider %s: trust must be private or public",pr->name);
        if(!url_ok(pr->url,pr->trust==RC_ENDPOINT_PUBLIC,test))
            return fail("provider %s: url must be %s without credentials, query or fragment",pr->name,pr->trust==RC_ENDPOINT_PUBLIC?"https":"http(s)");
        if(!json_object_get(v,"key_env")&&pr->trust==RC_ENDPOINT_PUBLIC)return fail("provider %s: public providers need key_env",pr->name);
        if(!secret(v,"key_env",pr->trust==RC_ENDPOINT_PUBLIC,&pr->key_env,&r->provider_keys[i]))return false;
    }
    o=json_object_get(root,"private_default");
    if(!o)return true;
    if(!section(o,"|provider||model|","private_default"))return false;
    char *name=text(o,"provider");
    if(!name||!(c->private_model=text(o,"model"))){free(name);return fail("private_default needs provider and model");}
    c->private_provider=rc_config_find_provider(c,name);
    if(c->private_provider==RC_PROVIDER_NONE||c->providers[c->private_provider].trust!=RC_ENDPOINT_PRIVATE){
        fail("private_default: %.40s is not a private provider",name);free(name);return false;
    }
    free(name);
    c->has_private_default=true;
    /* Mirror the M2 redirect target into the private_* fields read by the
     * context interpreter; dispatch itself always goes through providers. */
    rc_provider *pd=&c->providers[c->private_provider];
    return ((c->private_url=strdup(pd->url))&&(!pd->key_env||(c->private_key_env=strdup(pd->key_env)))&&
           (!r->provider_keys[c->private_provider]||(r->private_key=strdup(r->provider_keys[c->private_provider]))))||fail("out of memory");
}
/* Legacy form: private (+ optional public) map to implicit providers. */
static bool load_legacy(json_t *root,bool test,rc_runtime *r) {
    rc_config *c=&r->config;json_t *o;
    if(json_object_get(root,"private_default"))return fail("private_default needs the providers form");
    c->provider_count=json_object_get(root,"public")?2:1;
    c->providers=calloc(c->provider_count,sizeof *c->providers);
    r->provider_keys=calloc(c->provider_count,sizeof *r->provider_keys);
    if(!c->providers||!r->provider_keys)return fail("out of memory");
    o=json_object_get(root,"private");
    if(!o)return fail("providers (or the legacy private section) is required");
    if(!section(o,"|url||model||api_key_env|","private"))return false;
    if(!(c->private_url=text(o,"url")) || !(c->private_model=text(o,"model")))return fail("private needs url and model");
    if(!url_ok(c->private_url,false,test))return fail("private.url must be http(s) without credentials, query or fragment");
    if(!secret(o,"api_key_env",false,&c->private_key_env,&r->private_key))return false;
    o=json_object_get(root,"public");
    if(o){if(!section(o,"|url||model||api_key_env||adapter|","public"))return false;
        if(!(c->public_url=text(o,"url")) || !url_ok(c->public_url,true,test))return fail("public.url must be https without credentials, query or fragment");
        if(!secret(o,"api_key_env",true,&c->public_key_env,&r->provider_keys[1]))return false;
        if(json_object_get(o,"model") && !(c->public_model=text(o,"model")))return fail("public.model must be a string");}
    rc_provider *pp=&c->providers[0];pp->trust=RC_ENDPOINT_PRIVATE;
    if(!(pp->name=strdup("private"))||!(pp->url=strdup(c->private_url))||!(pp->adapter=strdup("openai-compatible"))||
       (c->private_key_env&&!(pp->key_env=strdup(c->private_key_env)))||(r->private_key&&!(r->provider_keys[0]=strdup(r->private_key))))return fail("out of memory");
    if(c->public_url){
        rc_provider *pu=&c->providers[1];pu->trust=RC_ENDPOINT_PUBLIC;
        if(!(pu->name=strdup("public"))||!(pu->url=strdup(c->public_url))||!(pu->key_env=strdup(c->public_key_env))||
           !(pu->adapter=strdup(rc_provider_legacy_public_adapter(c->public_url))))return fail("out of memory");
        /* Optional explicit adapter overrides the openrouter.ai host mapping. */
        if(json_object_get(o,"adapter")){
            free(pu->adapter);
            if(!(pu->adapter=text(o,"adapter"))||!rc_provider_adapter_known(pu->adapter))return fail("public.adapter must be openai-compatible or openrouter");
        }
    }
    c->has_private_default=true;c->private_provider=0;return true;
}
bool rc_runtime_load(const char *path,bool test,rc_runtime *r,char *err,size_t n) {
    memset(r,0,sizeof *r);r->test_mode=test;reason[0]=0;missing_count=0;
    json_error_t je;json_t *root=json_load_file(path,JSON_REJECT_DUPLICATES,&je),*o,*v;
    rc_config *c=&r->config;size_t num;
    if(!root){
        /* Position only: jansson's text quotes the config ("near ..."), and
         * config values such as patterns must never reach a log. */
        if(je.line>0)fail("not valid JSON (line %d, column %d)",je.line,je.column);else fail("config file cannot be read");
        goto bad;
    }
    if(!section(root,"|listen||private||public||providers||private_default||aliases||auth||limits||compliance||context|","config root"))goto bad;

    o=json_object_get(root,"listen");
    if(!o){fail("listen section is required");goto bad;}
    if(!section(o,"|host||port|","listen"))goto bad;
    if(!(c->listen_host=text(o,"host"))){fail("listen.host is required");goto bad;}
    if(!json_object_get(o,"port")){fail("listen.port is required");goto bad;}
    if(!number(o,"port",0,65535,&num))goto bad;
    c->listen_port=(long)num;
    /* Symbolic hosts resolve once at load: localhost, any, tailnet. */
    char bind_host[INET_ADDRSTRLEN];
    if(!rc_listen_resolve(c->listen_host,bind_host,sizeof bind_host)){
        if(!strcmp(c->listen_host,"tailnet"))fail("listen.host tailnet: no Tailscale address (100.64.0.0/10) is up on this host");
        else fail("listen.host must be an IPv4 address, localhost, tailnet or any");
        goto bad;
    }
    free(c->listen_host);if(!(c->listen_host=strdup(bind_host))){fail("out of memory");goto bad;}
    json_t *providers=json_object_get(root,"providers");
    bool registry=providers!=NULL;
    if(registry?!load_registry(root,providers,test,r):!load_legacy(root,test,r))goto bad;
    o=json_object_get(root,"auth");char *auth_name=NULL;
    if(!o){fail("auth section is required");goto bad;}
    if(!section(o,"|api_key_env|","auth"))goto bad;
    bool auth_ok=secret(o,"api_key_env",true,&auth_name,&r->auth_key);free(auth_name);if(!auth_ok)goto bad;
    o=json_object_get(root,"aliases");if(!json_is_array(o)||json_array_size(o)>256){fail("aliases must be an array of at most 256 entries");goto bad;}
    c->alias_count=json_array_size(o);c->aliases=calloc(c->alias_count?c->alias_count:1,sizeof *c->aliases);if(!c->aliases){fail("out of memory");goto bad;}
    for(size_t i=0;i<c->alias_count;i++){
        v=json_array_get(o,i);rc_alias *a=&c->aliases[i];
        if(registry){
            /* Provider form: "provider" only; a legacy "endpoint" key is rejected. */
            if(!section(v,"|from||provider||model|","alias"))goto bad;
            char *name=text(v,"provider");
            if(!name){fail("alias %zu: provider is required",i+1);goto bad;}
            a->provider=rc_config_find_provider(c,name);
            if(a->provider==RC_PROVIDER_NONE){fail("alias %zu: unknown provider %.48s",i+1,name);free(name);goto bad;}
            free(name);
        }else{
            if(!section(v,"|from||endpoint||model|","alias"))goto bad;
            char *endpoint=text(v,"endpoint");
            if(!endpoint){fail("alias %zu: endpoint is required",i+1);goto bad;}
            if(!strcmp(endpoint,"private"))a->provider=0;
            else if(!strcmp(endpoint,"public")&&c->public_url)a->provider=1;
            else{free(endpoint);fail("alias %zu: endpoint must be private or a configured public",i+1);goto bad;}
            free(endpoint);
        }
        a->endpoint=c->providers[a->provider].trust;
        if(!(a->from=text(v,"from"))||!(a->model=text(v,"model"))){fail("alias %zu needs from and model",i+1);goto bad;}
        for(size_t j=0;j<i;j++)if(!strcmp(a->from,c->aliases[j].from)){fail("alias %.48s is defined twice",a->from);goto bad;}
    }
    char verr[160];if(!rc_config_validate_providers(c,verr,sizeof verr)){fail("%s",verr);goto bad;}
    /* No identifier may resolve differently as an alias or concrete model;
     * a concrete model name identifies exactly one provider. */
    if(c->private_model && c->public_model && !strcmp(c->private_model,c->public_model)){fail("private and public model names must differ");goto bad;}
    for(size_t i=0;i<c->alias_count;i++) {
        rc_alias *a=&c->aliases[i];
        if((c->private_model && (!strcmp(a->from,c->private_model) || !strcmp(a->model,c->private_model)) &&
            (a->provider!=c->private_provider || strcmp(a->model,c->private_model))) ||
           (c->public_model && (!strcmp(a->from,c->public_model) || !strcmp(a->model,c->public_model)) &&
            (a->endpoint!=RC_ENDPOINT_PUBLIC || strcmp(a->model,c->public_model)))){
            fail("alias %.48s: its name or model resolves to a different provider elsewhere",a->from);goto bad;
        }
        for(size_t j=0;j<i;j++) {
            rc_alias *b=&c->aliases[j];
            if((!strcmp(a->from,b->model)||!strcmp(a->model,b->from)||!strcmp(a->model,b->model)) &&
               (a->provider!=b->provider || strcmp(a->model,b->model))){
                fail("aliases %.40s and %.40s: one model name would resolve to two providers",b->from,a->from);goto bad;
            }
        }
    }
    o=json_object_get(root,"limits");if(o&&!section(o,"|max_body_bytes||max_connections||request_timeout_seconds|","limits"))goto bad;
    if(!number(o,"max_body_bytes",1048576,16777216,&r->max_body_bytes)||!number(o,"max_connections",16,256,&num))goto bad;
    r->max_connections=(unsigned)num;
    if(!number(o,"request_timeout_seconds",60,3600,&num))goto bad;
    r->request_timeout_seconds=(unsigned)num;
    o=json_object_get(root,"compliance");
    r->content_scanning=true;
    if(o){if(!section(o,"|enabled||public_allowed||patterns||content_scanning||text_mode||identifiers|","compliance"))goto bad;
        v=json_object_get(o,"enabled");if(v&&!json_is_boolean(v)){fail("compliance.enabled must be true or false");goto bad;}r->compliance_enabled=json_is_true(v);
        v=json_object_get(o,"public_allowed");if(v&&!json_is_boolean(v)){fail("compliance.public_allowed must be true or false");goto bad;}r->public_allowed=json_is_true(v);
        v=json_object_get(o,"content_scanning");if(v&&!json_is_boolean(v)){fail("compliance.content_scanning must be true or false");goto bad;}if(v)r->content_scanning=json_is_true(v);
        v=json_object_get(o,"text_mode");
        if(v&&!eq_text(o,"text_mode","strict")&&!eq_text(o,"text_mode","agent")){fail("compliance.text_mode must be strict or agent");goto bad;}
        r->agent_text=v&&eq_text(o,"text_mode","agent");
        v=json_object_get(o,"patterns");if(v&&!json_is_array(v)){fail("compliance.patterns must be an array of strings");goto bad;}
        if(v){for(size_t i=0;i<json_array_size(v);i++)if(!json_is_string(json_array_get(v,i))){fail("compliance.patterns must be an array of strings");goto bad;}r->patterns=json_incref(v);}
        /* Personal identifiers to recognise (identifiers.h); only ever stricter. */
        v=json_object_get(o,"identifiers");if(v&&(!json_is_array(v)||!json_array_size(v))){fail("compliance.identifiers must be a non-empty array");goto bad;}
        for(size_t i=0;v&&i<json_array_size(v);i++){
            unsigned bit;if(!rc_identifier_name(json_string_value(json_array_get(v,i)),&bit)||(r->identifiers&bit)){fail("compliance.identifiers: entry %zu is unknown or repeated",i+1);goto bad;}
            r->identifiers|=bit;
        }
    }
    /* M2 redirection must always have a private-trust landing provider. */
    if(r->compliance_enabled&&(!rc_dispatch_gate||!c->has_private_default)){fail("compliance needs a private_default to redirect to");goto bad;}
    o=json_object_get(root,"context");
    if(o && !eq_text(o,"mode","disabled") && !c->has_private_default){fail("context needs a private_default");goto bad;}
    if(o && json_object_get(o,"source_key_env")){
        char *name=NULL;bool ok=secret(o,"source_key_env",true,&name,&r->source_key);free(name);
        if(!ok)goto bad;
        if(!strcmp(r->source_key,r->auth_key)){fail("context.source_key_env must hold a different key than auth.api_key_env");goto bad;}
    }
    if(!rc_gateway_configure(r,o)){fail("context section is invalid (see config/recursant.agent.example.json)");goto bad;}
    json_decref(root);return true;
bad:
    if(reason[0])snprintf(err,n,"invalid runtime configuration: %s",reason);
    else snprintf(err,n,"invalid runtime configuration");
    json_decref(root);rc_runtime_free(r);return false;
}
