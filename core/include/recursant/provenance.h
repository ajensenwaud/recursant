#ifndef RECURSANT_PROVENANCE_H
#define RECURSANT_PROVENANCE_H
#include <stdbool.h>
#include <stddef.h>
#include <jansson.h>
/* Model output the router itself observed leaving a PUBLIC provider, by exact
 * value: OpenRouter reasoning_details elements (reasoning.encrypted ciphertext,
 * reasoning.summary / reasoning.text). A harness replays them so the model can
 * continue its reasoning; M2 cannot inspect ciphertext, so it may send such an
 * element back to a public destination only when it is a recorded value. That
 * value was produced by a public provider, so replaying it discloses nothing
 * new; anything else (edited, foreign, or from a private model) stays
 * uninspectable. Private-endpoint output is never recorded (caller's duty).
 *
 * Elements are compared by their compact, key-sorted serialization. Bounded
 * FIFO (oldest forgotten first): a forgotten value fails closed (private).
 * Thread-safe. */
typedef struct rc_provenance rc_provenance;
#define RC_PROVENANCE_ELEMENT_MAX_BYTES (64u * 1024u)
rc_provenance *rc_provenance_new(size_t max_entries, size_t max_bytes);
void rc_provenance_free(rc_provenance *p);
/* Records every element of an array of objects. Elements over the per-element
 * bound, non-objects and duplicates are skipped. Returns how many were added. */
size_t rc_provenance_add(rc_provenance *p, json_t *elements);
/* True iff elements is a non-empty array and every element is recorded. */
bool rc_provenance_known(rc_provenance *p, json_t *elements);
#endif
