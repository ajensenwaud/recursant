#include "recursant/cost.h"
#include <math.h>
#include <string.h>
bool rc_price_valid(const rc_price *p) {
    return p && isfinite(p->input_per_mtok) && isfinite(p->output_per_mtok) &&
        isfinite(p->cached_input_per_mtok) && p->input_per_mtok>=0 &&
        p->output_per_mtok>=0 && p->cached_input_per_mtok>=0 &&
        p->cached_input_per_mtok<=p->input_per_mtok;
}
static uint64_t add(uint64_t a, uint64_t b) { return a>UINT64_MAX-b ? UINT64_MAX : a+b; }
static uint64_t quarter(uint64_t bytes) { return bytes/4 + (bytes%4!=0); }
uint64_t rc_estimate_prompt_tokens(const rc_usage_observation *last,
        uint64_t appended_bytes, uint64_t request_bytes) {
    if (last && last->known)
        return add(add(last->prompt_tokens, last->completion_tokens), quarter(appended_bytes));
    return quarter(request_bytes);
}
uint64_t rc_estimate_output_tokens(uint64_t max_tokens, uint64_t expected_output) {
    if (!expected_output) expected_output=RC_COST_DEFAULT_OUTPUT_TOKENS;
    return max_tokens<expected_output ? max_tokens : expected_output;
}
uint64_t rc_cached_input_tokens(bool is_owner, const rc_usage_observation *last,
        uint64_t prompt_tokens) {
    if (!is_owner || !last || !last->known || !last->cached_tokens) return 0;
    return last->prompt_tokens<prompt_tokens ? last->prompt_tokens : prompt_tokens;
}
double rc_turn_cost(const rc_price *p, uint64_t prompt_tokens,
        uint64_t cached_tokens, uint64_t output_tokens) {
    if (!rc_price_valid(p)) return -1;
    if (cached_tokens>prompt_tokens) cached_tokens=prompt_tokens;
    double cost=((double)(prompt_tokens-cached_tokens)*p->input_per_mtok +
        (double)cached_tokens*p->cached_input_per_mtok +
        (double)output_tokens*p->output_per_mtok)/1e6;
    return isfinite(cost) ? cost : -1;
}
static bool number(json_t *o, const char *k, double *out) {
    json_t *v=json_object_get(o,k);
    if (!json_is_number(v)) return false;
    double d=json_number_value(v);
    if (!isfinite(d) || d<0) return false;
    *out=d; return true;
}
bool rc_candidate_cost_parse(json_t *candidate, rc_candidate_cost *out) {
    if (!json_is_object(candidate) || !out) return false;
    json_t *fixed=json_object_get(candidate,"expected_task_cost"),*price=json_object_get(candidate,"price");
    if ((fixed!=NULL)==(price!=NULL)) return false;
    rc_candidate_cost c={0};
    if (fixed) {
        if (!number(candidate,"expected_task_cost",&c.fixed)) return false;
        *out=c; return true;
    }
    if (!json_is_object(price)) return false;
    const char *k; json_t *v;
    json_object_foreach(price,k,v) {
        (void)v;
        if (strcmp(k,"input_per_mtok") && strcmp(k,"output_per_mtok") &&
                strcmp(k,"cached_input_per_mtok")) return false;
    }
    if (!number(price,"input_per_mtok",&c.price.input_per_mtok) ||
            !number(price,"output_per_mtok",&c.price.output_per_mtok)) return false;
    c.price.cached_input_per_mtok=c.price.input_per_mtok;
    if (json_object_get(price,"cached_input_per_mtok") &&
            !number(price,"cached_input_per_mtok",&c.price.cached_input_per_mtok)) return false;
    if (!rc_price_valid(&c.price)) return false;
    c.priced=true; *out=c; return true;
}
