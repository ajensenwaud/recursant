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
static void line_bound(void) {
    /* A single SSE line longer than 64KiB fails closed even though the
     * whole-stream wire bound is larger. */
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    char *big=malloc(RC_RESPONSE_LIMIT+2);assert(big);memset(big,'x',RC_RESPONSE_LIMIT+1);big[0]=':';big[RC_RESPONSE_LIMIT+1]='\n';
    rc_response_observer_feed(o,big,RC_RESPONSE_LIMIT+2);assert(o->failed);free(big);free(o);
}
static void framing_and_bounds(void) {
    const char *wire=": keepalive\r\ndata: {\"choices\":\r\ndata: [{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"café 🦀\"},\"finish_reason\":\"stop\"}]}\r\n\r\ndata: [DONE]\r\n\r\n";
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    for(size_t i=0;i<strlen(wire);i++)rc_response_observer_feed(o,wire+i,1);
    json_t *m=rc_response_observer_message(o);assert(m);
    assert(!strcmp(json_string_value(json_object_get(m,"content")),"café 🦀"));json_decref(m);
    memset(o,0,sizeof *o);
    char *full=malloc(RC_RESPONSE_WIRE_LIMIT);assert(full);
    size_t pad=RC_RESPONSE_WIRE_LIMIT-strlen(first)-strlen(last);
    /* Wire bound filled with many bounded comment lines (each line <=64KiB). */
    memset(full,'x',pad);for(size_t i=0;i+1<pad;i+=4096){full[i]=':';size_t e=i+4095<pad-2?i+4095:pad-2;full[e]='\n';}
    full[pad-2]='\n';full[pad-1]='\n';
    memcpy(full+pad,first,strlen(first));memcpy(full+pad+strlen(first),last,strlen(last));
    rc_response_observer_feed(o,full,RC_RESPONSE_WIRE_LIMIT);
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
static json_t *tool_event(const char *content) {
    json_error_t error;
    json_t *v=json_loads("{\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"tool_calls\":[{\"index\":0,\"id\":\"call-1\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"tool_calls\",\"native_finish_reason\":\"tool_calls\"}]}",0,&error);assert(v);
    json_t *delta=json_object_get(json_array_get(json_object_get(v,"choices"),0),"delta");
    if(content)assert(!json_object_set_new(delta,"content",json_string(content)));
    return v;
}
static void tool_terminal_contract(void) {
    /* Empty/missing/null stream content normalizes to exact empty replay text. */
    for(int mode=0;mode<5;mode++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        json_t *v=tool_event(mode==0?NULL:mode==1?"":"café 🦀");
        json_t *c=json_array_get(json_object_get(v,"choices"),0),*d=json_object_get(c,"delta");
        if(mode==3)json_object_set_new(d,"content",json_null());
        feed_json(o,v);assert(!rc_response_observer_message(o));
        if(mode==4){
            json_object_set_new(c,"delta",json_pack("{s:s,s:s}","role","assistant","content",""));
            json_error_t error;json_object_set_new(v,"usage",json_loads(or_usage,0,&error));
            feed_json(o,v);
        }
        feed(o,"data: [DONE]\n\n");
        json_t *m=rc_response_observer_message(o);assert(m);
        assert(!strcmp(json_string_value(json_object_get(m,"content")),mode==2||mode==4?"café 🦀":""));
        json_decref(m);json_decref(v);free(o);
    }
}
/* Exact shape recorded from live OpenRouter openai/gpt-4.1 (pilot-1, 2026-09-29):
 * content:null tool deltas, then finish_reason tool_calls WITH
 * native_finish_reason "completed", repeated once with the accounting usage. */
static void openrouter_real_tool_finish(void) {
    /* Per-token OpenRouter chunks: ~300 wire bytes per argument token. A
     * 1500-token write_file call is ~450KB on the wire but ~6KB retained. */
    {
        const char *env="data: {\"id\":\"gen-2\",\"object\":\"chat.completion.chunk\",\"created\":7,\"model\":\"openai/gpt-4.1\",\"provider\":\"OpenAI\",\"choices\":[{\"index\":0,\"delta\":{\"content\":null,\"role\":\"assistant\",\"tool_calls\":[{\"index\":0,%s\"function\":{%s\"arguments\":\"%s\"}}]},\"finish_reason\":null,\"native_finish_reason\":null}]}\n\n";
        char buf[1024];
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        snprintf(buf,sizeof buf,env,"\"id\":\"call_long\",\"type\":\"function\",","\"name\":\"write_file\",","{\\\"content\\\":\\\"");feed(o,buf);
        for(int i=0;i<1500;i++){snprintf(buf,sizeof buf,env,"","","ab");feed(o,buf);}
        snprintf(buf,sizeof buf,env,"","","\\\"}");feed(o,buf);
        feed(o,"data: {\"id\":\"gen-2\",\"object\":\"chat.completion.chunk\",\"created\":7,\"model\":\"openai/gpt-4.1\",\"provider\":\"OpenAI\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"\",\"role\":\"assistant\"},\"finish_reason\":\"tool_calls\",\"native_finish_reason\":\"completed\"}]}\n\n");
        feed(o,"data: [DONE]\n\n");
        assert(o->total>4*65536);
        json_t *m=rc_response_observer_message(o);assert(m);
        const char *args=json_string_value(json_object_get(json_object_get(json_array_get(json_object_get(m,"tool_calls"),0),"function"),"arguments"));
        assert(strlen(args)==strlen("{\"content\":\"\"}")+3000);
        json_decref(m);free(o);
    }
    const char *base="{\"id\":\"gen-1\",\"object\":\"chat.completion.chunk\",\"created\":7,\"model\":\"openai/gpt-4.1\",\"provider\":\"OpenAI\",";
    char buf[1024];
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    snprintf(buf,sizeof buf,"data: %s\"choices\":[{\"index\":0,\"delta\":{\"content\":null,\"role\":\"assistant\",\"tool_calls\":[{\"index\":0,\"id\":\"call_x4\",\"type\":\"function\",\"function\":{\"name\":\"write_file\",\"arguments\":\"\"}}]},\"finish_reason\":null,\"native_finish_reason\":null}]}\n\n",base);feed(o,buf);
    snprintf(buf,sizeof buf,"data: %s\"choices\":[{\"index\":0,\"delta\":{\"content\":null,\"role\":\"assistant\",\"tool_calls\":[{\"index\":0,\"function\":{\"arguments\":\"{\\\"path\\\": \\\"a\\\"}\"}}]},\"finish_reason\":null,\"native_finish_reason\":null}]}\n\n",base);feed(o,buf);
    snprintf(buf,sizeof buf,"data: %s\"choices\":[{\"index\":0,\"delta\":{\"content\":\"\",\"role\":\"assistant\"},\"finish_reason\":\"tool_calls\",\"native_finish_reason\":\"completed\"}]}\n\n",base);feed(o,buf);
    snprintf(buf,sizeof buf,"data: %s\"service_tier\":\"default\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"\",\"role\":\"assistant\"},\"finish_reason\":\"tool_calls\",\"native_finish_reason\":\"completed\"}],\"usage\":%s}\n\n",base,or_usage);feed(o,buf);
    feed(o,"data: [DONE]\n\n");
    json_t *m=rc_response_observer_message(o);assert(m);
    json_t *call=json_array_get(json_object_get(m,"tool_calls"),0);
    assert(!strcmp(json_string_value(json_object_get(json_object_get(call,"function"),"arguments")),"{\"path\": \"a\"}"));
    assert(!strcmp(json_string_value(json_object_get(m,"content")),""));
    json_decref(m);free(o);
    /* Terminal/tail native mismatch still fails closed. */
    o=calloc(1,sizeof *o);assert(o);
    snprintf(buf,sizeof buf,"data: %s\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"tool_calls\":[{\"index\":0,\"id\":\"c\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"tool_calls\",\"native_finish_reason\":\"completed\"}]}\n\n",base);feed(o,buf);
    snprintf(buf,sizeof buf,"data: %s\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"tool_calls\",\"native_finish_reason\":\"tool_calls\"}],\"usage\":%s}\n\n",base,or_usage);feed(o,buf);
    feed(o,"data: [DONE]\n\n");
    assert(!rc_response_observer_message(o));free(o);
}
static void tool_guards(void) {
    for(int mode=0;mode<24;mode++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        json_t *v=tool_event(NULL),*c=json_array_get(json_object_get(v,"choices"),0);
        json_t *d=json_object_get(c,"delta"),*calls=json_object_get(d,"tool_calls");
        json_t *call=json_array_get(calls,0),*fn=json_object_get(call,"function");
        switch(mode){
        case 0: json_object_set_new(c,"finish_reason",json_string("stop"));break;
        case 1: json_object_set_new(c,"finish_reason",json_string("length"));break;
        case 2: json_object_set_new(c,"finish_reason",json_null());break;
        case 3: json_object_del(d,"tool_calls");break;
        case 4: json_object_set_new(d,"reasoning_content",json_string("opaque"));break;
        case 5: json_object_set_new(d,"refusal",json_string("refused"));break;
        case 6: json_object_set_new(call,"extra_content",json_pack("{s:s}","signature","opaque"));break;
        case 7: json_object_del(call,"id");break;
        case 8: json_object_set_new(call,"index",json_integer(1));break;
        case 9: json_object_del(fn,"arguments");break;
        case 10: json_object_set_new(fn,"arguments",json_null());break;
        case 11: json_object_set_new(d,"tool_calls",json_null());break;
        case 12: json_object_set_new(c,"native_finish_reason",json_string("length"));break;
        case 13: json_object_set_new(d,"signature",json_string("opaque"));break;
        case 14: json_object_set_new(c,"index",json_integer(1));break;
        case 15: {json_t *other=json_deep_copy(call);json_object_set_new(other,"index",json_integer(1));json_array_append_new(calls,other);break;}
        default: break;
        }
        feed_json(o,v);
        if(mode>=16&&mode<=20){
            json_object_set_new(c,"delta",json_object());
            json_error_t error;json_object_set_new(v,"usage",json_loads(or_usage,0,&error));
            if(mode==16)json_object_set_new(json_object_get(c,"delta"),"content",json_string("late"));
            if(mode==17)json_object_set_new(json_object_get(c,"delta"),"tool_calls",json_array());
            if(mode==18){json_object_set_new(c,"finish_reason",json_string("stop"));json_object_del(c,"native_finish_reason");}
            if(mode==19)json_object_del(c,"native_finish_reason");
            feed_json(o,v);
            if(mode==20)feed_json(o,v);
        }
        if(mode!=21)feed(o,"data: [DONE]\n\n");
        if(mode==22)feed(o,"data: [DONE]\n\n");
        if(mode==23)feed_json(o,v);
        assert(!rc_response_observer_message(o));json_decref(v);free(o);
    }
}
static void tool_message_and_wire_bounds(void) {
    for(int overflow=0;overflow<=1;overflow++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        json_t *v=tool_event(NULL),*c=json_array_get(json_object_get(v,"choices"),0);
        json_t *fn=json_object_get(json_array_get(json_object_get(json_object_get(c,"delta"),"tool_calls"),0),"function");
        feed_json(o,v);feed(o,"data: [DONE]\n\n");
        json_t *m=rc_response_observer_message(o);assert(m);
        char *encoded=json_dumps(m,JSON_COMPACT);assert(encoded);
        size_t n=32768-strlen(encoded)+2+(size_t)overflow;
        char *args=malloc(n+1);assert(args);memset(args,'x',n);args[n]=0;
        json_object_set_new(fn,"arguments",json_string(args));free(args);free(encoded);json_decref(m);
        memset(o,0,sizeof *o);feed_json(o,v);feed(o,"data: [DONE]\n\n");
        assert(o->total<RC_RESPONSE_WIRE_LIMIT);
        m=rc_response_observer_message(o);assert((m!=NULL)==!overflow);json_decref(m);
        if(!overflow){
            /* Full wire bound includes framing/comments, independent of retained message. */
            size_t n=RC_RESPONSE_WIRE_LIMIT-o->total;
            char *padding=malloc(n);assert(padding);memset(padding,'x',n);
            for(size_t i=0;i<n;i+=4096){padding[i]=':';size_t e=i+4095<n-1?i+4095:n-1;padding[e]='\n';}
            rc_response_observer_feed(o,padding,n);free(padding);
            m=rc_response_observer_message(o);assert(m);json_decref(m);
            feed(o,"\n");assert(!rc_response_observer_message(o));
        }
        json_decref(v);free(o);
    }
}
static void streamed_tools(void) {
    const char *wire="data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"index\":0,\"id\":\"call-1\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{\"}}]},\"finish_reason\":null}]}\n\ndata: {\"choices\":[{\"index\":0,\"delta\":{\"tool_calls\":[{\"index\":0,\"function\":{\"arguments\":\"}\"}}]},\"finish_reason\":null}]}\n\ndata: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"tool_calls\"}]}\n\ndata: [DONE]\n\n";
    for(size_t split=0;split<=strlen(wire);split++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        rc_response_observer_feed(o,wire,split);
        rc_response_observer_feed(o,wire+split,strlen(wire)-split);
        json_t *m=rc_response_observer_message(o);assert(m);
        assert(json_is_string(json_object_get(m,"content"))&&!strcmp(json_string_value(json_object_get(m,"content")),""));
        json_t *calls=json_object_get(m,"tool_calls");assert(json_array_size(calls)==1);
        json_t *call=json_array_get(calls,0);
        assert(!json_object_get(call,"index"));
        assert(!strcmp(json_string_value(json_object_get(call,"id")),"call-1"));
        assert(!strcmp(json_string_value(json_object_get(json_object_get(call,"function"),"arguments")),"{}"));
        json_decref(m);free(o);
    }
}
/* S2b: the observer knows which provider adapter produced the stream. Plain
 * OpenAI streams (incl. the include_usage empty-choices tail) are accepted by
 * both; the OpenRouter-only accounting tail and fields only by openrouter. */
static json_t *observe(bool strict,const char *wire){
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    o->strict_openai=strict;feed(o,wire);
    json_t *m=rc_response_observer_message(o);free(o);return m;
}
static void adapter_dialects(void) {
    const char *plain_usage="data: {\"choices\":[],\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":4,\"total_tokens\":7,"
        "\"prompt_tokens_details\":{\"cached_tokens\":1,\"audio_tokens\":0},"
        "\"completion_tokens_details\":{\"reasoning_tokens\":1,\"audio_tokens\":0,\"accepted_prediction_tokens\":0,\"rejected_prediction_tokens\":0}}}\n\n";
    char wire[8192];
    for(int strict=0;strict<2;strict++){
        snprintf(wire,sizeof wire,"%s%s",first,last);
        json_t *m=observe(strict,wire);assert(m);json_decref(m);
        snprintf(wire,sizeof wire,"%s%.*s%sdata: [DONE]\n\n",first,(int)(strlen(last)-strlen("data: [DONE]\n\n")),last,plain_usage);
        m=observe(strict,wire);
        if(!m)fprintf(stderr,"strict=%d rejected plain include_usage tail\n",strict);
        assert(m);json_decref(m);
    }
    json_t *tail=usage_tail();char *s=json_dumps(tail,JSON_COMPACT);assert(s);
    snprintf(wire,sizeof wire,"%s%sdata: %s\n\ndata: [DONE]\n\n",or_first,or_stop,s);
    json_t *m=observe(false,wire);assert(m);json_decref(m);
    m=observe(true,wire);
    if(m)fprintf(stderr,"openai-compatible accepted OpenRouter accounting tail\n");
    assert(!m);
    free(s);json_decref(tail);
    /* OpenAI itself emits service_tier:"default"; vLLM extensions stay portable. */
    for(int strict=0;strict<2;strict++){
        snprintf(wire,sizeof wire,"data: {\"service_tier\":\"default\",\"system_fingerprint\":\"fp\",\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null,\"logprobs\":null}],\"usage\":null}\n\n%s",last);
        m=observe(strict,wire);assert(m);json_decref(m);
    }
    /* Each OpenRouter-only field alone, on an otherwise plain OpenAI stream. */
    const char *only[]={
        "data: {\"provider\":\"OpenAI\",\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null}]}\n\n",
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null,\"native_finish_reason\":null}]}\n\n",
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"cost\":0}}\n\n",
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"is_byok\":false}}\n\n",
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"cost_details\":{\"upstream_inference_cost\":0}}}\n\n",
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"prompt_tokens_details\":{\"cache_write_tokens\":0}}}\n\n",
        "data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"x\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"completion_tokens_details\":{\"image_tokens\":0}}}\n\n",
    };
    for(size_t i=0;i<sizeof only/sizeof *only;i++){
        snprintf(wire,sizeof wire,"%s%s",only[i],last);
        m=observe(false,wire);
        if(!m)fprintf(stderr,"openrouter rejected field %zu\n",i);
        assert(m);json_decref(m);
        m=observe(true,wire);
        if(m)fprintf(stderr,"openai-compatible accepted OpenRouter-only field %zu\n",i);
        assert(!m);
    }
    /* Repeated non-empty terminal choice carrying usage is OpenRouter-only. */
    snprintf(wire,sizeof wire,"%s%.*sdata: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}],"
        "\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2}}\n\ndata: [DONE]\n\n",
        first,(int)(strlen(last)-strlen("data: [DONE]\n\n")),last);
    m=observe(false,wire);assert(m);json_decref(m);
    m=observe(true,wire);
    if(m)fprintf(stderr,"openai-compatible accepted repeated terminal choice\n");
    assert(!m);
}
static void usage_capture(void) {
    const char *u1="\"usage\":{\"prompt_tokens\":100,\"completion_tokens\":7,\"total_tokens\":107,\"prompt_tokens_details\":{\"cached_tokens\":90}}";
    const char *u2="\"usage\":{\"prompt_tokens\":101,\"completion_tokens\":7,\"total_tokens\":108}";
    const char *over="\"usage\":{\"prompt_tokens\":5,\"completion_tokens\":1,\"total_tokens\":6,\"prompt_tokens_details\":{\"cached_tokens\":6}}";
    char tail[512];
    /* 0: include_usage tail recorded; 1: no usage; 2: conflicting second usage; 3: cached>prompt. */
    for(int mode=0;mode<4;mode++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);o->strict_openai=true;
        feed(o,first);
        if(mode==2){snprintf(tail,sizeof tail,"data: {%s,\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n",u2);feed(o,tail);}
        else feed(o,"data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n");
        if(mode!=1){snprintf(tail,sizeof tail,"data: {\"choices\":[],%s}\n\n",mode==3?over:u1);feed(o,tail);}
        feed(o,"data: [DONE]\n\n");
        json_t *m=rc_response_observer_message(o);
        if(mode==0){assert(m&&o->usage_known&&o->usage_prompt==100&&o->usage_completion==7&&o->usage_cached==90);}
        if(mode==1){assert(m&&!o->usage_known);}
        if(mode>=2){assert(!m);}
        json_decref(m);free(o);
    }
}
int main(int argc,char **argv){line_bound();openrouter_real_tool_finish();usage_capture();adapter_dialects();tool_guards();tool_message_and_wire_bounds();tool_terminal_contract();streamed_tools();assert(argc==1||argc>=3);for(int i=2;i<argc;i++)replay(argv[i],argv[1]);terminal_guards();optional_metadata();reject_openrouter_metadata();openrouter_usage_tail();openrouter_metadata();every_split();reject_metadata();mixed_identity();framing_and_bounds();invalid_comment_utf8();puts("response observer tests passed");return 0;}
