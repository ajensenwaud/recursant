/* Test-only auth fixture; production authentication implementation is unchanged. */
#include "recursant/attempts.h"
rc_attempt_ledger *rc_attempt_probe_create(void) {
    static rc_project projects[]={{"synthetic-project", "NOT_READ"}};
    static rc_config config={.projects=projects, .project_count=1};
    static char *tokens[]={"synthetic-not-a-secret"};
    static rc_auth_table auth={.cfg=&config, .tokens=tokens};
    return rc_attempt_create(&auth,16,60000000000ULL);
}
