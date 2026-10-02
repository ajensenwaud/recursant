#include "recursant/signals.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Deterministic, bounded structured-signal classifier (see signals.h).
 *
 * Mapping (conservative, heuristic; never verified success):
 *   completed_turns == 0 or malformed input            -> 0
 *   last message not a string-content tool result      -> 0
 *   trailing run of >= 2 failed tool results (assistant
 *     turns between them allowed; user/system breaks)   -> RECOVERY
 *   any failure among the last RC_SIGNALS_WINDOW
 *     tool results otherwise                           -> 0
 *   clean window, tools offered, tool_choice != "none" -> TOOL_FOLLOWUP_OK
 *   clean window, no tools or tool_choice == "none"    -> FINAL_ANSWER
 * FORMAT_SIMPLE is produced only by the async interpreter, never here. */
static unsigned char lower(unsigned char c) { return c>='A'&&c<='Z' ? (unsigned char)(c-'A'+'a') : c; }
/* Case-insensitive match of lowercase needle at p (bounded by end). */
static bool at(const char *p, const char *end, const char *needle) {
    size_t n=strlen(needle);
    if ((size_t)(end-p)<n) return false;
    for (size_t i=0; i<n; ++i) if (lower((unsigned char)p[i])!=(unsigned char)needle[i]) return false;
    return true;
}
/* "exit" [ _-]* "code" [ \t:="']* ["-"] digits, nonzero value -> failure. */
static bool nonzero_exit(const char *p, const char *end) {
    if (!at(p,end,"exit")) return false;
    p+=4;
    while (p<end && (*p==' '||*p=='_'||*p=='-')) ++p;
    if (!at(p,end,"code")) return false;
    p+=4;
    while (p<end && (*p==' '||*p=='\t'||*p==':'||*p=='='||*p=='"'||*p=='\'')) ++p;
    if (p<end && *p=='-') ++p;
    bool digits=false, nonzero=false;
    while (p<end && *p>='0' && *p<='9') { digits=true; if (*p!='0') nonzero=true; ++p; }
    return digits && nonzero;
}
static bool scan(const char *p, const char *end) {
    static const char *markers[]={"error","traceback","failed","exception"};
    for (; p<end; ++p) {
        for (size_t m=0; m<sizeof markers/sizeof *markers; ++m) if (at(p,end,markers[m])) return true;
        if (nonzero_exit(p,end)) return true;
    }
    return false;
}
static bool scan_text(const char *text, size_t length) {
    const char *end=text+length;
    if (length<=2*RC_SIGNALS_SCAN_BYTES) return scan(text,end);
    return scan(text,text+RC_SIGNALS_SCAN_BYTES) || scan(end-RC_SIGNALS_SCAN_BYTES,end);
}
/* Structured tool results. Most agent tools (pinned Hermes: terminal, read_file,
 * write_file, patch, search_files, execute_code, delegate_task) return a JSON
 * object whose outcome fields say whether the call worked. Those fields decide;
 * payload fields (file content, diffs, search matches, summaries) are DATA and
 * are never scanned for failure words: reading source that mentions ValueError
 * is not a failed step. Only free command output is scanned, and only when no
 * exit code was reported. A JSON object may be followed by one bracketed
 * harness note. Returns 1 failed, 0 clean, -1 not a JSON object. */
static bool contains(const char *t, size_t n, const char *needle) {
    size_t m=strlen(needle);
    for (size_t i=0;i+m<=n;++i) if (!memcmp(t+i,needle,m)) return true;
    return false;
}
/* Case-sensitive markers that ordinary data and passing test names do not
 * produce: unittest/pytest failure summaries and Python exceptions. */
