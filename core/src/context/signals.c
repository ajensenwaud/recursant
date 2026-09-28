#include "recursant/signals.h"
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
/* Structured tool-result envelope (e.g. pinned Hermes terminal:
 * {"output":...,"exit_code":0,"error":null}). Field NAMES are protocol, not
 * failure text. Returns 1 failed, 0 clean, -1 not a recognized envelope. */
static int envelope_failed(const char *text, size_t length) {
    size_t i=0; while (i<length && (text[i]==' '||text[i]=='\n'||text[i]=='\t'||text[i]=='\r')) ++i;
    if (i==length || text[i]!='{' || length>(size_t)4*RC_SIGNALS_SCAN_BYTES) return -1;
    json_t *o=json_loadb(text,length,JSON_REJECT_DUPLICATES,NULL);
    if (!json_is_object(o)) { json_decref(o); return -1; }
    static const char *known="|output||exit_code||error||success||status||stdout||stderr|";
    bool recognized=false; int failed=0; const char *k; json_t *v;
    json_object_foreach(o,k,v) {
        char token[40];
        if (strlen(k)>30) { json_decref(o); return -1; }
        token[0]='|'; strcpy(token+1,k); strcat(token,"|");
        if (!strstr(known,token)) { json_decref(o); return -1; }
        recognized=true;
        if (!strcmp(k,"exit_code")) {
            if (!json_is_integer(v)) { if (!json_is_null(v)) failed=1; }
            else if (json_integer_value(v)!=0) failed=1;
        } else if (!strcmp(k,"error")) {
            if (!json_is_null(v) && !json_is_false(v) && !(json_is_string(v) && !json_string_length(v))) failed=1;
        } else if (!strcmp(k,"success")) {
            if (!json_is_true(v)) failed=1;
        } else if (!strcmp(k,"status")) {
            const char *s=json_string_value(v);
            if (!s || (strcmp(s,"ok") && strcmp(s,"success") && strcmp(s,"completed"))) failed=1;
        } else if (json_is_string(v)) {
            if (scan_text(json_string_value(v),json_string_length(v))) failed=1;
        } else if (!json_is_null(v)) failed=1;
    }
    json_decref(o);
    return recognized ? failed : -1;
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
uint64_t rc_signals_classify(json_t *body, const rc_signal_scope *scope) {
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
    unsigned seen=0, run=0; bool running=true, failed_any=false;
    for (size_t i=n; i-- > 0 && seen<RC_SIGNALS_WINDOW;) {
        json_t *m=json_array_get(messages,i);
        if (role_is(m,"assistant")) continue;
        if (!role_is(m,"tool")) { running=false; continue; }
        json_t *content=json_object_get(m,"content");
        if (!json_is_string(content)) return 0;
        bool failed=rc_signals_failed_text(json_string_value(content),json_string_length(content));
        ++seen;
        if (failed) { failed_any=true; if (running) ++run; }
        else running=false;
    }
    if (run>=2) return RC_TASK_RECOVERY;
    if (failed_any) return 0;
    return offered ? RC_TASK_TOOL_FOLLOWUP_OK : RC_TASK_FINAL_ANSWER;
}
bool rc_task_qualifiable(const char *name, uint64_t *bit) {
    if (!name || !bit) return false;
    if (!strcmp(name,"format_simple")) { *bit=RC_TASK_FORMAT_SIMPLE; return true; }
    if (!strcmp(name,"tool_followup_ok")) { *bit=RC_TASK_TOOL_FOLLOWUP_OK; return true; }
    if (!strcmp(name,"final_answer")) { *bit=RC_TASK_FINAL_ANSWER; return true; }
    return false;
}
const char *rc_task_name(uint64_t bit) {
    switch (bit) {
    case 0: return "none";
    case RC_TASK_FORMAT_SIMPLE: return "format_simple";
    case RC_TASK_TOOL_FOLLOWUP_OK: return "tool_followup_ok";
    case RC_TASK_FINAL_ANSWER: return "final_answer";
    case RC_TASK_RECOVERY: return "recovery";
    default: return "invalid";
    }
}
