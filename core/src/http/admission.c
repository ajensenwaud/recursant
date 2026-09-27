#include "recursant/admission.h"

#include <string.h>

rc_admit_result rc_admit_request(const rc_auth_table *auth,
                                 const rc_admission_policy *policy,
                                 const char *authorization,
                                 long content_length,
                                 long current_inflight,
                                 long *project_out) {
    /* Order is deliberate: identity first, then body sanity, then size,
     * then capacity. An unauthenticated caller never learns quota or size
     * state. */
    if (!project_out)
        return RC_ADMIT_INVALID_INPUT;
    if (!auth)
        return RC_ADMIT_DENY_AUTH; /* no table = nobody can authenticate */
    if (!policy)
        return RC_ADMIT_INVALID_INPUT;
    if (policy->max_body_bytes <= 0 || policy->max_inflight < 0 ||
        current_inflight < 0 || current_inflight > policy->max_inflight)
        return RC_ADMIT_INVALID_INPUT;

    const long project = rc_auth_bearer(auth, authorization);
    if (project < 0)
        return RC_ADMIT_DENY_AUTH;

    if (content_length < 0)
        return RC_ADMIT_DENY_MALFORMED;
    if (content_length > policy->max_body_bytes)
        return RC_ADMIT_DENY_TOO_LARGE;
    if (current_inflight >= policy->max_inflight)
        return RC_ADMIT_DENY_OVERLOAD;

    *project_out = project;
    return RC_ADMIT_OK;
}