static bool strong_markers(const char *t, size_t n) {
    static const char *markers[]={"Traceback (most recent call last)","FAILED","ERROR:","Error:","AssertionError"};
    for (size_t k=0;k<sizeof markers/sizeof *markers;++k) if (contains(t,n,markers[k])) return true;
    return false;
}
static bool ok_status(json_t *v) {
    const char *s=json_string_value(v);
    return s && (!strcmp(s,"ok") || !strcmp(s,"success") || !strcmp(s,"completed"));
}
static bool error_value(json_t *v) {
    return v && !json_is_null(v) && !json_is_false(v) && !(json_is_string(v) && !json_string_length(v));
}
static int envelope_failed(const char *text, size_t length) {
    size_t i=0; while (i<length && (text[i]==' '||text[i]=='\n'||text[i]=='\t'||text[i]=='\r')) ++i;
    if (i==length || text[i]!='{' || length>(size_t)64*RC_SIGNALS_SCAN_BYTES) return -1;
    json_error_t error;
    json_t *o=json_loadb(text+i,length-i,JSON_REJECT_DUPLICATES|JSON_DISABLE_EOF_CHECK,&error);
    if (!json_is_object(o)) { json_decref(o); return -1; }
    size_t j=i+(size_t)error.position;
    while (j<length && (text[j]==' '||text[j]=='\n'||text[j]=='\t'||text[j]=='\r')) ++j;
    if (j<length && (text[j]!='[' || text[length-1]!=']')) { json_decref(o); return -1; }
    int failed=0;
    json_t *exit_code=json_object_get(o,"exit_code"), *status=json_object_get(o,"status");
    json_t *success=json_object_get(o,"success"), *results=json_object_get(o,"results");
    if (error_value(json_object_get(o,"error"))) failed=1;
    if (exit_code && !(json_is_integer(exit_code) && json_integer_value(exit_code)==0) && !json_is_null(exit_code)) failed=1;
    if (success && !json_is_true(success)) failed=1;
    if (status && !ok_status(status)) failed=1;
    if (json_is_true(json_object_get(o,"not_found"))) failed=1;
    /* Delegated work (e.g. delegate_task): each child's own status. */
    if (json_is_array(results)) {
        size_t k; json_t *r;
        json_array_foreach(results,k,r) {
            json_t *st=json_object_get(r,"status");
            if (json_is_object(r) && st && !ok_status(st)) failed=1;
        }
    }
    /* Command output still counts: a pipeline such as "tests | tail" exits 0
     * when the tests fail. With an exit code reported, only unambiguous
     * failure markers count (a test named test_error_handling passing is not
     * a failure); without one, the broad markers apply as before. */
    static const char *outputs[]={"output","stdout","stderr"};
    for (size_t k=0;!failed&&k<3;++k) {
        json_t *v=json_object_get(o,outputs[k]);
        if (!json_is_string(v)) continue;
        const char *t=json_string_value(v); size_t n=json_string_length(v);
        if (exit_code ? strong_markers(t,n) : scan_text(t,n)) failed=1;
    }
    json_decref(o);
    return failed;
}
bool rc_signals_failed_text(const char *text, size_t length) {
    if (!text) return false;
    int envelope=envelope_failed(text,length);
    if (envelope>=0) return envelope==1;
    return scan_text(text,length);
}
static bool role_is(json_t *m, const char *role) {
    const char *r=json_string_value(json_object_get(m,"role"));
    return r && !strcmp(r,role);
}
static bool known_role(json_t *m) {
    return role_is(m,"system")||role_is(m,"developer")||role_is(m,"user")||
        role_is(m,"assistant")||role_is(m,"tool");
}
/* Harness rejection of a malformed call before execution (e.g. pinned Hermes
 * {"error":"notify/heartbeat only apply to background commands ..."}): an
 * object with exactly one key "error" holding a nonempty string, optionally
 * followed by one trailing bracketed harness note line (Hermes appends
 * "\n\n[hermes note: ...]" to repeated identical calls). The tool did not
 * run, so it is neither an executed failure nor a success. */
static bool rejected_call(const char *text, size_t length) {
    size_t i=0; while (i<length && (text[i]==' '||text[i]=='\n'||text[i]=='\t'||text[i]=='\r')) ++i;
    if (i==length || text[i]!='{' || length>(size_t)RC_SIGNALS_SCAN_BYTES) return false;
    json_error_t error;
    json_t *o=json_loadb(text+i,length-i,JSON_REJECT_DUPLICATES|JSON_DISABLE_EOF_CHECK,&error);
    json_t *e=json_object_get(o,"error");
    bool r=json_is_object(o) && json_object_size(o)==1 && json_is_string(e) && json_string_length(e);
    json_decref(o);
    if (!r) return false;
    size_t j=i+(size_t)error.position;
    while (j<length && (text[j]==' '||text[j]=='\n'||text[j]=='\t'||text[j]=='\r')) ++j;
    if (j==length) return true;
    /* Exactly one bracketed note ending the text, no newline inside. */
    if (text[j]!='[' || text[length-1]!=']') return false;
    for (size_t k=j+1; k+1<length; ++k) if (text[k]=='\n'||text[k]=='['||text[k]==']') return false;
    return true;
}
/* "name\x1f" + compact sorted-key arguments (raw text when not JSON, or when
 * larger than the envelope bound). NULL when the call has no name/arguments
 * or on allocation failure. Caller frees. */
