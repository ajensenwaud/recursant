#include "recursant/tool_boundary.h"
#include <jansson.h>
#include <stdlib.h>
#include <string.h>

struct rc_tool_boundary { json_t *history, *assistant, *reasoning; uint32_t requirements; };
static bool text(json_t *v, const char *expected) {
    const char *s=json_string_value(v);
    return s && strcmp(s,expected)==0;
}
static bool nul_free(json_t *v) {
    return json_is_string(v) && json_string_length(v)==strlen(json_string_value(v));
}
bool rc_tool_text_content(json_t *content) {
    if (nul_free(content)) return true;
    size_t n=json_array_size(content);
    if (!json_is_array(content) || !n || n>RC_TOOL_MAX_TEXT_PARTS) return false;
    for (size_t i=0;i<n;++i) {
        json_t *part=json_array_get(content,i);
        if (!json_is_object(part) || json_object_size(part)!=2 ||
            !text(json_object_get(part,"type"),"text") || !nul_free(json_object_get(part,"text"))) return false;
    }
    return true;
}
/* Replayed reasoning_details (OpenRouter): a non-empty array of objects, on an
 * assistant message only. Structure here; provenance is checked against the
 * boundary's observed elements (replay) and by M2 (egress). */
static bool reasoning_shape(json_t *v) {
    json_t *r=json_object_get(v,"reasoning_details");
    if (!r) return true;
    if (!text(json_object_get(v,"role"),"assistant") || !json_is_array(r) ||
        !json_array_size(r) || json_array_size(r)>RC_TOOL_MAX_REASONING) return false;
    size_t i; json_t *e;
    json_array_foreach(r,i,e) if (!json_is_object(e)) return false;
    return true;
}
static size_t reasoning_member(json_t *v) { return json_object_get(v,"reasoning_details") ? 1u : 0u; }
static bool plain(json_t *v) {
    json_t *role=json_object_get(v,"role");
    return json_is_object(v) && json_object_size(v)==2+reasoning_member(v) && reasoning_shape(v) &&
        (text(role,"user") || text(role,"system") || text(role,"assistant")) &&
        rc_tool_text_content(json_object_get(v,"content"));
}
static bool calls_valid(json_t *v) {
    json_t *cs=json_object_get(v,"tool_calls"), *content=json_object_get(v,"content");
    if (!json_is_object(v) || json_object_size(v)!=(content?3u:2u)+reasoning_member(v) || !reasoning_shape(v) ||
        !text(json_object_get(v,"role"),"assistant") ||
        (content && !json_is_null(content) && !json_is_string(content)) ||
        !json_is_array(cs) || !json_array_size(cs) || json_array_size(cs)>RC_TOOL_MAX_CALLS)
        return false;
    for (size_t i=0;i<json_array_size(cs);++i) {
        json_t *c=json_array_get(cs,i), *id=json_object_get(c,"id"), *f=json_object_get(c,"function");
        if (!json_is_object(c) || json_object_size(c)!=3 || !json_is_string(id) ||
            !json_string_length(id) || json_string_length(id)>RC_TOOL_MAX_ID_BYTES ||
            !text(json_object_get(c,"type"),"function") || !json_is_object(f) ||
            json_object_size(f)!=2 || !json_is_string(json_object_get(f,"name")) ||
            !json_string_length(json_object_get(f,"name")) ||
            !json_is_string(json_object_get(f,"arguments"))) return false;
        for (size_t j=0;j<i;++j)
            if (json_equal(id,json_object_get(json_array_get(cs,j),"id"))) return false;
    }
    return true;
}
static rc_tool_status history_valid(rc_tool_boundary *b) {
    json_t *ids[RC_TOOL_MAX_HISTORY_CALLS];
    bool done[RC_TOOL_MAX_HISTORY_CALLS]={false};
    size_t used=0, start=0, pending=0, n=json_array_size(b->history);
    for (size_t i=0;i<=n;++i) {
        json_t *m=i==n?b->assistant:json_array_get(b->history,i);
        if (pending) {
            if (i==n || !json_is_object(m) || json_object_size(m)!=3 ||
                !text(json_object_get(m,"role"),"tool") ||
                !json_is_string(json_object_get(m,"content"))) return RC_TOOL_INVALID;
            size_t j=start;
            for (;j<used;++j) if (json_equal(ids[j],json_object_get(m,"tool_call_id"))) break;
            if (j==used || done[j]) return RC_TOOL_INVALID;
            done[j]=true; --pending; continue;
        }
        if (i<n && plain(m)) continue;
        if (!calls_valid(m)) return RC_TOOL_INVALID;
        json_t *cs=json_object_get(m,"tool_calls");
        size_t count=json_array_size(cs);
        b->requirements |= RC_TOOL_CAP_HISTORY | RC_TOOL_CAP_FUNCTIONS;
        if (count>1) b->requirements |= RC_TOOL_CAP_PARALLEL;
        if (count>RC_TOOL_MAX_HISTORY_CALLS-used) return RC_TOOL_LIMIT;
        start=used;
        for (size_t j=0;j<count;++j) {
            json_t *id=json_object_get(json_array_get(cs,j),"id");
            for (size_t k=0;k<used;++k) if (json_equal(ids[k],id)) return RC_TOOL_INVALID;
            ids[used++]=id;
        }
        pending=count;
    }
    return RC_TOOL_COMPLETE;
}
uint32_t rc_tool_boundary_requirements(const rc_tool_boundary *b) {
    return b ? b->requirements : 0;
}
bool rc_tool_boundary_candidate(const rc_tool_boundary *b, uint32_t known, uint32_t supported) {
    return b && (known & b->requirements)==b->requirements &&
        (supported & b->requirements)==b->requirements;
}
void rc_tool_boundary_free(rc_tool_boundary *b) {
    if (b) { json_decref(b->history); json_decref(b->assistant); json_decref(b->reasoning); free(b); }
}
rc_tool_status rc_tool_boundary_capture(const char *h, size_t hn,
    const char *a, size_t an, rc_tool_boundary **out) {
    if (!out) return RC_TOOL_INVALID;
    *out = NULL;
    if (!h || !a) return RC_TOOL_INVALID;
    if (hn > RC_TOOL_MAX_BYTES || an > RC_TOOL_MAX_BYTES) return RC_TOOL_LIMIT;
    rc_tool_boundary *b = calloc(1, sizeof *b);
    if (!b) return RC_TOOL_NOMEM;
    b->history = json_loadb(h, hn, JSON_REJECT_DUPLICATES, NULL);
    b->assistant = json_loadb(a, an, JSON_REJECT_DUPLICATES, NULL);
    if (!json_is_array(b->history) || !calls_valid(b->assistant)) {
        rc_tool_boundary_free(b); return RC_TOOL_INVALID;
    }
    if (json_array_size(b->history) + 1 +
        json_array_size(json_object_get(b->assistant,"tool_calls")) > RC_TOOL_MAX_MESSAGES) {
        rc_tool_boundary_free(b); return RC_TOOL_LIMIT;
    }
    rc_tool_status status=history_valid(b);
    if (status!=RC_TOOL_COMPLETE) { rc_tool_boundary_free(b); return status; }
    *out = b; return RC_TOOL_COMPLETE;
}
/* Replayed assistant equals the observed one. Function-call arguments are
 * JSON text: harnesses (e.g. pinned Hermes) replay them re-serialized, so when
 * the OBSERVED arguments decode to JSON, the replayed string must decode
 * (duplicates rejected) to a deep-equal value; whitespace/key order may differ,
 * every decoded member/value/array order must match. Non-JSON observed
 * arguments keep exact string equality. All other members stay exact. */
