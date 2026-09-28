#include "recursant/cost.h"
/* RED stub: behaviour intentionally absent until the tests fail. */
bool rc_price_valid(const rc_price *p) { (void)p; return false; }
uint64_t rc_estimate_prompt_tokens(const rc_usage_observation *last,
        uint64_t appended_bytes, uint64_t request_bytes) {
    (void)last; (void)appended_bytes; return request_bytes;
}
uint64_t rc_estimate_output_tokens(uint64_t max_tokens, uint64_t expected_output) {
    (void)expected_output; return max_tokens;
}
uint64_t rc_cached_input_tokens(bool is_owner, const rc_usage_observation *last,
        uint64_t prompt_tokens) {
    (void)is_owner; (void)last; (void)prompt_tokens; return 0;
}
double rc_turn_cost(const rc_price *p, uint64_t prompt_tokens,
        uint64_t cached_tokens, uint64_t output_tokens) {
    (void)p; (void)prompt_tokens; (void)cached_tokens; (void)output_tokens; return 0;
}
bool rc_candidate_cost_parse(json_t *candidate, rc_candidate_cost *out) {
    (void)candidate; (void)out; return false;
}
