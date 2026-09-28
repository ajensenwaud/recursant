#include "recursant/tool_boundary.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const char *history = "[{\"role\":\"user\",\"content\":\"run\"}]";
static const char *assistant = "{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"call A\",\"type\":\"function\",\"function\":{\"name\":\"run\",\"arguments\":\"{}\"}}]}";
static void replay_text(char *buf, size_t n, const char *tail) {
    snprintf(buf,n,"[%.*s,%s%s]",(int)strlen(history)-2,history+1,assistant,tail);
}
#include <jansson.h>
#include <stdlib.h>
static void rejected(json_t *h, json_t *a) {
    char *hs=json_dumps(h,JSON_COMPACT), *as=json_dumps(a,JSON_COMPACT);
    rc_tool_boundary *b=NULL;
    assert(rc_tool_boundary_capture(hs,strlen(hs),as,strlen(as),&b)==RC_TOOL_INVALID);
    assert(b==NULL); free(hs); free(as);
}
static void schema_tests(void) {
    json_t *h=json_loads(history,0,NULL), *a=json_loads(assistant,0,NULL);
    json_object_set_new(a,"reasoning_content",json_null()); rejected(h,a);
    json_object_del(a,"reasoning_content");
    json_t *calls=json_object_get(a,"tool_calls"), *call=json_array_get(calls,0);
    json_array_append(calls,call); rejected(h,a); json_array_remove(calls,1);
    json_object_set_new(call,"id",json_string("")); rejected(h,a);
    json_object_set_new(call,"id",json_string("call A"));
    json_object_set_new(json_object_get(call,"function"),"arguments",json_object()); rejected(h,a);
    json_object_set_new(json_object_get(call,"function"),"arguments",json_string("{}"));
    json_t *fn=json_object_get(call,"function");
    json_object_set_new(fn,"opaque",json_null()); rejected(h,a); json_object_del(fn,"opaque");
    json_object_set_new(call,"index",json_integer(0)); rejected(h,a); json_object_del(call,"index");
    json_object_set_new(call,"type",json_string("custom")); rejected(h,a);
    json_object_set_new(call,"type",json_string("function"));
    json_object_set_new(fn,"name",json_string("")); rejected(h,a);
    json_object_set_new(fn,"name",json_string("run"));
    json_object_set_new(a,"content",json_array()); rejected(h,a);
    json_object_set_new(a,"content",json_null());
    json_object_set_new(a,"refusal",json_null()); rejected(h,a); json_object_del(a,"refusal");
    json_object_set_new(json_array_get(h,0),"name",json_string("opaque")); rejected(h,a);
    json_decref(h); json_decref(a);
}
static void history_tests(void) {
    char buf[4096]; replay_text(buf,sizeof buf,",{\"role\":\"tool\",\"tool_call_id\":\"call A\",\"content\":\"failed\"}");
    json_t *h=json_loads(buf,0,NULL), *a=json_loads(assistant,0,NULL);
    json_object_set_new(json_array_get(json_object_get(a,"tool_calls"),0),"id",json_string("next"));
    char *as=json_dumps(a,JSON_COMPACT); rc_tool_boundary *b=NULL;
    assert(rc_tool_boundary_capture(buf,strlen(buf),as,strlen(as),&b)==RC_TOOL_COMPLETE);
    rc_tool_boundary_free(b); free(as);
    json_object_set_new(json_array_get(json_object_get(a,"tool_calls"),0),"id",json_string("call A"));
    rejected(h,a); /* Reuse of a historical call ID is ambiguous. */
    json_object_set_new(json_array_get(json_object_get(a,"tool_calls"),0),"id",json_string("next"));
    json_object_set_new(json_array_get(h,2),"tool_call_id",json_string("foreign")); rejected(h,a);
    json_object_set_new(json_array_get(h,2),"tool_call_id",json_string("call A"));
    json_array_insert(h,2,json_array_get(h,0)); rejected(h,a); json_array_remove(h,2);
    json_array_append(h,json_array_get(h,2)); rejected(h,a); json_array_remove(h,3);
    json_array_remove(h,2); rejected(h,a);
    json_decref(h); json_decref(a);
}
static void bounds_tests(void) {
    json_t *h=json_array(), *m=json_pack("{s:s,s:s}","role","user","content","x");
    for (size_t i=0;i<RC_TOOL_MAX_MESSAGES;++i) json_array_append(h,m);
    char *hs=json_dumps(h,JSON_COMPACT); rc_tool_boundary *b=NULL;
    assert(rc_tool_boundary_capture(hs,strlen(hs),assistant,strlen(assistant),&b)==RC_TOOL_LIMIT);
    assert(!b); free(hs); json_decref(h); json_decref(m);
    assert(rc_tool_boundary_capture(history,RC_TOOL_MAX_BYTES+1,assistant,strlen(assistant),&b)==RC_TOOL_LIMIT);
    assert(!b);
}
static rc_tool_status replay_json(rc_tool_boundary *b, json_t *v) {
    char *s=json_dumps(v,JSON_COMPACT); assert(s);
    rc_tool_status status=rc_tool_boundary_replay(b,s,strlen(s)); free(s); return status;
}
static void parallel_tests(void) {
    json_t *a=json_loads(assistant,0,NULL), *h=json_loads(history,0,NULL);
    json_t *cs=json_object_get(a,"tool_calls"), *c=json_deep_copy(json_array_get(cs,0));
    json_object_set_new(c,"id",json_string("第二")); json_array_append_new(cs,c);
    char *as=json_dumps(a,JSON_COMPACT); rc_tool_boundary *b=NULL;
    assert(rc_tool_boundary_capture(history,strlen(history),as,strlen(as),&b)==RC_TOOL_COMPLETE);
    assert(rc_tool_boundary_requirements(b)==7);
    assert(!rc_tool_boundary_candidate(b,3,7));
    assert(!rc_tool_boundary_candidate(b,7,3));
    assert(rc_tool_boundary_candidate(b,7,7));
    json_array_append(h,a);
    json_t *r=json_pack("{s:s,s:s,s:s}","role","tool","tool_call_id","第二","content","not JSON: exit 137");
    json_array_append(h,r); assert(replay_json(b,h)==RC_TOOL_INCOMPLETE);
    json_array_append(h,r); assert(replay_json(b,h)==RC_TOOL_INVALID);
    json_array_remove(h,3);
    json_t *r2=json_deep_copy(r); json_object_set_new(r2,"tool_call_id",json_string("call A"));
    json_array_append(h,r2); assert(replay_json(b,h)==RC_TOOL_COMPLETE);
    /* Out-of-order results are complete; original byte/string values remain exact. */
    json_object_set_new(json_array_get(h,0),"content",json_string("fabricated"));
    assert(replay_json(b,h)==RC_TOOL_INVALID);
    json_object_set_new(json_array_get(h,0),"content",json_string("run"));
    /* Equivalent JSON arguments (Hermes compact re-serialization) replay;
     * a decoded-value change still does not. */
    json_object_set_new(json_object_get(json_array_get(cs,0),"function"),"arguments",json_string("{ }"));
    assert(replay_json(b,h)==RC_TOOL_COMPLETE);
    json_object_set_new(json_object_get(json_array_get(cs,0),"function"),"arguments",json_string("{\"x\":1}"));
    assert(replay_json(b,h)==RC_TOOL_INVALID);
    json_object_set_new(json_object_get(json_array_get(cs,0),"function"),"arguments",json_string("{}"));
    json_object_set_new(r,"opaque",json_null()); assert(replay_json(b,h)==RC_TOOL_INVALID);
    json_object_del(r,"opaque");
    json_object_set_new(r,"content",json_null()); assert(replay_json(b,h)==RC_TOOL_INVALID);
    json_object_set_new(r,"content",json_string("test failed"));
    json_array_append_new(h,json_pack("{s:s,s:s}","role","user","content","extra"));
    assert(replay_json(b,h)==RC_TOOL_INVALID); json_array_remove(h,4);
    json_array_set(h,2,json_array_get(h,0)); assert(replay_json(b,h)==RC_TOOL_INVALID);
    rc_tool_boundary_free(b); free(as); json_decref(r); json_decref(r2); json_decref(a); json_decref(h);
}
static void malformed_tests(void) {
    const char *bad[]={"", "null", "[]", "{} trailing", "{\"role\":\"assistant\",\"role\":\"assistant\"}",
        "{\"role\":\"assistant\\u0000\",\"tool_calls\":[]}", "{\"role\":\"assistant\",\"tool_calls\":[]}"};
    for (size_t i=0;i<sizeof bad/sizeof *bad;++i) {
        rc_tool_boundary *b=NULL;
        assert(rc_tool_boundary_capture(history,strlen(history),bad[i],strlen(bad[i]),&b)==RC_TOOL_INVALID);
        assert(!b);
    }
    rc_tool_boundary *b=NULL;
    char raw[4096]; size_t len=strlen(assistant);
    memcpy(raw,assistant,len); raw[len]=0; memcpy(raw+len+1,"garbage",7);
    assert(rc_tool_boundary_capture(history,strlen(history),raw,len+8,&b)==RC_TOOL_INVALID);
    assert(rc_tool_boundary_capture(NULL,0,assistant,strlen(assistant),&b)==RC_TOOL_INVALID);
    assert(rc_tool_boundary_capture(history,strlen(history),assistant,strlen(assistant),NULL)==RC_TOOL_INVALID);
    assert(rc_tool_boundary_replay(NULL,"[]",2)==RC_TOOL_INVALID);
    rc_tool_boundary_free(NULL);
}
static void edge_tests(void) {
    json_t *a=json_loads(assistant,0,NULL), *h=json_loads(history,0,NULL);
    json_t *cs=json_object_get(a,"tool_calls"), *first=json_array_get(cs,0);
    char id[RC_TOOL_MAX_ID_BYTES+2]; memset(id,'x',sizeof id); id[RC_TOOL_MAX_ID_BYTES]=0;
    json_object_set_new(first,"id",json_string(id));
    char *as=json_dumps(a,JSON_COMPACT); rc_tool_boundary *b=NULL;
    assert(rc_tool_boundary_capture(history,strlen(history),as,strlen(as),&b)==RC_TOOL_COMPLETE);
    rc_tool_boundary_free(b); free(as);
    id[RC_TOOL_MAX_ID_BYTES]='x'; id[RC_TOOL_MAX_ID_BYTES+1]=0;
    json_object_set_new(first,"id",json_string(id)); rejected(h,a);
    json_object_set_new(first,"id",json_string("0"));
    for (size_t i=1;i<RC_TOOL_MAX_CALLS;++i) {
        json_t *c=json_deep_copy(first); char num[32]; snprintf(num,sizeof num,"%zu",i);
        json_object_set_new(c,"id",json_string(num)); json_array_append_new(cs,c);
    }
    as=json_dumps(a,JSON_COMPACT);
    assert(rc_tool_boundary_capture(history,strlen(history),as,strlen(as),&b)==RC_TOOL_COMPLETE);
    json_array_append(h,a);
    for (size_t i=RC_TOOL_MAX_CALLS;i>0;--i) {
        char num[32]; snprintf(num,sizeof num,"%zu",i-1);
        json_array_append_new(h,json_pack("{s:s,s:s,s:s}","role","tool","tool_call_id",num,"content",""));
    }
    assert(replay_json(b,h)==RC_TOOL_COMPLETE);
    assert(rc_tool_boundary_replay(b,"[]",RC_TOOL_MAX_BYTES+1)==RC_TOOL_LIMIT);
    assert(rc_tool_boundary_replay(b,NULL,0)==RC_TOOL_INVALID);
    char *hs=json_dumps(h,JSON_COMPACT);
    rc_tool_boundary *next=NULL;
    assert(rc_tool_boundary_capture(hs,strlen(hs),assistant,strlen(assistant),&next)==RC_TOOL_LIMIT);
    assert(!next); free(hs); free(as); rc_tool_boundary_free(b);
    json_array_append(cs,first); rejected(h,a);
    json_decref(a); json_decref(h);

    h=json_array(); json_t *m=json_pack("{s:s,s:s}","role","user","content","");
    for (size_t i=0;i<RC_TOOL_MAX_MESSAGES-2;++i) json_array_append(h,m);
    hs=json_dumps(h,JSON_COMPACT);
    assert(rc_tool_boundary_capture(hs,strlen(hs),assistant,strlen(assistant),&b)==RC_TOOL_COMPLETE);
    rc_tool_boundary_free(b); free(hs); json_decref(m); json_decref(h);
}
/* Hermes (pinned d0288be) replays tool-call arguments re-serialized compactly
 * after json.loads: whitespace may differ, decoded JSON must not. */
