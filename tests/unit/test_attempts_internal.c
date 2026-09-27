/* White-box arithmetic boundary: no public test hook or production ABI change. */
#include "../../core/src/context/attempts.c"
#include <assert.h>
int main(void) {
    rc_project project={"fixture","UNUSED"};
    rc_config cfg={.projects=&project,.project_count=1};
    char *token="synthetic";
    rc_auth_table auth={.cfg=&cfg,.tokens=&token};
    rc_attempt_ledger *l=rc_attempt_create(&auth,1,10);
    assert(l);
    l->serial=UINT64_MAX;
    rc_attempt_id id={{0},0};
    assert(rc_attempt_begin(l,"Bearer synthetic",NULL,1,&id)==RC_ATTEMPT_UNTRACKED);
    assert(id.serial==0 && l->lost && l->serial==UINT64_MAX);
    rc_attempt_destroy(l);
    return 0;
}
