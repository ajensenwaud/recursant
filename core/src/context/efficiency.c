#include "recursant/efficiency.h"
#include <math.h>
#include <string.h>

const char *const rc_efficiency_names[RC_EFF_FEATURES]={
    "bias","last_failed","fails_in_last3","failure_run","log_messages","log_tool_results","log_last_len",
    "subagent","repeat_last_call","no_tools_offered",
    "last_call_terminal","last_call_read_file","last_call_write_file","last_call_patch",
    "last_call_search_files","last_call_execute_code","last_call_delegate_task"};

/* Python len(): Unicode code points of valid UTF-8 (jansson guarantees it). */
static size_t code_points(const char *s, size_t n) {
    size_t c=0;for(size_t i=0;i<n;i++)if(((unsigned char)s[i]&0xC0)!=0x80)c++;
    return c;
}
static bool contains(const char *s, size_t n, const char *needle) {
    size_t m=strlen(needle);
    for(size_t i=0;i+m<=n;i++)if(!memcmp(s+i,needle,m))return true;
    return false;
}
static bool contains_ascii_nocase(const char *s, size_t n, const char *needle) {
    size_t m=strlen(needle);
    for(size_t i=0;i+m<=n;i++){
        size_t k=0;
        for(;k<m;k++){unsigned char a=(unsigned char)s[i+k];if(a>='A'&&a<='Z')a=(unsigned char)(a-'A'+'a');if(a!=(unsigned char)needle[k])break;}
        if(k==m)return true;
    }
    return false;
}
/* bench/efficiency/features.py FAIL, searched in the first RC_EFF_SCAN_BYTES:
 * Traceback (most recent call last)|FAILED|ERROR:|Error:|AssertionError|
 * "exit_code": [1-9]|"success": false|"error": "[^"] */
