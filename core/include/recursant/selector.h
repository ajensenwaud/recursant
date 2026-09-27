#ifndef RECURSANT_SELECTOR_H
#define RECURSANT_SELECTOR_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define RC_SELECTOR_MAX_CANDIDATES 64
/* Alias indices refer to one caller-owned, immutable rc_config generation.
 * No URLs, model strings, wire schema, or quality estimates are invented here.
 * qualified_tasks is an explicit externally validated task-class bit mask;
 * zero means NOT qualified for automatic selection. */
typedef struct {
    size_t alias_index;
    uint64_t qualified_tasks, context_limit;
    uint32_t capabilities;
} rc_candidate;
typedef struct rc_candidate_registry rc_candidate_registry;
/* Copies a bounded, unique alias table; version must be nonzero. Caller binds
 * the version to config + qualification evidence and retires it atomically. */
rc_candidate_registry *rc_candidates_create(uint64_t version,
    const rc_candidate *candidates, size_t count);
void rc_candidates_destroy(rc_candidate_registry *registry);
typedef struct {
    bool permitted;
    double expected_task_cost;
} rc_candidate_quote;
typedef enum {
    RC_CONTINUITY_UNKNOWN, RC_CONTINUITY_PINNED, RC_CONTINUITY_REPLAYABLE
} rc_continuity;
typedef struct {
    uint64_t registry_version;
    size_t baseline_alias, pinned_alias;
    rc_continuity continuity;
    bool context_usable;
    uint64_t now, context_observed_at, context_expires_at;
    uint64_t task_class, context_tokens;
    uint32_t required_capabilities;
    double minimum_saving;
} rc_selection_request;
typedef enum { RC_SELECT_BASELINE, RC_SELECT_CHEAPEST, RC_SELECT_PIN } rc_selection_reason;
typedef struct { size_t alias_index; rc_selection_reason reason; } rc_selection;
typedef enum { RC_SELECT_OK, RC_SELECT_INVALID, RC_SELECT_BLOCKED } rc_select_status;
/* Pure bounded selection: no allocation, I/O, clock reads, state mutation, or
 * authentication. Safe for concurrent readers while the caller keeps registry
 * and input arrays alive and immutable. Destroy must not race any reader.
 *
 * Integration contract (NOT a wire/config schema):
 * - quotes are in registry insertion order and match registry_version. Caller
 *   supplies current concrete-destination M2 eligibility, not telemetry claims.
 * - all costs and minimum_saving must be finite, nonnegative, same-unit total
 *   expected task costs including replay, retries and interpretation overhead.
 *   Unknown costs must NOT be represented by zero. This API does not calculate
 *   costs or establish quality, prices, cache residency, or qualification.
 * - task_class is zero (unknown) or one bit in a caller-defined frozen taxonomy;
 *   capability bits and token demand come from authoritative request facts.
 *   context_tokens includes input/replay plus reserved output and must be >0.
 * - context_usable means exact-scope, revision-validated, authorized context.
 *   Times share the caller's monotonic domain; observed_at <= now < expires_at
 *   is fresh. Missing, future, expired or unknown-class context retains baseline.
 * - continuity comes ONLY from authoritative protocol state. UNKNOWN blocks;
 *   PINNED retains only the named permitted, capable pin, regardless of context,
 *   qualification or price. No optional context clears a pin.
 * - REPLAYABLE requires an explicitly validated safe boundary. The configured
 *   baseline must exist and meet hard eligibility even with fresh context; this
 *   first downshift-only slice blocks rather than inventing a recovery route.
 *   A baseline/pin need not be auto-qualified: retaining either is NOT a claim
 *   of demonstrated quality. Every alternative requires explicit qualification
 *   for this task class. No qualification is inferred from price/capabilities.
 * - Select strictly cheaper alternatives only when saving > minimum_saving.
 *   Equal cost retains baseline; alternative ties prefer smaller alias_index.
 *
 * Caller must validate alias indices against its immutable config generation,
 * then recheck current policy and continuity on the final payload/destination
 * before dispatch. Output is unchanged on INVALID/BLOCKED. No soft snapshot
 * registry fields are interpreted here; its free-form strings lack this typed
 * and authority-checked contract. No HTTP automatic route is activated.
 */
rc_select_status rc_select(const rc_candidate_registry *,
    const rc_candidate_quote *, size_t quote_count,
    const rc_selection_request *, rc_selection *out);
#endif