static bool args_equal(json_t *observed, json_t *replayed) {
    if (!json_is_string(observed) || !json_is_string(replayed)) return false;
    if (json_equal(observed, replayed)) return true;
    json_t *a = json_loadb(json_string_value(observed), json_string_length(observed), JSON_REJECT_DUPLICATES, NULL);
    if (!a) return false;
    json_t *b = json_loadb(json_string_value(replayed), json_string_length(replayed), JSON_REJECT_DUPLICATES, NULL);
    bool same = b && json_equal(a, b);
    json_decref(a); json_decref(b); return same;
}
/* No assistant text: "", null or absent are one value (the gateway observes ""
 * from a stream; pi and the OpenAI SDK replay null). Real text stays exact. */
static bool no_text(json_t *v) {
    return !v || json_is_null(v) || (json_is_string(v) && !json_string_length(v));
}
static size_t members(json_t *o) {
    return json_object_size(o) - (json_object_get(o, "content") ? 1u : 0u) - reasoning_member(o);
}
/* A replayed reasoning_details is optional; when present, every element must
 * equal an element the gateway observed with this very turn. */
static bool reasoning_replayed(json_t *replayed, json_t *observed_reasoning) {
    json_t *r = json_object_get(replayed, "reasoning_details");
    if (!r) return true;
    if (!reasoning_shape(replayed) || !observed_reasoning) return false;
    size_t i, j; json_t *e, *o;
    json_array_foreach(r, i, e) {
        bool found = false;
        json_array_foreach(observed_reasoning, j, o) if (json_equal(e, o)) { found = true; break; }
        if (!found) return false;
    }
    return true;
}
static bool assistant_equal(json_t *replayed, json_t *observed, json_t *observed_reasoning) {
    if (!json_is_object(replayed) || members(replayed) != members(observed) ||
        json_object_get(observed, "reasoning_details") || !reasoning_replayed(replayed, observed_reasoning)) return false;
    json_t *rt = json_object_get(replayed, "content"), *ot = json_object_get(observed, "content");
    if (!(no_text(rt) && no_text(ot)) && !(rt && ot && json_equal(rt, ot))) return false;
    const char *k; json_t *v;
    json_object_foreach(observed, k, v) {
        if (!strcmp(k, "content")) continue;
        json_t *r = json_object_get(replayed, k);
        if (!r) return false;
        if (strcmp(k, "tool_calls")) { if (!json_equal(r, v)) return false; continue; }
        if (!json_is_array(r) || json_array_size(r) != json_array_size(v)) return false;
        for (size_t i = 0; i < json_array_size(v); ++i) {
            json_t *oc = json_array_get(v, i), *rc = json_array_get(r, i);
            if (!json_is_object(rc) || json_object_size(rc) != json_object_size(oc)) return false;
            const char *ck; json_t *cv;
            json_object_foreach(oc, ck, cv) {
                json_t *rv = json_object_get(rc, ck);
                if (!rv) return false;
                if (strcmp(ck, "function")) { if (!json_equal(rv, cv)) return false; continue; }
                if (!json_is_object(rv) || json_object_size(rv) != json_object_size(cv) ||
                    !json_equal(json_object_get(rv, "name"), json_object_get(cv, "name")) ||
                    !args_equal(json_object_get(cv, "arguments"), json_object_get(rv, "arguments"))) return false;
            }
        }
    }
    return true;
}
static rc_tool_status replay_tree(const rc_tool_boundary *b, json_t *v);
rc_tool_status rc_tool_boundary_replay(const rc_tool_boundary *b, const char *m, size_t n) {
    if (!b || !m) return RC_TOOL_INVALID;
    if (n > RC_TOOL_MAX_BYTES) return RC_TOOL_LIMIT;
    json_t *v = json_loadb(m, n, JSON_REJECT_DUPLICATES, NULL);
    rc_tool_status status = replay_tree(b, v);
    json_decref(v);
    return status;
}
rc_tool_status rc_tool_boundary_replay_json(const rc_tool_boundary *b, json_t *messages) {
    if (!b || !messages) return RC_TOOL_INVALID;
    return replay_tree(b, messages);
}
static rc_tool_status replay_tree(const rc_tool_boundary *b, json_t *v) {
    size_t count = json_array_size(b->history);
    json_t *calls = json_object_get(b->assistant,"tool_calls");
    size_t nc = json_array_size(calls), total = json_array_size(v);
    bool seen[RC_TOOL_MAX_CALLS] = {false};
    bool ok = nc > 0 && nc <= RC_TOOL_MAX_CALLS && json_is_array(v) &&
        total >= count + 1 && total <= count + 1 + nc;
    for (size_t i=0; ok && i<count; ++i)
        ok = json_equal(json_array_get(v,i),json_array_get(b->history,i));
    if (ok) ok = assistant_equal(json_array_get(v,count), b->assistant, b->reasoning);
    for (size_t i=count+1; ok && i<total; ++i) {
        json_t *r = json_array_get(v,i);
        const char *role = json_string_value(json_object_get(r,"role"));
        json_t *id = json_object_get(r,"tool_call_id");
        ok = json_is_object(r) && json_object_size(r)==3 && role &&
            strcmp(role,"tool")==0 && json_is_string(id) &&
            json_is_string(json_object_get(r,"content"));
        size_t j=0;
        for (; ok && j<nc; ++j)
            if (json_equal(id,json_object_get(json_array_get(calls,j),"id"))) break;
        if (!ok || j==nc || seen[j]) { ok=false; break; }
        seen[j]=true;
    }
    return !ok ? RC_TOOL_INVALID : total==count+1+nc ? RC_TOOL_COMPLETE : RC_TOOL_INCOMPLETE;
}
bool rc_tool_boundary_set_reasoning(rc_tool_boundary *b, json_t *elements) {
    if (!b) return false;
    json_decref(b->reasoning); b->reasoning = NULL;
    if (!elements) return true;
    size_t i; json_t *e;
    if (!json_is_array(elements) || !json_array_size(elements) || json_array_size(elements)>RC_TOOL_MAX_REASONING) return false;
    json_array_foreach(elements, i, e) if (!json_is_object(e)) return false;
    b->reasoning = json_deep_copy(elements);
    return b->reasoning != NULL;
}
