#ifndef RECURSANT_EFFICIENCY_H
#define RECURSANT_EFFICIENCY_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>
/* Efficiency model (context.efficiency): a logistic regression over facts the
 * request already carries, predicting the chance that the economy model makes
 * the same next move as the baseline (bench/efficiency/train.py). ADVISORY ONLY,
 * in the judge's slot: it may add a downshift class on an unclassified turn
 * (p >= downshift_min) or remove one the signals gave (p < veto_below). It never
 * touches recovery escalation, pins, private-only sessions, final M2,
 * capability/qualification gates or the cost check. Local arithmetic: no
 * egress, no allocation beyond jansson reads, microseconds per request.
 *
 * Features mirror bench/efficiency/features.py exactly (checked offline by
 * bench/efficiency/parity.py over every recorded request). Lengths are counted
 * in Unicode code points, as Python does. */
enum {
    RC_EFF_BIAS, RC_EFF_LAST_FAILED, RC_EFF_FAILS_IN_LAST3, RC_EFF_FAILURE_RUN,
    RC_EFF_LOG_MESSAGES, RC_EFF_LOG_TOOL_RESULTS, RC_EFF_LOG_LAST_LEN, RC_EFF_SUBAGENT,
    RC_EFF_REPEAT_LAST_CALL, RC_EFF_NO_TOOLS_OFFERED,
    RC_EFF_LAST_TERMINAL, RC_EFF_LAST_READ_FILE, RC_EFF_LAST_WRITE_FILE, RC_EFF_LAST_PATCH,
    RC_EFF_LAST_SEARCH_FILES, RC_EFF_LAST_EXECUTE_CODE, RC_EFF_LAST_DELEGATE_TASK,
    RC_EFF_FEATURES
};
/* Config/feature names, in enum order (bias, last_failed, ..., last_call_delegate_task). */
extern const char *const rc_efficiency_names[RC_EFF_FEATURES];
/* Failure markers are searched in the first RC_EFF_SCAN_BYTES code points of
 * each result (Python's x[:8000]). */
#define RC_EFF_SCAN_BYTES 8000u
typedef struct {
    bool enabled;
    double weights[RC_EFF_FEATURES];
    double downshift_min; /* add a downshift class at p >= this (0.5..1) */
    double veto_below;    /* remove a signals downshift at p < this (0..downshift_min; 0 = never) */
} rc_efficiency_config;
/* Strict parse of {"weights": {name: number, ...}, "downshift_min": x,
 * "veto_below": y}. weights must name "bias"; unknown names, non-finite or
 * |w| > 100 fail. veto_below is optional (default 0). */
bool rc_efficiency_configure(json_t *section, rc_efficiency_config *out);
/* Feature vector of a chat request body; false when it has no messages array. */
bool rc_efficiency_features(const json_t *body, double out[RC_EFF_FEATURES]);
/* P(economy agrees) in (0,1), or -1 when the body has no features. */
double rc_efficiency_score(const rc_efficiency_config *cfg, const json_t *body);
#endif
