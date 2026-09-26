#ifndef RECURSANT_EGRESS_H
#define RECURSANT_EGRESS_H
#include <stdbool.h>
#include <stdint.h>

typedef enum { RC_CLASS_UNKNOWN, RC_CLASS_PUBLIC, RC_CLASS_PRIVATE } rc_classification;
typedef enum { RC_DEST_PRIVATE, RC_DEST_PUBLIC } rc_destination;
typedef enum {
    RC_EGRESS_ALLOW,
    RC_EGRESS_INVALID_INPUT,
    RC_EGRESS_POLICY_CHANGED,
    RC_EGRESS_UNSCANNED,
    RC_EGRESS_PUBLIC_NOT_GRANTED,
    RC_EGRESS_PRIVATE_REQUIRED
} rc_egress_result;

typedef struct {
    rc_classification classification;
    rc_destination destination;
    bool public_grant;
    bool final_payload_scanned;
    uint64_t expected_policy_generation;
    uint64_t current_policy_generation;
} rc_egress_input;

/* Evaluates an already classified, final provider-bound request. No I/O. */
rc_egress_result rc_check_egress(const rc_egress_input *input);
#endif
