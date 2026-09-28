#ifndef RECURSANT_COST_H
#define RECURSANT_COST_H
#include <stdbool.h>
#include <stdint.h>
#include <jansson.h>
/* Per-turn token-and-price cost model (M3 S3). Pure, no allocation or I/O.
 *
 * Every token count here is an ESTIMATE, never an exact billing figure:
 * - prompt tokens come from the provider-reported usage of the scope's last
 *   completed turn plus ceil(appended bytes / 4), or ceil(request bytes / 4)
 *   when no usage was observed. Bytes/4 is a heuristic, not a tokenizer.
 * - output tokens are min(max_tokens, expected_output_tokens).
 * - cached input is only assumed for the scope's current owner model and only
 *   when the provider reported cached_tokens > 0 on the last turn (measured
 *   cache evidence). Any other model loses the cache (switching penalty).
 * Prices are USD per million tokens. Results are USD per turn. */
#define RC_COST_DEFAULT_OUTPUT_TOKENS 512u
#define RC_COST_MAX_OUTPUT_TOKENS 100000u
typedef struct {
    double input_per_mtok, output_per_mtok, cached_input_per_mtok;
} rc_price;
/* Finite, >= 0 and cached_input_per_mtok <= input_per_mtok. */
bool rc_price_valid(const rc_price *);
/* Provider usage of the last completed turn in one scope. */
typedef struct {
    bool known;
    uint64_t prompt_tokens, completion_tokens, cached_tokens;
} rc_usage_observation;
/* Saturating; request_bytes is used only without usage evidence. */
uint64_t rc_estimate_prompt_tokens(const rc_usage_observation *last,
    uint64_t appended_bytes, uint64_t request_bytes);
/* expected_output 0 means RC_COST_DEFAULT_OUTPUT_TOKENS. */
uint64_t rc_estimate_output_tokens(uint64_t max_tokens, uint64_t expected_output);
/* Cached input assumed for this candidate; 0 for non-owners (cache loss). */
uint64_t rc_cached_input_tokens(bool is_owner, const rc_usage_observation *last,
    uint64_t prompt_tokens);
/* uncached*input + cached*cached_input + output*output, per_mtok/1e6.
 * cached_tokens is clamped to prompt_tokens. Negative on invalid price. */
double rc_turn_cost(const rc_price *, uint64_t prompt_tokens,
    uint64_t cached_tokens, uint64_t output_tokens);
/* Candidate cost declaration from context.candidates[i]: exactly one of the
 * legacy "expected_task_cost" (finite >= 0, caller's common unit, behaviour
 * unchanged) or "price" {"input_per_mtok","output_per_mtok"[,
 * "cached_input_per_mtok"]} in USD per million tokens. Unknown price keys are
 * rejected; cached defaults to input. Other candidate keys are the caller's. */
typedef struct { bool priced; double fixed; rc_price price; } rc_candidate_cost;
bool rc_candidate_cost_parse(json_t *candidate, rc_candidate_cost *out);
#endif
