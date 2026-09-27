#include "recursant/response_observer.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *first="data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"café 🦀\"},\"finish_reason\":null}]}\n\n";
static const char *last="data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n";
static void feed(rc_response_observer *o,const char *s){rc_response_observer_feed(o,s,strlen(s));}
static void reject_metadata(void) {
    const char *bad[]={"\"id\":{}", "\"model\":{}", "\"object\":\"response\"", "\"created\":true",
        "\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"prompt_tokens_details\":{\"opaque\":0}}",
        "\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"completion_tokens_details\":{\"reasoning_tokens\":true}}",
        "\"usage\":{\"prompt_tokens\":-1,\"completion_tokens\":1,\"total_tokens\":2}",
        "\"id\":\"first\",\"id\":\"duplicate\""};
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        char data[512];snprintf(data,sizeof data,"data: {%s,\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"text\"},\"finish_reason\":null}]}\n\n",bad[i]);
        feed(o,data);feed(o,last);
        json_t *m=rc_response_observer_message(o);
        if(m)fprintf(stderr,"accepted malformed/opaque metadata: %s\n",bad[i]);
        assert(!m);free(o);
    }
}
static void every_split(void) {
    char wire[1024];snprintf(wire,sizeof wire,"%s%s",first,last);
    for(size_t split=0;split<=strlen(wire);split++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        rc_response_observer_feed(o,wire,split);rc_response_observer_feed(o,wire+split,strlen(wire)-split);
        json_t *m=rc_response_observer_message(o);assert(m);
        assert(!strcmp(json_string_value(json_object_get(m,"content")),"café 🦀"));json_decref(m);free(o);
    }
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    for(size_t i=0;i<strlen(wire);i++){
        rc_response_observer_feed(o,wire+i,1);
        if(i+1<strlen(wire))assert(!rc_response_observer_message(o));
    }
    json_t *m=rc_response_observer_message(o);assert(m);json_decref(m);free(o);
}
static void mixed_identity(void) {
    const char *names[]={"id","model","created"};
    for(size_t i=0;i<3;i++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        char data[512];
        snprintf(data,sizeof data,"data: {\"%s\":%s,\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\"},\"finish_reason\":null}]}\n\n",names[i],i==2?"1":"\"one\"");feed(o,data);
        snprintf(data,sizeof data,"data: {\"%s\":%s,\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n",names[i],i==2?"2":"\"two\"");feed(o,data);
        json_t *m=rc_response_observer_message(o);
        if(m)fprintf(stderr,"accepted mixed generation %s\n",names[i]);
        assert(!m);free(o);
    }
}
static void framing_and_bounds(void) {
    const char *wire=": keepalive\r\ndata: {\"choices\":\r\ndata: [{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"café 🦀\"},\"finish_reason\":\"stop\"}]}\r\n\r\ndata: [DONE]\r\n\r\n";
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    for(size_t i=0;i<strlen(wire);i++)rc_response_observer_feed(o,wire+i,1);
    json_t *m=rc_response_observer_message(o);assert(m);
    assert(!strcmp(json_string_value(json_object_get(m,"content")),"café 🦀"));json_decref(m);
    memset(o,0,sizeof *o);
    char *full=malloc(RC_RESPONSE_LIMIT);assert(full);
    size_t pad=RC_RESPONSE_LIMIT-strlen(first)-strlen(last);
    memset(full,'x',pad);full[0]=':';full[pad-2]='\n';full[pad-1]='\n';
    memcpy(full+pad,first,strlen(first));memcpy(full+pad+strlen(first),last,strlen(last));
    rc_response_observer_feed(o,full,RC_RESPONSE_LIMIT);
    m=rc_response_observer_message(o);assert(m);json_decref(m);
    feed(o,"\n");assert(!rc_response_observer_message(o));feed(o,first);feed(o,last);assert(!rc_response_observer_message(o));
    free(full);free(o);
}
static void invalid_comment_utf8(void) {
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    feed(o,": invalid \xff\n\n");feed(o,first);feed(o,last);
    assert(!rc_response_observer_message(o));free(o);
}
/* Synthetic values, observed OpenRouter shape; not a captured wire fixture. */
static const char *or_first=
    "data: {\"id\":\"synthetic\",\"object\":\"chat.completion.chunk\",\"created\":1,"
    "\"model\":\"synthetic-model\",\"provider\":\"OpenAI\",\"choices\":[{\"index\":0,"
    "\"delta\":{\"content\":\"fixture café\",\"role\":\"assistant\"},"
    "\"finish_reason\":null,\"native_finish_reason\":null}]}\n\n";
