#ifndef RECURSANT_JUDGE_H
#define RECURSANT_JUDGE_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>
/* Synchronous per-turn judgement (e.g. TypeSafe Jev via the OpenRouter
 * Decisions API). ADVISORY ONLY: it can add a downshift class on a turn where
 * the deterministic signals gave no class; it never overrides M2, continuity,
 * pins, capability/qualification gates, recovery escalation or cost checks.
 *
 * Egress: the bounded state leaves the estate to the configured PUBLIC
 * decision provider. The caller must only ask when final M2 already permits
 * public placement of the same request. Default off (no judge section).
 *
 * Bounded: state <= RC_JUDGE_STATE_BYTES compact JSON (task text + last
 * RC_JUDGE_RECENT tool calls/results, each clipped), deadline 50..2000 ms,
 * response <= 64 KiB, strict parse. Any failure = no advice (signals only). */
#define RC_JUDGE_STATE_BYTES 12288u
#define RC_JUDGE_RECENT 6u
#define RC_JUDGE_TEXT_CLIP 600u
typedef struct {
    bool enabled;
    char url[2049], model[129];
    const char *key;          /* borrowed resolved provider key; never logged */
    unsigned timeout_ms;
    double routine_min, difficulty_max;
} rc_judge_config;
typedef struct {
    bool attempted; /* a judgeable state was built and a call started */
    bool ok;
    double routine, difficulty; /* P(routine) in [0,1]; score in [0,2] */
    unsigned latency_ms;
} rc_judge_result;
/* New compact decision request, or NULL when the body has no judgeable turn
 * (no assistant turn yet, last message not a tool result, malformed). */
char *rc_judge_request(const json_t *body, const char *model);
/* Strict Decisions API response parse; false leaves *out unchanged. */
bool rc_judge_parse(const char *text, size_t length, rc_judge_result *out);
/* Blocking call bounded by cfg->timeout_ms. Never holds caller locks. */
rc_judge_result rc_judge_ask(const rc_judge_config *cfg, const json_t *body);
/* Decision rule on a valid result. */
bool rc_judge_routine(const rc_judge_config *cfg, const rc_judge_result *r);
#endif
