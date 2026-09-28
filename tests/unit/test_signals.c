#include "recursant/signals.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
static const rc_signal_scope ONE={1};
static json_t *load(const char *text) {
    json_error_t e; json_t *v=json_loads(text,0,&e);
    if (!v) { fprintf(stderr,"fixture: %s\n",e.text); exit(1); }
    return v;
}
static uint64_t classify(const char *text, const rc_signal_scope *s) {
    json_t *b=load(text); uint64_t c=rc_signals_classify(b,s); json_decref(b); return c;
}
#define TOOLS "\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"f\"}}]"
#define CALL(id) "{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"" id "\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{}\"}}]}"
#define RESULT(id,text) "{\"role\":\"tool\",\"tool_call_id\":\"" id "\",\"content\":\"" text "\"}"
#define USER(text) "{\"role\":\"user\",\"content\":\"" text "\"}"
static void taxonomy(void) {
    CHECK(RC_TASK_FORMAT_SIMPLE==1 && RC_TASK_TOOL_FOLLOWUP_OK==2 &&
          RC_TASK_FINAL_ANSWER==4 && RC_TASK_RECOVERY==8);
    uint64_t bit=99;
    CHECK(rc_task_qualifiable("format_simple",&bit) && bit==RC_TASK_FORMAT_SIMPLE);
    CHECK(rc_task_qualifiable("tool_followup_ok",&bit) && bit==RC_TASK_TOOL_FOLLOWUP_OK);
    CHECK(rc_task_qualifiable("final_answer",&bit) && bit==RC_TASK_FINAL_ANSWER);
    bit=99;
    CHECK(!rc_task_qualifiable("recovery",&bit) && bit==99);
    CHECK(!rc_task_qualifiable("Format_simple",&bit));
    CHECK(!rc_task_qualifiable("format_simple ",&bit));
    CHECK(!rc_task_qualifiable("",&bit));
    CHECK(!rc_task_qualifiable(NULL,&bit));
    CHECK(!strcmp(rc_task_name(0),"none"));
    CHECK(!strcmp(rc_task_name(RC_TASK_FORMAT_SIMPLE),"format_simple"));
    CHECK(!strcmp(rc_task_name(RC_TASK_TOOL_FOLLOWUP_OK),"tool_followup_ok"));
    CHECK(!strcmp(rc_task_name(RC_TASK_FINAL_ANSWER),"final_answer"));
    CHECK(!strcmp(rc_task_name(RC_TASK_RECOVERY),"recovery"));
    CHECK(!strcmp(rc_task_name(3),"invalid"));
    CHECK(!strcmp(rc_task_name(16),"invalid"));
}
static void followup_and_final(void) {
    const char *ok="{\"messages\":[" USER("start") "," CALL("c1") "," RESULT("c1","wrote 3 files") "]," TOOLS "}";
    CHECK(classify(ok,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    CHECK(classify("{\"messages\":[" USER("start") "," CALL("c1") "," RESULT("c1","ok") "]," TOOLS ",\"tool_choice\":\"auto\"}",&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    CHECK(classify("{\"messages\":[" USER("start") "," CALL("c1") "," RESULT("c1","ok") "]," TOOLS ",\"tool_choice\":\"required\"}",&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* No tools offered, or tools explicitly disabled: final answer. */
    CHECK(classify("{\"messages\":[" USER("start") "," CALL("c1") "," RESULT("c1","ok") "]}",&ONE)==RC_TASK_FINAL_ANSWER);
    CHECK(classify("{\"messages\":[" USER("start") "," CALL("c1") "," RESULT("c1","ok") "]," TOOLS ",\"tool_choice\":\"none\"}",&ONE)==RC_TASK_FINAL_ANSWER);
    /* Parallel successful results. */
    CHECK(classify("{\"messages\":[" USER("s") ",{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[]}," RESULT("a","ok") "," RESULT("b","done") "]," TOOLS "}",&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* First physical turn in the scope never gets a structured class. */
    const rc_signal_scope zero={0};
    CHECK(classify(ok,&zero)==0);
    CHECK(classify(ok,NULL)==0);
    /* Not a tool follow-up: trailing user or assistant message. */
    CHECK(classify("{\"messages\":[" USER("hello") "]," TOOLS "}",&ONE)==0);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," USER("more") "]}",&ONE)==0);
    CHECK(classify("{\"messages\":[" USER("s") ",{\"role\":\"assistant\",\"content\":\"plan\"}]}",&ONE)==0);
}
static void failures_and_recovery(void) {
    /* A single failure is neither success nor recovery. */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","Traceback (most recent call last)") "]," TOOLS "}",&ONE)==0);
    /* Two consecutive failures (assistant turns between them) -> recovery. */
    const char *two="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ERROR: no such file") "," CALL("c2") "," RESULT("c2","command failed") "]," TOOLS "}";
    CHECK(classify(two,&ONE)==RC_TASK_RECOVERY);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ValueError exception") "," CALL("c2") "," RESULT("c2","exit code: 2") "]}",&ONE)==RC_TASK_RECOVERY);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","x failed") "," RESULT("c2","y failed") "]," TOOLS "}",&ONE)==RC_TASK_RECOVERY);
    /* Recent failure then success: not clean, not recovery. */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","error") "," CALL("c2") "," RESULT("c2","ok") "]," TOOLS "}",&ONE)==0);
    /* Failure outside the 3-result window does not taint a clean follow-up. */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c0") "," RESULT("c0","error") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2","ok") "," CALL("c3") "," RESULT("c3","ok") "]," TOOLS "}",&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* A user message breaks the consecutive-failure run. */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","error") "," USER("try again") "," CALL("c2") "," RESULT("c2","error") "]," TOOLS "}",&ONE)==0);
    /* Success after two failures ends recovery. */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","error") "," CALL("c2") "," RESULT("c2","error") "," CALL("c3") "," RESULT("c3","ok") "]," TOOLS "}",&ONE)==0);
}
static void markers(void) {
    const char *failed[]={"error","Error: x","ERROR","TypeError","Traceback (most recent call last):",
        "tests FAILED","Failed to open","RuntimeException","java.lang.Exception",
        "exit code 1","Exit Code: 127","exit_code=2","\"exit_code\": 3","exitcode 255","exit code -1"};
    for (size_t i=0; i<sizeof failed/sizeof *failed; ++i)
        CHECK(rc_signals_failed_text(failed[i],strlen(failed[i])));
    const char *clean[]={"","ok","wrote 3 files","exit code 0","Exit code: 0","exit_code=0",
        "exit code","the terror","err","fail","traceroute ok","exceptional results"};
    /* "the terror"/"exceptional" still contain markers; the scan is conservative. */
    for (size_t i=0; i<6; ++i) CHECK(!rc_signals_failed_text(clean[i],strlen(clean[i])));
    CHECK(!rc_signals_failed_text(clean[6],strlen(clean[6])));
    CHECK(rc_signals_failed_text(clean[7],strlen(clean[7])));
    CHECK(!rc_signals_failed_text(clean[8],strlen(clean[8])));
    CHECK(!rc_signals_failed_text(clean[9],strlen(clean[9])));
    CHECK(!rc_signals_failed_text(clean[10],strlen(clean[10])));
    CHECK(rc_signals_failed_text(clean[11],strlen(clean[11])));
    CHECK(!rc_signals_failed_text(NULL,0));
    /* Embedded NUL: bounded length, not strlen. */
    CHECK(rc_signals_failed_text("ok\0error",8));
    CHECK(!rc_signals_failed_text("ok\0error",2));
    /* Bounded scan: head and tail windows only. */
    size_t n=3*RC_SIGNALS_SCAN_BYTES; char *big=malloc(n+1); CHECK(big);
    memset(big,'a',n); big[n]=0;
    memcpy(big+n/2,"error",5);
    CHECK(!rc_signals_failed_text(big,n));
    memcpy(big+n-5,"error",5);
    CHECK(rc_signals_failed_text(big,n));
    memset(big,'a',n); memcpy(big+10,"Traceback",9);
    CHECK(rc_signals_failed_text(big,n));
    free(big);
}
static void malformed(void) {
    CHECK(rc_signals_classify(NULL,&ONE)==0);
    CHECK(classify("{}",&ONE)==0);
    CHECK(classify("{\"messages\":[]}",&ONE)==0);
    CHECK(classify("{\"messages\":{}}",&ONE)==0);
    CHECK(classify("[]",&ONE)==0);
    CHECK(classify("{\"messages\":[1," RESULT("c1","ok") "]}",&ONE)==0);
    CHECK(classify("{\"messages\":[{\"content\":\"x\"}," RESULT("c1","ok") "]}",&ONE)==0);
    CHECK(classify("{\"messages\":[{\"role\":7,\"content\":\"x\"}," RESULT("c1","ok") "]}",&ONE)==0);
    CHECK(classify("{\"messages\":[{\"role\":\"wizard\",\"content\":\"x\"}," RESULT("c1","ok") "]}",&ONE)==0);
    /* Tool result content must be a plain string (unknown shape -> no class). */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") ",{\"role\":\"tool\",\"tool_call_id\":\"c1\",\"content\":[{\"type\":\"text\",\"text\":\"ok\"}]}]}",&ONE)==0);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") ",{\"role\":\"tool\",\"tool_call_id\":\"c1\"}]}",&ONE)==0);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") ",{\"role\":\"tool\",\"tool_call_id\":\"c1\",\"content\":null}]}",&ONE)==0);
    /* Malformed tools / tool_choice. */
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "],\"tools\":{}}",&ONE)==0);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "],\"tools\":[]}",&ONE)==0);
    CHECK(classify("{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "]," TOOLS ",\"tool_choice\":7}",&ONE)==0);
    /* Oversized message arrays are not classified. */
    json_t *b=load("{\"messages\":[]}"),*m=json_object_get(b,"messages");
    for (unsigned i=0; i<RC_SIGNALS_MAX_MESSAGES; ++i)
        json_array_append_new(m,load(i%2 ? RESULT("c","ok") : CALL("c")));
    CHECK(rc_signals_classify(b,&ONE)==RC_TASK_FINAL_ANSWER);
    json_array_insert_new(m,0,load(USER("s")));
    CHECK(rc_signals_classify(b,&ONE)==0);
    json_decref(b);
}
int main(void) {
    taxonomy();
    followup_and_final();
    failures_and_recovery();
    markers();
    malformed();
    puts("signals tests passed");
    return 0;
}