static const char *or_stop=
    "data: {\"id\":\"synthetic\",\"object\":\"chat.completion.chunk\",\"created\":1,"
    "\"model\":\"synthetic-model\",\"provider\":\"OpenAI\",\"choices\":[{\"index\":0,"
    "\"delta\":{\"content\":\"\",\"role\":\"assistant\"},"
    "\"finish_reason\":\"stop\",\"native_finish_reason\":\"completed\"}]}\n\n";
static void openrouter_metadata(void) {
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    feed(o,or_first);feed(o,or_stop);feed(o,"data: [DONE]\n\n");
    json_t *m=rc_response_observer_message(o);assert(m);
    assert(!strcmp(json_string_value(json_object_get(m,"content")),"fixture café"));
    json_decref(m);free(o);
}
static const char *or_usage=
    "{\"prompt_tokens\":7,\"completion_tokens\":3,\"total_tokens\":10,"
    "\"cost\":0.00002,\"is_byok\":false,"
    "\"prompt_tokens_details\":{\"cached_tokens\":0,\"cache_write_tokens\":0,\"audio_tokens\":0,\"video_tokens\":0},"
    "\"completion_tokens_details\":{\"reasoning_tokens\":0,\"image_tokens\":0,\"audio_tokens\":0},"
    "\"cost_details\":{\"upstream_inference_cost\":0.00002,\"upstream_inference_prompt_cost\":0.00001,"
    "\"upstream_inference_completions_cost\":0.00001}}";