static bool failed(const char *s, size_t n) {
    /* x[:8000] in Python is code points: stop before the 8001st one. */
    size_t points=0;
    for(size_t i=0;i<n;i++)if(((unsigned char)s[i]&0xC0)!=0x80&&++points>RC_EFF_SCAN_BYTES){n=i;break;}
    static const char *const plain[]={"Traceback (most recent call last)","FAILED","ERROR:","Error:","AssertionError","\"success\": false"};
    for(size_t i=0;i<sizeof plain/sizeof *plain;i++)if(contains(s,n,plain[i]))return true;
    static const char exit_code[]="\"exit_code\": ",error[]="\"error\": \"";
    for(size_t i=0;i+sizeof exit_code-1<n;i++)
        if(!memcmp(s+i,exit_code,sizeof exit_code-1)&&s[i+sizeof exit_code-1]>='1'&&s[i+sizeof exit_code-1]<='9')return true;
    for(size_t i=0;i+sizeof error-1<n;i++)
        if(!memcmp(s+i,error,sizeof error-1)&&s[i+sizeof error-1]!='"')return true;
    return false;
}
static const char *role(json_t *m){return json_string_value(json_object_get(m,"role"));}
static bool is(json_t *m,const char *r){const char *x=role(m);return x&&!strcmp(x,r);}
/* Python truthiness of req.get('tools'). */
static bool truthy(json_t *v) {
    if(!v||json_is_null(v)||json_is_false(v))return false;
    if(json_is_array(v))return json_array_size(v)>0;
    if(json_is_object(v))return json_object_size(v)>0;
    if(json_is_string(v))return json_string_length(v)>0;
    if(json_is_integer(v))return json_integer_value(v)!=0;
    if(json_is_real(v))return json_real_value(v)!=0.0;
    return true;
}
bool rc_efficiency_features(const json_t *body, double f[RC_EFF_FEATURES]) {
    json_t *messages=json_object_get(body,"messages");
    if(!json_is_array(messages))return false;
    for(int i=0;i<RC_EFF_FEATURES;i++)f[i]=0.0;
    size_t n=json_array_size(messages),tools=0,run=0;
    const char *last=NULL;size_t last_len=0;
    /* Failure flags of the last three results, oldest first, and the trailing run. */
    bool window[3]={false,false,false};size_t seen=0;
    const char *system=NULL;size_t system_len=0;
    json_t *first_user=NULL;bool have_user=false;
    const char *call_last=NULL,*call_prev=NULL;size_t calls=0;
    for(size_t i=0;i<n;i++){
        json_t *m=json_array_get(messages,i);
        if(is(m,"tool")){
            json_t *c=json_object_get(m,"content");
            const char *s=json_is_string(c)?json_string_value(c):"";size_t len=json_is_string(c)?json_string_length(c):0;
            bool bad=failed(s,len);
            tools++;last=s;last_len=len;
            window[0]=window[1];window[1]=window[2];window[2]=bad;seen++;
            run=bad?run+1:0;
        }
        else if(is(m,"system")&&!system){
            json_t *c=json_object_get(m,"content");
            /* Python: next(content of the first system message) or '' */
            system=json_is_string(c)?json_string_value(c):"";system_len=json_is_string(c)?json_string_length(c):0;
        }
        else if(is(m,"user")&&!have_user){have_user=true;first_user=json_object_get(m,"content");}
        else if(is(m,"assistant")){
            json_t *list=json_object_get(m,"tool_calls");
            for(size_t k=0;k<json_array_size(list);k++){
                call_prev=call_last;
                call_last=json_string_value(json_object_get(json_object_get(json_array_get(list,k),"function"),"name"));
                calls++;
            }
        }
    }
    f[RC_EFF_BIAS]=1.0;
    size_t w=seen<3?seen:3;
    f[RC_EFF_LAST_FAILED]=w&&window[2]?1.0:0.0;
    for(size_t i=3-w;i<3;i++)if(window[i])f[RC_EFF_FAILS_IN_LAST3]+=1.0;
    f[RC_EFF_FAILURE_RUN]=(double)(run<3?run:3);
    f[RC_EFF_LOG_MESSAGES]=log1p((double)n);
    f[RC_EFF_LOG_TOOL_RESULTS]=log1p((double)tools);
    f[RC_EFF_LOG_LAST_LEN]=log1p((double)(last?code_points(last,last_len):0));
    /* 'subagent' in system.lower() or len(first_user) < 600 and 'delegat' in system.lower().
     * first_user: content string (code points), a list (its length), else ''. */
    size_t user_len=0;
    if(json_is_string(first_user))user_len=code_points(json_string_value(first_user),json_string_length(first_user));
    else if(json_is_array(first_user))user_len=json_array_size(first_user);
    if(system&&(contains_ascii_nocase(system,system_len,"subagent")||(user_len<600&&contains_ascii_nocase(system,system_len,"delegat"))))
        f[RC_EFF_SUBAGENT]=1.0;
    if(calls>=2&&((!call_last&&!call_prev)||(call_last&&call_prev&&!strcmp(call_last,call_prev))))f[RC_EFF_REPEAT_LAST_CALL]=1.0;
    f[RC_EFF_NO_TOOLS_OFFERED]=truthy(json_object_get(body,"tools"))?0.0:1.0;
    if(calls&&call_last)
        for(int i=RC_EFF_LAST_TERMINAL;i<RC_EFF_FEATURES;i++)
            if(!strcmp(call_last,rc_efficiency_names[i]+strlen("last_call_")))f[i]=1.0;
    return true;
}
double rc_efficiency_score(const rc_efficiency_config *cfg, const json_t *body) {
    double f[RC_EFF_FEATURES];
    if(!rc_efficiency_features(body,f))return -1.0;
    double z=0;for(int i=0;i<RC_EFF_FEATURES;i++)z+=cfg->weights[i]*f[i];
    z=z>30?30:z<-30?-30:z;
    return 1.0/(1.0+exp(-z));
}
static bool number(json_t *v,double lo,double hi,double *out) {
    if(!json_is_number(v))return false;
    double x=json_number_value(v);
    if(!isfinite(x)||x<lo||x>hi)return false;
    *out=x;return true;
}
bool rc_efficiency_configure(json_t *section, rc_efficiency_config *out) {
    if(!json_is_object(section))return false;
    const char *k;json_t *v;
    json_object_foreach(section,k,v)if(strcmp(k,"weights")&&strcmp(k,"downshift_min")&&strcmp(k,"veto_below"))return false;
    rc_efficiency_config c={.enabled=true};
    json_t *weights=json_object_get(section,"weights");
    if(!json_is_object(weights)||!json_object_get(weights,"bias"))return false;
    json_object_foreach(weights,k,v){
        int i=0;for(;i<RC_EFF_FEATURES&&strcmp(k,rc_efficiency_names[i]);i++);
        if(i==RC_EFF_FEATURES||!number(v,-100,100,&c.weights[i]))return false;
    }
    if(!number(json_object_get(section,"downshift_min"),0.5,1.0,&c.downshift_min))return false;
    json_t *veto=json_object_get(section,"veto_below");
    if(veto&&!number(veto,0.0,c.downshift_min,&c.veto_below))return false;
    *out=c;return true;
}
