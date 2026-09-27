#define _POSIX_C_SOURCE 200809L
#include "recursant/runtime.h"
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
    rc_config *c=&r->config;
    free(c->listen_host);free(c->private_url);free(c->private_model);free(c->private_key_env);
    free(c->public_url);free(c->public_model);free(c->public_key_env);
    for(size_t i=0;i<c->alias_count;i++){free(c->aliases[i].from);free(c->aliases[i].model);}free(c->aliases);
    free(r->auth_key);free(r->private_key);free(r->public_key);json_decref(r->patterns);memset(r,0,sizeof *r);
}
bool rc_runtime_load(const char *path,bool test,rc_runtime *r,char *err,size_t n) {
    memset(r,0,sizeof *r);r->test_mode=test;
    json_error_t je;json_t *root=json_load_file(path,JSON_REJECT_DUPLICATES,&je),*o,*v;
    rc_config *c=&r->config;size_t num;
    if(!keys(root,"|listen||private||public||aliases||auth||limits||compliance|"))goto bad;
    o=json_object_get(root,"listen");
    if(!keys(o,"|host||port|") || !(c->listen_host=text(o,"host")) || !json_object_get(o,"port") || !number(o,"port",0,65535,&num))goto bad;
    c->listen_port=(long)num;
    struct in_addr bind_addr;
    if(inet_pton(AF_INET,c->listen_host,&bind_addr)!=1)goto bad;
    o=json_object_get(root,"private");
    if(!keys(o,"|url||model||api_key_env|") || !(c->private_url=text(o,"url")) || !(c->private_model=text(o,"model")) || !url_ok(c->private_url,false,test) || !secret(o,"api_key_env",false,&c->private_key_env,&r->private_key))goto bad;
    o=json_object_get(root,"public");
    if(o){if(!keys(o,"|url||model||api_key_env|") || !(c->public_url=text(o,"url")) || !url_ok(c->public_url,true,test) || !secret(o,"api_key_env",true,&c->public_key_env,&r->public_key))goto bad;
        if(json_object_get(o,"model") && !(c->public_model=text(o,"model")))goto bad;}
    o=json_object_get(root,"auth");char *auth_name=NULL;
    if(!keys(o,"|api_key_env|"))goto bad;
    bool auth_ok=secret(o,"api_key_env",true,&auth_name,&r->auth_key);free(auth_name);if(!auth_ok)goto bad;
    o=json_object_get(root,"aliases");if(!json_is_array(o)||json_array_size(o)>256)goto bad;
    c->alias_count=json_array_size(o);c->aliases=calloc(c->alias_count?c->alias_count:1,sizeof *c->aliases);if(!c->aliases)goto bad;
    for(size_t i=0;i<c->alias_count;i++){
        v=json_array_get(o,i);rc_alias *a=&c->aliases[i];char *endpoint=text(v,"endpoint");
        if(!keys(v,"|from||endpoint||model|")||!endpoint){free(endpoint);goto bad;}
        if(!strcmp(endpoint,"private"))a->endpoint=RC_ENDPOINT_PRIVATE;
        else if(!strcmp(endpoint,"public")&&c->public_url)a->endpoint=RC_ENDPOINT_PUBLIC;
        else{free(endpoint);goto bad;}free(endpoint);
        if(!(a->from=text(v,"from"))||!(a->model=text(v,"model")))goto bad;
        for(size_t j=0;j<i;j++)if(!strcmp(a->from,c->aliases[j].from))goto bad;
    }
    /* No identifier may resolve differently as an alias or concrete model. */
    if(c->public_model && !strcmp(c->private_model,c->public_model))goto bad;
    for(size_t i=0;i<c->alias_count;i++) {
        rc_alias *a=&c->aliases[i];
        if((!strcmp(a->from,c->private_model) || !strcmp(a->model,c->private_model)) &&
           (a->endpoint!=RC_ENDPOINT_PRIVATE || strcmp(a->model,c->private_model)))goto bad;
        if(c->public_model && (!strcmp(a->from,c->public_model) || !strcmp(a->model,c->public_model)) &&
           (a->endpoint!=RC_ENDPOINT_PUBLIC || strcmp(a->model,c->public_model)))goto bad;
        for(size_t j=0;j<i;j++) {
            rc_alias *b=&c->aliases[j];
            if((!strcmp(a->from,b->model)||!strcmp(a->model,b->from)||!strcmp(a->model,b->model)) &&
               (a->endpoint!=b->endpoint || strcmp(a->model,b->model)))goto bad;
        }
    }
    o=json_object_get(root,"limits");if(o&&!keys(o,"|max_body_bytes||max_connections||request_timeout_seconds|"))goto bad;
    if(!number(o,"max_body_bytes",1048576,16777216,&r->max_body_bytes)||!number(o,"max_connections",16,256,&num))goto bad;
    r->max_connections=(unsigned)num;
    if(!number(o,"request_timeout_seconds",60,3600,&num))goto bad;
    r->request_timeout_seconds=(unsigned)num;
    o=json_object_get(root,"compliance");
    if(o){if(!keys(o,"|enabled||public_allowed||patterns|"))goto bad;
        v=json_object_get(o,"enabled");if(v&&!json_is_boolean(v))goto bad;r->compliance_enabled=json_is_true(v);
        v=json_object_get(o,"public_allowed");if(v&&!json_is_boolean(v))goto bad;r->public_allowed=json_is_true(v);
        v=json_object_get(o,"patterns");if(v&&!json_is_array(v))goto bad;
        if(v){for(size_t i=0;i<json_array_size(v);i++)if(!json_is_string(json_array_get(v,i)))goto bad;r->patterns=json_incref(v);}
    }
    if(r->compliance_enabled&&!rc_dispatch_gate)goto bad;
    json_decref(root);return true;
bad:
    snprintf(err,n,"invalid runtime configuration");json_decref(root);rc_runtime_free(r);return false;
}
