#ifndef RECURSANT_ADMISSION_H
#define RECURSANT_ADMISSION_H

#include "recursant/auth.h"

#include <stddef.h>

typedef enum {
    RC_ADMIT_OK,
    RC_ADMIT_DENY_AUTH,       /* 401 */
    RC_ADMIT_DENY_MALFORMED,  /* 400: impossible/absent length on a body */
    RC_ADMIT_DENY_TOO_LARGE,  /* 413 */
    RC_ADMIT_DENY_OVERLOAD,   /* 503 */
    RC_ADMIT_INVALID_INPUT    /* caller bug; fail closed */
} rc_admit_result;

typedef struct {
    long max_body_bytes;
    long max_inflight;
} rc_admission_policy;

/* Pure admission decision: no I/O, no sockets. Every deny path must be
 * taken BEFORE the caller opens or writes to any upstream connection.
 * content_length is the parsed Content-Length (-1 when absent or
 * unparsable). project_out receives the authenticated project index and is
 * only meaningful on RC_ADMIT_OK. */
rc_admit_result rc_admit_request(const rc_auth_table *auth,
                                 const rc_admission_policy *policy,
                                 const char *authorization,
                                 long content_length,
                                 long current_inflight,
                                 long *project_out);

#endif
