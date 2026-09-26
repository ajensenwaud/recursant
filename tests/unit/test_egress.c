#include "recursant/egress.h"
#include <stdio.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); return 1; } } while (0)

int main(void) {
    rc_egress_input input = {
        .classification = RC_CLASS_UNKNOWN,
        .destination = RC_DEST_PUBLIC,
        .public_grant = true,
        .final_payload_scanned = true,
        .expected_policy_generation = 1,
        .current_policy_generation = 1
    };
    CHECK(rc_check_egress(&input) == RC_EGRESS_PRIVATE_REQUIRED);
    input.classification = RC_CLASS_PUBLIC;
    input.public_grant = false;
    CHECK(rc_check_egress(&input) != RC_EGRESS_ALLOW);
    input.public_grant = true;
    input.final_payload_scanned = false;
    CHECK(rc_check_egress(&input) != RC_EGRESS_ALLOW);
    input.final_payload_scanned = true;
    input.current_policy_generation = 2;
    CHECK(rc_check_egress(&input) != RC_EGRESS_ALLOW);
    input.current_policy_generation = 1;
    CHECK(rc_check_egress(NULL) != RC_EGRESS_ALLOW);
    input.classification = (rc_classification)99;
    input.destination = RC_DEST_PRIVATE;
    CHECK(rc_check_egress(&input) != RC_EGRESS_ALLOW);
    input.classification = RC_CLASS_PUBLIC;
    input.destination = (rc_destination)99;
    CHECK(rc_check_egress(&input) != RC_EGRESS_ALLOW);
    input.destination = RC_DEST_PUBLIC;
    /* Regression matrix over all defined classifications/destinations. */
    unsigned checked = 0;
    for (int classification = RC_CLASS_UNKNOWN; classification <= RC_CLASS_PRIVATE; ++classification) {
        for (int destination = RC_DEST_PRIVATE; destination <= RC_DEST_PUBLIC; ++destination) {
            for (int grant = 0; grant <= 1; ++grant) {
                for (int scanned = 0; scanned <= 1; ++scanned) {
                    input.classification = (rc_classification)classification;
                    input.destination = (rc_destination)destination;
                    input.public_grant = grant != 0;
                    input.final_payload_scanned = scanned != 0;
                    const bool allowed = scanned && (destination == RC_DEST_PRIVATE ||
                        (classification == RC_CLASS_PUBLIC && grant));
                    CHECK((rc_check_egress(&input) == RC_EGRESS_ALLOW) == allowed);
                    ++checked;
                }
            }
        }
    }
    printf("PASS egress rejection checks and %u state combinations\n", checked);
    return 0;
}
