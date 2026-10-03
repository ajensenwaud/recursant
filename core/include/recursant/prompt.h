#ifndef RECURSANT_PROMPT_H
#define RECURSANT_PROMPT_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>
/* Prompt classifier (context.prompt): for single-query and chat traffic, and
 * optionally an agent task's opening instruction. Reads ONLY the newest message
 * when it is a user message (a fresh human question) and predicts the chance
 * that the economy tier answers it correctly (bench/prompt/train.py). At
 * p >= simple_min the turn gets the "simple_prompt" class, which only
 * candidates qualified for it can serve. Tool results are never read here:
 * inside an agent loop the signals decide. Advisory, below compliance and
 * continuity; local arithmetic, no egress.
 *
 * Features (mirrored exactly by bench/prompt/features.py, checked by
 * bench/prompt/parity.py): the first RC_PROMPT_TEXT_MAX bytes of the message
 * (text parts joined by '\n'); ASCII lower-cased; tokens are maximal runs of
 * [a-z0-9]; each distinct token of at most RC_PROMPT_TOKEN_MAX bytes adds its
 * vocabulary weight once; plus the dense features below. */
enum {
    RC_PROMPT_BIAS, RC_PROMPT_LOG_CHARS, RC_PROMPT_LOG_LINES, RC_PROMPT_LOG_TOKENS,
    RC_PROMPT_CODE_FRAC, RC_PROMPT_DIGIT_FRAC, RC_PROMPT_OPS_FRAC, RC_PROMPT_QUESTION,
    RC_PROMPT_DENSE
};
extern const char *const rc_prompt_names[RC_PROMPT_DENSE];
#define RC_PROMPT_TEXT_MAX 65536u
#define RC_PROMPT_TOKEN_MAX 32u
#define RC_PROMPT_VOCAB_MAX 20000u
typedef struct rc_prompt_vocab rc_prompt_vocab;
typedef struct {
    bool enabled;
    bool agent_turns;      /* also classify a user message in a request that offers tools */
    double simple_min;     /* 0.5..1 */
    double weights[RC_PROMPT_DENSE];
    rc_prompt_vocab *vocab;
} rc_prompt_config;
/* Strict parse of {"weights": {dense name: number}, "vocab": {token: number},
 * "simple_min": x, "agent_turns": bool}. "bias" required; vocabulary keys
 * [a-z0-9]{1,32}, at most RC_PROMPT_VOCAB_MAX; every weight finite, |w| <= 100.
 * On success allocates the vocabulary (rc_prompt_destroy frees it). */
bool rc_prompt_configure(json_t *section, rc_prompt_config *out);
void rc_prompt_destroy(rc_prompt_config *cfg);
/* Dense features of a text (bytes). Returns the number of tokens. */
size_t rc_prompt_dense(const char *text, size_t length, double out[RC_PROMPT_DENSE]);
/* Score of a text, or of a request body's newest message (-1 when the newest
 * message is not a user message with text). */
double rc_prompt_score_text(const rc_prompt_config *cfg, const char *text, size_t length);
double rc_prompt_score(const rc_prompt_config *cfg, const json_t *body);
#endif