static void argument_spelling_tests(void) {
    const char *spaced="{\"role\":\"assistant\",\"content\":\"step\",\"tool_calls\":[{\"id\":\"c1\",\"type\":\"function\",\"function\":{\"name\":\"terminal\",\"arguments\":\"{\\\"command\\\": \\\"pwd\\\", \\\"n\\\": [1, 2]}\"}}]}";
    rc_tool_boundary *b=NULL;
    assert(rc_tool_boundary_capture(history,strlen(history),spaced,strlen(spaced),&b)==RC_TOOL_COMPLETE);
    const char *head="[{\"role\":\"user\",\"content\":\"run\"},{\"role\":\"assistant\",\"content\":\"step\",\"tool_calls\":[{\"id\":\"c1\",\"type\":\"function\",\"function\":{\"name\":\"terminal\",\"arguments\":";
    const char *tail="}}]},{\"role\":\"tool\",\"tool_call_id\":\"c1\",\"content\":\"ok\"}]";
    const char *same[]={"\"{\\\"command\\\":\\\"pwd\\\",\\\"n\\\":[1,2]}\"", "\"{\\\"n\\\":[1,2],\\\"command\\\":\\\"pwd\\\"}\"",
                        "\"{\\\"command\\\": \\\"pwd\\\", \\\"n\\\": [1, 2]}\""};
    const char *changed[]={"\"{\\\"command\\\":\\\"ls\\\",\\\"n\\\":[1,2]}\"", "\"{\\\"command\\\":\\\"pwd\\\",\\\"n\\\":[2,1]}\"",
                           "\"{\\\"command\\\":\\\"pwd\\\"}\"", "\"{\\\"command\\\":\\\"pwd\\\",\\\"n\\\":[1,2],\\\"x\\\":null}\"",
                           "\"not json\"", "\"{\\\"command\\\":\\\"pwd\\\",\\\"command\\\":\\\"pwd\\\",\\\"n\\\":[1,2]}\""};
    char buf[1024];
    for(size_t i=0;i<sizeof same/sizeof *same;i++){snprintf(buf,sizeof buf,"%s%s%s",head,same[i],tail);assert(rc_tool_boundary_replay(b,buf,strlen(buf))==RC_TOOL_COMPLETE);}
    for(size_t i=0;i<sizeof changed/sizeof *changed;i++){snprintf(buf,sizeof buf,"%s%s%s",head,changed[i],tail);assert(rc_tool_boundary_replay(b,buf,strlen(buf))==RC_TOOL_INVALID);}
    rc_tool_boundary_free(b);
    /* Non-JSON original arguments keep exact string comparison. */
    const char *raw="{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"c1\",\"type\":\"function\",\"function\":{\"name\":\"t\",\"arguments\":\"not json\"}}]}";
    assert(rc_tool_boundary_capture(history,strlen(history),raw,strlen(raw),&b)==RC_TOOL_COMPLETE);
    const char *rhead="[{\"role\":\"user\",\"content\":\"run\"},{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"c1\",\"type\":\"function\",\"function\":{\"name\":\"t\",\"arguments\":";
    snprintf(buf,sizeof buf,"%s\"not json\"%s",rhead,tail);assert(rc_tool_boundary_replay(b,buf,strlen(buf))==RC_TOOL_COMPLETE);
    snprintf(buf,sizeof buf,"%s\"not  json\"%s",rhead,tail);assert(rc_tool_boundary_replay(b,buf,strlen(buf))==RC_TOOL_INVALID);
    rc_tool_boundary_free(b);
}
int main(void) {
    argument_spelling_tests();
    edge_tests();
    parallel_tests(); malformed_tests();
    schema_tests(); history_tests(); bounds_tests();
    rc_tool_boundary *b = NULL;
    assert(rc_tool_boundary_capture(history,strlen(history),assistant,strlen(assistant),&b)==RC_TOOL_COMPLETE);
    assert(rc_tool_boundary_requirements(b)==(RC_TOOL_CAP_HISTORY|RC_TOOL_CAP_FUNCTIONS));
    assert(!rc_tool_boundary_candidate(b,0,UINT32_MAX));
    assert(!rc_tool_boundary_candidate(b,UINT32_MAX,0));
    assert(rc_tool_boundary_candidate(b,UINT32_MAX,UINT32_MAX));
    assert(!rc_tool_boundary_candidate(NULL,UINT32_MAX,UINT32_MAX));
    char replay[4096];
    replay_text(replay,sizeof replay,",{\"role\":\"tool\",\"tool_call_id\":\"call A\",\"content\":\"exit 1; tests failed\"}");
    assert(rc_tool_boundary_replay(b,replay,strlen(replay))==RC_TOOL_COMPLETE);
    replay_text(replay,sizeof replay,"");
    assert(rc_tool_boundary_replay(b,replay,strlen(replay))==RC_TOOL_INCOMPLETE);
    replay_text(replay,sizeof replay,",{\"role\":\"tool\",\"tool_call_id\":\"foreign\",\"content\":\"ok\"}");
    assert(rc_tool_boundary_replay(b,replay,strlen(replay))==RC_TOOL_INVALID);
    rc_tool_boundary_free(b);
    puts("tool_boundary: PASS");
}
