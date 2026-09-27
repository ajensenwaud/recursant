#include "recursant/selector.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
struct rc_candidate_registry {
    uint64_t version;
    size_t count;
    rc_candidate candidates[RC_SELECTOR_MAX_CANDIDATES];
};
rc_candidate_registry *rc_candidates_create(uint64_t version,
        const rc_candidate *candidates, size_t count) {
    if (!version || !candidates || !count || count > RC_SELECTOR_MAX_CANDIDATES)
        return NULL;
    for (size_t i=0; i<count; ++i) {
        if (!candidates[i].context_limit) return NULL;
        for (size_t j=0; j<i; ++j)
            if (candidates[i].alias_index == candidates[j].alias_index) return NULL;
    }
    rc_candidate_registry *r=malloc(sizeof *r);
    if (!r) return NULL;
    r->version=version; r->count=count;
    memcpy(r->candidates, candidates, count*sizeof *candidates);
    return r;
}
void rc_candidates_destroy(rc_candidate_registry *r) { free(r); }
static bool eligible(const rc_candidate *c, const rc_candidate_quote *quote,
        const rc_selection_request *q) {
    return quote->permitted && c->context_limit>=q->context_tokens &&
        (c->capabilities & q->required_capabilities)==q->required_capabilities;
}
rc_select_status rc_select(const rc_candidate_registry *r,
        const rc_candidate_quote *quotes, size_t quote_count,
        const rc_selection_request *q, rc_selection *out) {
    if (!r || !quotes || !q || !out || quote_count!=r->count ||
            q->registry_version!=r->version || !q->context_tokens) return RC_SELECT_INVALID;
    if (!isfinite(q->minimum_saving) || q->minimum_saving<0 ||
            (q->task_class && (q->task_class & (q->task_class-1))))
        return RC_SELECT_INVALID;
    for (size_t i=0; i<r->count; ++i)
        if (!isfinite(quotes[i].expected_task_cost) || quotes[i].expected_task_cost<0)
            return RC_SELECT_INVALID;
    if (q->continuity!=RC_CONTINUITY_UNKNOWN && q->continuity!=RC_CONTINUITY_PINNED &&
            q->continuity!=RC_CONTINUITY_REPLAYABLE) return RC_SELECT_INVALID;
    if (q->continuity==RC_CONTINUITY_UNKNOWN) return RC_SELECT_BLOCKED;
    if (q->continuity==RC_CONTINUITY_PINNED) {
        for (size_t i=0; i<r->count; ++i) {
            if (r->candidates[i].alias_index==q->pinned_alias &&
                    eligible(&r->candidates[i], &quotes[i], q)) {
                *out=(rc_selection){q->pinned_alias,RC_SELECT_PIN};
                return RC_SELECT_OK;
            }
        }
        return RC_SELECT_BLOCKED;
    }
    size_t baseline=r->count;
    for (size_t i=0; i<r->count; ++i)
        if (r->candidates[i].alias_index==q->baseline_alias) baseline=i;
    if (baseline==r->count || !eligible(&r->candidates[baseline], &quotes[baseline], q))
        return RC_SELECT_BLOCKED;
    size_t best=baseline;
    if (q->context_usable && q->context_observed_at<=q->now &&
            q->now<q->context_expires_at && q->task_class) {
        for (size_t i=0; i<r->count; ++i)
            if (eligible(&r->candidates[i], &quotes[i], q) &&
                    (r->candidates[i].qualified_tasks & q->task_class) &&
                    (quotes[i].expected_task_cost<quotes[best].expected_task_cost ||
                     (best!=baseline && quotes[i].expected_task_cost==quotes[best].expected_task_cost &&
                      r->candidates[i].alias_index<r->candidates[best].alias_index))) best=i;
    }
    /* Subtract ordered finite nonnegative values, avoiding addition overflow. */
    if (best!=baseline && quotes[baseline].expected_task_cost-
            quotes[best].expected_task_cost<=q->minimum_saving) best=baseline;
    *out=(rc_selection){r->candidates[best].alias_index,
        best==baseline ? RC_SELECT_BASELINE : RC_SELECT_CHEAPEST};
    return RC_SELECT_OK;
}