static json_t *usage_tail(void) {
    json_error_t error;
    json_t *tail=json_loads(or_stop+6,JSON_REJECT_DUPLICATES,&error);assert(tail);
    assert(!json_object_set_new(tail,"service_tier",json_string("default")));
    json_t *u=json_loads(or_usage,JSON_REJECT_DUPLICATES,&error);assert(u);
    assert(!json_object_set_new(tail,"usage",u));return tail;
}
static void feed_json(rc_response_observer *o,json_t *v) {
    char *s=json_dumps(v,JSON_COMPACT);assert(s);
    feed(o,"data: ");feed(o,s);feed(o,"\n\n");free(s);
}
static void openrouter_usage_tail(void) {
    json_t *tail=usage_tail();char *s=json_dumps(tail,JSON_COMPACT);assert(s);
    char wire[4096];int n=snprintf(wire,sizeof wire,"%s%sdata: %s\n\ndata: [DONE]\n\n",or_first,or_stop,s);
    assert(n>0&&(size_t)n<sizeof wire);
    for(size_t split=0;split<=(size_t)n;split++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        rc_response_observer_feed(o,wire,split);rc_response_observer_feed(o,wire+split,(size_t)n-split);
        json_t *m=rc_response_observer_message(o);assert(m);
        assert(!strcmp(json_string_value(json_object_get(m,"content")),"fixture café"));
        json_decref(m);free(o);
    }
    free(s);json_decref(tail);
}
/* Replace one field in a valid observed-shape accounting tail. */
static void reject_openrouter_metadata(void) {
    struct bad {const char *where,*key,*value;} bad[]={
        {"root","provider","null"},{"root","provider","\"\""},
        {"root","provider","\"Different\""},{"root","provider","7"},
        {"root","provider","\"OpenAI\\u0000suffix\""},
        {"root","service_tier","{}"},{"root","service_tier","\"unknown\""},
        {"root","opaque","null"},{"root","","null"},{"root","provider|id","null"},
        {"root","kv_transfer_params","{}"},{"root","metrics","{}"},
        {"choice","native_finish_reason","\"length\""},{"choice","native_finish_reason","0"},
        {"choice","finish_reason","null"},{"choice","finish_reason","\"length\""},
        {"choice","finish_reason","\"tool_calls\""},{"choice","index","1"},
        {"choice","opaque","null"},{"choice","","null"},{"choice","index|delta","null"},
        {"delta","content","\"more\""},{"delta","content","false"},
        {"delta","role","\"user\""},{"delta","role","null"},
        {"delta","tool_calls","[]"},{"delta","reasoning","\"state\""},
        {"delta","function_call","{}"},{"delta","annotations","[]"},
        {"usage","cost","-1"},{"usage","cost","true"},{"usage","cost","\"0\""},
        {"usage","cost","null"},{"usage","is_byok","0"},{"usage","is_byok","null"},
        {"usage","cost_details","null"},{"usage","cost_details","[]"},
        {"usage","opaque","0"},{"usage","","0"},{"usage","cost|is_byok","0"},
        {"prompt_tokens_details","cache_write_tokens","-1"},{"prompt_tokens_details","video_tokens","0.5"},
        {"prompt_tokens_details","cached_tokens","false"},{"prompt_tokens_details","opaque","0"},
        {"prompt_tokens_details","","0"},{"prompt_tokens_details","cached_tokens|audio_tokens","0"},
        {"completion_tokens_details","image_tokens","null"},{"completion_tokens_details","opaque","0"},
        {"completion_tokens_details","","0"},{"completion_tokens_details","image_tokens|audio_tokens","0"},
        {"cost_details","upstream_inference_cost","-0.001"},
        {"cost_details","upstream_inference_prompt_cost","false"},
        {"cost_details","upstream_inference_completions_cost","\"0.001\""},
        {"cost_details","opaque","0"},{"cost_details","","0"},
        {"cost_details","upstream_inference_cost|upstream_inference_prompt_cost","0"}
    };
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++){
        json_t *tail=usage_tail(),*u=json_object_get(tail,"usage");
        json_t *choice=json_array_get(json_object_get(tail,"choices"),0),*target;
        if(!strcmp(bad[i].where,"root"))target=tail;
        else if(!strcmp(bad[i].where,"choice"))target=choice;
        else if(!strcmp(bad[i].where,"delta"))target=json_object_get(choice,"delta");
        else if(!strcmp(bad[i].where,"usage"))target=u;
        else target=json_object_get(u,bad[i].where);
        json_error_t error;json_t *value=json_loads(bad[i].value,JSON_DECODE_ANY|JSON_ALLOW_NUL,&error);assert(value);
        assert(!json_object_set_new(target,bad[i].key,value));
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        feed(o,or_first);feed(o,or_stop);feed_json(o,tail);feed(o,"data: [DONE]\n\n");
        json_t *m=rc_response_observer_message(o);
        if(m)fprintf(stderr,"accepted %s.%s=%s\n",bad[i].where,bad[i].key,bad[i].value);
        assert(!m);free(o);json_decref(tail);
    }
}
static void terminal_guards(void) {
    for(int mode=0;mode<12;mode++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        json_t *tail=usage_tail();feed(o,or_first);
        if(mode!=0)feed(o,or_stop);
        switch(mode){
        case 0: feed(o,"data: [DONE]\n\n");break; /* early DONE */
        case 1: feed_json(o,tail);break; /* missing DONE */
        case 2: feed(o,or_stop);feed(o,"data: [DONE]\n\n");break; /* duplicate stop */
        case 3: feed_json(o,tail);feed_json(o,tail);feed(o,"data: [DONE]\n\n");break;
        case 4: feed_json(o,tail);feed(o,"data: [DONE]\n\ndata: [DONE]\n\n");break;
        case 5: feed(o,"data: [DONE]\n\n");feed_json(o,tail);break;
        case 6: json_object_del(tail,"usage");feed_json(o,tail);feed(o,"data: [DONE]\n\n");break;
        case 7: json_object_set_new(tail,"usage",json_null());feed_json(o,tail);feed(o,"data: [DONE]\n\n");break;
        case 8: { /* native completion cannot precede normalized completion */
            memset(o,0,sizeof *o);
            json_t *choice=json_array_get(json_object_get(tail,"choices"),0);
            json_object_set_new(choice,"finish_reason",json_null());
            feed_json(o,tail);feed(o,or_stop);feed(o,"data: [DONE]\n\n");break;
        }
        case 9: { /* terminal native reason cannot change */
            json_t *choice=json_array_get(json_object_get(tail,"choices"),0);
            json_object_set_new(choice,"native_finish_reason",json_null());
            feed_json(o,tail);feed(o,"data: [DONE]\n\n");break;
        }
        case 10: /* duplicate metadata key remains invalid */
            feed(o,"data: {\"provider\":\"OpenAI\",\"provider\":\"OpenAI\",\"choices\":[],\"usage\":");
            feed(o,or_usage);feed(o,"}\n\ndata: [DONE]\n\n");break;
        case 11: /* no continuation after even a valid empty-choices tail */
            json_object_set_new(tail,"choices",json_array());feed_json(o,tail);
            feed(o,or_stop);feed(o,"data: [DONE]\n\n");break;
        }
        assert(!rc_response_observer_message(o));free(o);json_decref(tail);
    }
    const char *bad_numbers[]={"1e9999","-1e9999","NaN","Infinity"};
    for(size_t i=0;i<sizeof bad_numbers/sizeof *bad_numbers;i++){
        /* Test each cost position on raw JSON: non-finite values cannot be
         * created through Jansson's json_real API in the mutation tests. */
        const char *cost_names[]={"cost","upstream_inference_cost","upstream_inference_prompt_cost","upstream_inference_completions_cost"};
        for(size_t j=0;j<sizeof cost_names/sizeof *cost_names;j++){
            rc_response_observer *o=calloc(1,sizeof *o);assert(o);
            char b[512];
            snprintf(b,sizeof b,"data: {\"choices\":[],\"usage\":{\"prompt_tokens\":7,\"completion_tokens\":3,\"total_tokens\":10,%s\"%s\":%s%s}}\n\n",
                     j?"\"cost_details\":{":"",cost_names[j],bad_numbers[i],j?"}":"");
            feed(o,or_first);feed(o,or_stop);feed(o,b);feed(o,"data: [DONE]\n\n");
            assert(!rc_response_observer_message(o));free(o);
        }
    }
}
static void optional_metadata(void) {
    for(int mode=0;mode<4;mode++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        json_t *tail=usage_tail(),*u=json_object_get(tail,"usage");
        if(mode==0){
            json_object_set_new(tail,"choices",json_array());
            json_object_set_new(tail,"service_tier",json_null());
        }else if(mode==1){
            json_object_set_new(u,"cost",json_integer(0));json_object_set_new(u,"is_byok",json_true());
            json_t *details=json_object_get(u,"cost_details");
            json_object_set_new(details,"upstream_inference_cost",json_integer(1));
        }else if(mode==2){
            json_object_del(u,"cost");json_object_del(u,"is_byok");json_object_del(u,"cost_details");
            json_object_set_new(u,"prompt_tokens_details",json_null());
            json_object_set_new(u,"completion_tokens_details",json_null());
        }else{
            json_object_set_new(json_object_get(u,"prompt_tokens_details"),"cache_write_tokens",json_integer(2));
            json_object_set_new(json_object_get(u,"prompt_tokens_details"),"video_tokens",json_integer(2));
            json_object_set_new(json_object_get(u,"completion_tokens_details"),"image_tokens",json_integer(2));
        }
        feed(o,or_first);feed(o,or_stop);feed_json(o,tail);feed(o,"data: [DONE]\n\n");
        json_t *m=rc_response_observer_message(o);assert(m);json_decref(m);free(o);json_decref(tail);
    }
}
/* Optional private-wire replay: expected-text file.sse [file.sse ...].
 * Files remain external; the ordinary unit suite uses only synthetic data. */
