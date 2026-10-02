#include "recursant/signals.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
static const rc_signal_scope ONE={.completed_turns=1};
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
    CHECK(RC_TASK_DELEGATED_START==16);
    CHECK(rc_task_qualifiable("delegated_start",&bit) && bit==RC_TASK_DELEGATED_START);
    CHECK(!strcmp(rc_task_name(RC_TASK_DELEGATED_START),"delegated_start"));
    CHECK(!strcmp(rc_task_name(32),"invalid"));
    CHECK(!strcmp(rc_task_name(17),"invalid"));
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
    const rc_signal_scope zero={.completed_turns=0};
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
static void structured_envelopes(void) {
    /* Pinned Hermes terminal results are JSON envelopes. The literal key
     * "error": null or exit_code 0 is not a failure marker. */
    const char *clean[]={"{\"output\": \"/workspace\", \"exit_code\": 0, \"error\": null}",
        "{\"output\": \"\", \"exit_code\": 0, \"error\": null}",
        "{\"output\": \"{\\\"finish\\\": {}, \\\"makespan\\\": 0}\", \"exit_code\": 0, \"error\": null}",
        "{\"success\": true, \"error\": \"\"}", "{\"exit_code\": 0}"};
    for (size_t i=0; i<sizeof clean/sizeof *clean; ++i) CHECK(!rc_signals_failed_text(clean[i],strlen(clean[i])));
    const char *failed[]={"{\"output\": \"\", \"exit_code\": 1, \"error\": null}",
        "{\"output\": \"x\", \"exit_code\": 0, \"error\": \"permission denied\"}",
        "{\"output\": \"Traceback (most recent call last):\", \"exit_code\": 0, \"error\": null}",
        "{\"output\": \"3 tests FAILED\", \"exit_code\": 0, \"error\": null}",
        "{\"success\": false}", "{\"exit_code\": -9, \"error\": null}", "{\"status\": \"error\"}"};
    for (size_t i=0; i<sizeof failed/sizeof *failed; ++i) CHECK(rc_signals_failed_text(failed[i],strlen(failed[i])));
    /* Envelope with an error inside output text still counts (plain scan of output). */
    const char *follow="{\"messages\":[" USER("s") "," CALL("c1") ",{\"role\":\"tool\",\"tool_call_id\":\"c1\",\"content\":\"{\\\"output\\\": \\\"ok\\\", \\\"exit_code\\\": 0, \\\"error\\\": null}\"}]," TOOLS "}";
    CHECK(classify(follow,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
}
static void structured_payloads(void) {
    /* Recorded pinned-Hermes shapes (D-ma2). Payload fields are data: a source
     * file mentioning ValueError, a diff adding an exception, a delegate summary
     * about error handling, or a passing test called test_error_* are clean. */
    const char *clean[]={
        "{\"content\": \"1|def f(x):\\n2|    raise ValueError('bad')  # error handling\", \"total_lines\": 2, \"file_size\": 40, \"truncated\": false, \"is_binary\": false, \"is_image\": false, \"not_found\": false}",
        "{\"bytes_written\": 120, \"dirs_created\": true, \"verified\": true, \"lint\": {\"status\": \"ok\", \"output\": \"\"}, \"resolved_path\": \"/w/a.py\", \"files_modified\": [\"/w/a.py\"]}",
        "{\"success\": true, \"diff\": \"+    except Exception as error:\\n+        raise\", \"files_modified\": [\"/w/a.py\"]}",
        "{\"results\": [{\"task_index\": 0, \"status\": \"completed\", \"summary\": \"Added error handling; raises ValueError on bad input\"}], \"total_duration_seconds\": 3.2, \"note\": \"\"}",
        "{\"total_count\": 2, \"matches_text\": \"a.py\\n  3: raise TypeError\", \"matches_format\": \"path-grouped\"}",
        "{\"output\": \"test_error_handling (t.T.test_error_handling) ... ok\\n\\nOK\", \"exit_code\": 0, \"error\": null}",
        "{\"status\": \"success\", \"output\": \"no exceptions raised\", \"exit_code\": 0}"};
    for (size_t i=0; i<sizeof clean/sizeof *clean; ++i) CHECK(!rc_signals_failed_text(clean[i],strlen(clean[i])));
    /* Outcome fields still decide failures, including after a harness note. */
    const char *failed[]={
        "{\"content\": \"\", \"total_lines\": 0, \"error\": \"File not found: /w/x.py\", \"not_found\": true}",
        "{\"error\": \"Refusing to overwrite a.py\", \"path\": \"a.py\", \"resolved_path\": \"/w/a.py\", \"stale_write_blocked\": true}",
        "{\"success\": false, \"error\": \"Could not find a match for old_string\"}",
        "{\"results\": [{\"task_index\": 0, \"status\": \"failed\", \"summary\": \"ok\"}], \"note\": \"\"}",
        "{\"total_count\": 0, \"error\": \"Path not found: x\"}",
        "{\"output\": \"x\", \"exit_code\": 126, \"error\": null, \"hint\": \"Exit 126\"}\n\n[hermes note: 3rd identical call]",
        "{\"output\": \"ERROR: test_x (t.T.test_x)\\nFAILED (errors=1)\", \"exit_code\": 0, \"error\": null}",
        "{\"status\": \"error\", \"output\": \"\\n--- stderr ---\\nTraceback (most recent call last):\", \"exit_code\": 1}"};
    for (size_t i=0; i<sizeof failed/sizeof *failed; ++i) CHECK(rc_signals_failed_text(failed[i],strlen(failed[i])));
    /* Not a JSON object, or trailing text that is not one bracketed note:
     * the broad word scan applies as before. */
    CHECK(rc_signals_failed_text("raise ValueError",16));
    const char *trailing="{\"exit_code\": 0} then an error";
    CHECK(rc_signals_failed_text(trailing,strlen(trailing)));
}
static void rejected_invocations(void) {
    /* Pilot-2/3: Hermes rejects a malformed call before executing anything:
     * {"error":"notify/heartbeat only apply to background commands ..."}.
     * The tool never ran: it is not an executed failure (no recovery run) and
     * not a success. It is transparent to the window once an executed clean
     * result follows; a trailing rejection itself gets no class. */
#define REJ "{\\\"error\\\": \\\"notify/heartbeat only apply to background commands\\\"}"
#define OKE "{\\\"output\\\": \\\"3 passed\\\", \\\"exit_code\\\": 0, \\\"error\\\": null}"
    /* Fix 2: up to RC_SIGNALS_MAX_REJECTIONS trailing rejections after a clean
     * executed window keep the clean class (the retry is an argument repair;
     * baseline-direct gpt-4.1 made the identical rejected calls). A longer
     * rejection loop gets no class (baseline) so a stronger owner may break it. */
    const char *one="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2",REJ) "]," TOOLS "}";
    CHECK(classify(one,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    const char *trailing="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2",REJ) "," CALL("c3") "," RESULT("c3",REJ) "]," TOOLS "}";
    CHECK(classify(trailing,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    const char *three="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2",REJ) "," CALL("c3") "," RESULT("c3",REJ) "," CALL("c4") "," RESULT("c4",REJ) "]," TOOLS "}";
    CHECK(classify(three,&ONE)==0);
    /* Only rejections, no executed result at all: no class. */
    const char *only="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1",REJ) "]," TOOLS "}";
    CHECK(classify(only,&ONE)==0);
    /* A trailing rejection never converts an executed failure into success. */
    const char *failed_then_rej="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","Traceback (most recent call last)") "," CALL("c2") "," RESULT("c2",REJ) "]," TOOLS "}";
    CHECK(classify(failed_then_rej,&ONE)==0);
    /* Real Hermes repeated-call note is still a rejection; other trailing text is not. */
    const char *noted="{\"error\": \"notify/heartbeat only apply\"}\n\n[hermes note: this is the 3rd consecutive identical call. Do not repeat it.]";
    const char *junk="{\"error\": \"x\"}\n\nTraceback (most recent call last)";
    const char *two_notes="{\"error\": \"x\"}\n[a]\n[b]";
    json_t *b=json_pack("{s:[{s:s,s:s},{s:s,s:n,s:[{s:s,s:s,s:{s:s,s:s}}]},{s:s,s:s,s:s},{s:s,s:n,s:[{s:s,s:s,s:{s:s,s:s}}]},{s:s,s:s,s:s}],s:[{s:s,s:{s:s}}]}",
        "messages","role","user","content","s",
        "role","assistant","content","tool_calls","id","c1","type","function","function","name","f","arguments","{}",
        "role","tool","tool_call_id","c1","content","ok",
        "role","assistant","content","tool_calls","id","c2","type","function","function","name","f","arguments","{}",
        "role","tool","tool_call_id","c2","content",noted,
        "tools","type","function","function","name","f");
    CHECK(b && rc_signals_classify(b,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    json_object_set_new(json_array_get(json_object_get(b,"messages"),4),"content",json_string(junk));
    CHECK(rc_signals_classify(b,&ONE)==0);
    json_object_set_new(json_array_get(json_object_get(b,"messages"),4),"content",json_string(two_notes));
    CHECK(rc_signals_classify(b,&ONE)==0);
    json_decref(b);
    const char *after="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2",REJ) "," CALL("c3") "," RESULT("c3",REJ) "," CALL("c4") "," RESULT("c4",REJ) "," CALL("c5") "," RESULT("c5",OKE) "]," TOOLS "}";
    CHECK(classify(after,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* Rejections do not hide an EXECUTED failure in the window. */
    const char *hidden="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","Traceback (most recent call last)") "," CALL("c2") "," RESULT("c2",REJ) "," CALL("c3") "," RESULT("c3",OKE) "]," TOOLS "}";
    CHECK(classify(hidden,&ONE)==0);
    /* Executed failures around a rejection still form a recovery run. */
    const char *run="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ERROR: x") "," CALL("c2") "," RESULT("c2",REJ) "," CALL("c3") "," RESULT("c3","command failed") "]," TOOLS "}";
    CHECK(classify(run,&ONE)==RC_TASK_RECOVERY);
    /* Only an exact single-key {"error": nonempty string} is a rejection. */
    CHECK(rc_signals_failed_text("{\"error\": \"x\"}",14));
    const char *exec_err="{\"output\": \"\", \"exit_code\": 0, \"error\": \"x\"}";
    const char *after_exec="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","{\\\"output\\\": \\\"\\\", \\\"exit_code\\\": 1, \\\"error\\\": \\\"x\\\"}") "," CALL("c2") "," RESULT("c2",OKE) "]," TOOLS "}";
    CHECK(rc_signals_failed_text(exec_err,strlen(exec_err)));
    CHECK(classify(after_exec,&ONE)==0);
    const char *empty_err="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","{\\\"error\\\": \\\"\\\"}") "," CALL("c2") "," RESULT("c2",OKE) "]," TOOLS "}";
    CHECK(classify(empty_err,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK); /* empty error = clean envelope */
    /* Many rejections cannot scan unboundedly; still bounded by MAX_MESSAGES. */
#undef REJ
#undef OKE
}
#define CALLA(id,name,args) "{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"" id "\",\"type\":\"function\",\"function\":{\"name\":\"" name "\",\"arguments\":\"" args "\"}}]}"
static void repeat_loop(void) {
    /* context.repeat_escalation: the newest call (name + canonical arguments)
     * made >= RC_SIGNALS_REPEAT_MIN times among the last RC_SIGNALS_REPEAT_WINDOW
     * calls is a stuck agent: escalate, whatever its results say. */
    const rc_signal_scope on={.completed_turns=1,.repeat_escalation=true};
    const char *three="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2","ok") "," CALL("c3") "," RESULT("c3","ok") "]," TOOLS "}";
    CHECK(classify(three,&ONE)==RC_TASK_TOOL_FOLLOWUP_OK);   /* off: unchanged */
    CHECK(classify(three,&on)==RC_TASK_RECOVERY);
    const char *two="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2","ok") "]," TOOLS "}";
    CHECK(classify(two,&on)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* Key order does not matter; values and names do. */
    const char *reordered="{\"messages\":[" USER("s") ","
        CALLA("c1","run","{\\\"a\\\":1,\\\"b\\\":2}") "," RESULT("c1","ok") ","
        CALLA("c2","run","{\\\"b\\\":2,\\\"a\\\":1}") "," RESULT("c2","ok") ","
        CALLA("c3","run","{\\\"a\\\": 1, \\\"b\\\": 2}") "," RESULT("c3","ok") "]," TOOLS "}";
    CHECK(classify(reordered,&on)==RC_TASK_RECOVERY);
    const char *values="{\"messages\":[" USER("s") ","
        CALLA("c1","run","{\\\"a\\\":1}") "," RESULT("c1","ok") ","
        CALLA("c2","run","{\\\"a\\\":2}") "," RESULT("c2","ok") ","
        CALLA("c3","run","{\\\"a\\\":1}") "," RESULT("c3","ok") "]," TOOLS "}";
    CHECK(classify(values,&on)==RC_TASK_TOOL_FOLLOWUP_OK);
    const char *names="{\"messages\":[" USER("s") ","
        CALLA("c1","read","{}") "," RESULT("c1","ok") ","
        CALLA("c2","list","{}") "," RESULT("c2","ok") ","
        CALLA("c3","read","{}") "," RESULT("c3","ok") "]," TOOLS "}";
    CHECK(classify(names,&on)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* Only the last six calls count. */
    const char *old="{\"messages\":[" USER("s") ","
        CALLA("c1","run","{}") "," RESULT("c1","ok") "," CALLA("c2","run","{}") "," RESULT("c2","ok") ","
        CALLA("c3","x1","{}") "," RESULT("c3","ok") "," CALLA("c4","x2","{}") "," RESULT("c4","ok") ","
        CALLA("c5","x3","{}") "," RESULT("c5","ok") "," CALLA("c6","x4","{}") "," RESULT("c6","ok") ","
        CALLA("c7","x5","{}") "," RESULT("c7","ok") "," CALLA("c8","run","{}") "," RESULT("c8","ok") "]," TOOLS "}";
    CHECK(classify(old,&on)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* Unparseable arguments compare as text. */
    const char *raw="{\"messages\":[" USER("s") ","
        CALLA("c1","run","not json") "," RESULT("c1","ok") "," CALLA("c2","run","not json") "," RESULT("c2","ok") ","
        CALLA("c3","run","not json") "," RESULT("c3","ok") "]," TOOLS "}";
    CHECK(classify(raw,&on)==RC_TASK_RECOVERY);
    /* A trailing harness rejection stays neutral (rejection rules decide). */
    const char *rej="{\"messages\":[" USER("s") "," CALL("c1") "," RESULT("c1","ok") "," CALL("c2") "," RESULT("c2","ok") "," CALL("c3") "," RESULT("c3","{\\\"error\\\": \\\"bad arguments\\\"}") "]," TOOLS "}";
    CHECK(classify(rej,&on)==RC_TASK_TOOL_FOLLOWUP_OK);
    /* Parallel calls in one turn count individually. */
    const char *parallel="{\"messages\":[" USER("s") ",{\"role\":\"assistant\",\"content\":null,\"tool_calls\":["
        "{\"id\":\"a\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{}\"}},"
        "{\"id\":\"b\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{}\"}},"
        "{\"id\":\"c\",\"type\":\"function\",\"function\":{\"name\":\"f\",\"arguments\":\"{}\"}}]},"
        RESULT("a","ok") "," RESULT("b","ok") "," RESULT("c","ok") "]," TOOLS "}";
    CHECK(classify(parallel,&on)==RC_TASK_RECOVERY);
}
#undef CALLA
int main(void) {
    repeat_loop();
    rejected_invocations();
    structured_envelopes();
    structured_payloads();
    taxonomy();
    followup_and_final();
    failures_and_recovery();
    markers();
    malformed();
    puts("signals tests passed");
    return 0;
}
