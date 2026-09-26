#include "recursant/egress.h"

rc_egress_result rc_check_egress(const rc_egress_input *input) {
    if (!input)
        return RC_EGRESS_INVALID_INPUT;
    if ((input->classification != RC_CLASS_UNKNOWN && input->classification != RC_CLASS_PUBLIC && input->classification != RC_CLASS_PRIVATE) ||
        (input->destination != RC_DEST_PRIVATE && input->destination != RC_DEST_PUBLIC))
        return RC_EGRESS_INVALID_INPUT;


    if (input->expected_policy_generation != input->current_policy_generation)
        return RC_EGRESS_POLICY_CHANGED;

    if (!input->final_payload_scanned)
        return RC_EGRESS_UNSCANNED;

    if (input->destination == RC_DEST_PUBLIC && !input->public_grant)
        return RC_EGRESS_PUBLIC_NOT_GRANTED;

    if (input->destination == RC_DEST_PUBLIC && input->classification != RC_CLASS_PUBLIC)
        return RC_EGRESS_PRIVATE_REQUIRED;
    return RC_EGRESS_ALLOW;
}