static void replay(const char *path,const char *expected) {
    FILE *f=fopen(path,"rb");assert(f);
    char *wire=malloc(RC_RESPONSE_LIMIT+1);assert(wire);
    size_t n=fread(wire,1,RC_RESPONSE_LIMIT+1,f);assert(!ferror(f)&&feof(f)&&n&&n<=RC_RESPONSE_LIMIT);
    assert(!fclose(f));
    for(size_t split=0;split<=n;split++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        rc_response_observer_feed(o,wire,split);rc_response_observer_feed(o,wire+split,n-split);
        json_t *m=rc_response_observer_message(o);assert(m&&!o->failed);
        assert(!strcmp(json_string_value(json_object_get(m,"content")),expected));
        json_decref(m);free(o);
    }
    for(size_t fragment=1;fragment<=37;fragment+=36){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        for(size_t offset=0;offset<n;offset+=fragment){
            size_t count=n-offset<fragment?n-offset:fragment;
            rc_response_observer_feed(o,wire+offset,count);
        }
        json_t *m=rc_response_observer_message(o);assert(m&&!o->failed);
        assert(!strcmp(json_string_value(json_object_get(m,"content")),expected));
        json_decref(m);free(o);
    }
    free(wire);printf("private wire replay passed (%zu bytes; every split, 1/37-byte fragments)\n",n);
}
int main(int argc,char **argv){assert(argc==1||argc>=3);for(int i=2;i<argc;i++)replay(argv[i],argv[1]);terminal_guards();optional_metadata();reject_openrouter_metadata();openrouter_usage_tail();openrouter_metadata();every_split();reject_metadata();mixed_identity();framing_and_bounds();invalid_comment_utf8();puts("response observer tests passed");return 0;}