static char *call_key(json_t *call) {
    json_t *f=json_object_get(call,"function"), *a=json_object_get(f,"arguments");
    const char *name=json_string_value(json_object_get(f,"name")), *args=json_string_value(a);
    if (!name || !args) return NULL;
    char *canon=NULL;
    if (json_string_length(a)<=(size_t)64*RC_SIGNALS_SCAN_BYTES) {
        json_error_t error; json_t *v=json_loadb(args,json_string_length(a),JSON_DECODE_ANY,&error);
        if (v) { canon=json_dumps(v,JSON_COMPACT|JSON_SORT_KEYS|JSON_ENCODE_ANY); json_decref(v); }
    }
    const char *use=canon?canon:args; size_t n=strlen(name)+strlen(use)+2;
    char *key=malloc(n);
    if (key) snprintf(key,n,"%s\x1f%s",name,use);
    free(canon); return key;
}
static bool stalled(json_t *messages, size_t n) {
    char *keys[RC_SIGNALS_REPEAT_WINDOW]={0}; unsigned k=0; bool ok=true;
    for (size_t i=n; ok && i-- > 0 && k<RC_SIGNALS_REPEAT_WINDOW;) {
        json_t *m=json_array_get(messages,i);
        if (!role_is(m,"assistant")) continue;
        json_t *calls=json_object_get(m,"tool_calls");
        for (size_t c=json_array_size(calls); c-- > 0 && k<RC_SIGNALS_REPEAT_WINDOW;)
            if (!(keys[k++]=call_key(json_array_get(calls,c)))) { ok=false; break; }
    }
    unsigned same=0;
    for (unsigned i=0; ok && i<k; ++i) if (!strcmp(keys[i],keys[0])) ++same;
    for (unsigned i=0; i<k; ++i) free(keys[i]);
    return ok && same>=RC_SIGNALS_REPEAT_MIN;
}
static uint64_t classify(json_t *body, const rc_signal_scope *scope, bool *executed_failure) {
    *executed_failure=false;
    if (!json_is_object(body) || !scope || !scope->completed_turns) return 0;
    json_t *messages=json_object_get(body,"messages");
    size_t n=json_array_size(messages);
    if (!json_is_array(messages) || !n || n>RC_SIGNALS_MAX_MESSAGES) return 0;
    for (size_t i=0; i<n; ++i) {
        json_t *m=json_array_get(messages,i);
        if (!json_is_object(m) || !known_role(m)) return 0;
    }
    json_t *tools=json_object_get(body,"tools"), *choice=json_object_get(body,"tool_choice");
    if (tools && (!json_is_array(tools) || !json_array_size(tools))) return 0;
    if (choice && !json_is_string(choice) && !json_is_object(choice)) return 0;
    bool offered=tools && !(json_is_string(choice) && !strcmp(json_string_value(choice),"none"));
    if (!role_is(json_array_get(messages,n-1),"tool")) return 0;
    unsigned seen=0, run=0, rejected=0; bool running=true, failed_any=false;
    for (size_t i=n; i-- > 0 && seen<RC_SIGNALS_WINDOW;) {
        json_t *m=json_array_get(messages,i);
        if (role_is(m,"assistant")) continue;
        if (!role_is(m,"tool")) { running=false; continue; }
        json_t *content=json_object_get(m,"content");
        if (!json_is_string(content)) return 0;
        const char *text=json_string_value(content); size_t length=json_string_length(content);
        /* Rejected (never executed) calls are transparent to the window and
         * the recovery run. Trailing ones are counted: a short run is an
         * argument repair, a long run is a loop (see signals.h). */
        if (rejected_call(text,length)) { if (!seen) ++rejected; continue; }
        bool failed=rc_signals_failed_text(text,length);
        ++seen;
        if (failed) { failed_any=true; if (running) ++run; }
        else running=false;
    }
    *executed_failure=failed_any;
    if (!seen || rejected>RC_SIGNALS_MAX_REJECTIONS) return 0;
    if (run>=2) return RC_TASK_RECOVERY;
    if (scope->repeat_escalation && !rejected && stalled(messages,n)) return RC_TASK_RECOVERY;
    if (failed_any) return 0;
    return offered ? RC_TASK_TOOL_FOLLOWUP_OK : RC_TASK_FINAL_ANSWER;
}
uint64_t rc_signals_classify(json_t *body, const rc_signal_scope *scope) {
    bool failed; return classify(body,scope,&failed);
}
bool rc_signals_recent_failure(json_t *body) {
    rc_signal_scope one={.completed_turns=1}; bool failed; (void)classify(body,&one,&failed); return failed;
}
bool rc_task_qualifiable(const char *name, uint64_t *bit) {
    if (!name || !bit) return false;
    if (!strcmp(name,"format_simple")) { *bit=RC_TASK_FORMAT_SIMPLE; return true; }
    if (!strcmp(name,"tool_followup_ok")) { *bit=RC_TASK_TOOL_FOLLOWUP_OK; return true; }
    if (!strcmp(name,"final_answer")) { *bit=RC_TASK_FINAL_ANSWER; return true; }
    if (!strcmp(name,"delegated_start")) { *bit=RC_TASK_DELEGATED_START; return true; }
    return false;
}
const char *rc_task_name(uint64_t bit) {
    switch (bit) {
    case 0: return "none";
    case RC_TASK_FORMAT_SIMPLE: return "format_simple";
    case RC_TASK_TOOL_FOLLOWUP_OK: return "tool_followup_ok";
    case RC_TASK_FINAL_ANSWER: return "final_answer";
    case RC_TASK_RECOVERY: return "recovery";
    case RC_TASK_DELEGATED_START: return "delegated_start";
    default: return "invalid";
    }
}
