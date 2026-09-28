#include "recursant/selector.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <float.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
static void registry_bounds(void) {
    rc_candidate c[RC_SELECTOR_MAX_CANDIDATES] = {0};
    for (size_t i=0; i<RC_SELECTOR_MAX_CANDIDATES; ++i) {
        c[i].alias_index=i; c[i].context_limit=4096;
    }
    CHECK(!rc_candidates_create(0, c, 1));
    CHECK(!rc_candidates_create(1, NULL, 1));
    CHECK(!rc_candidates_create(1, c, 0));
    CHECK(!rc_candidates_create(1, c, RC_SELECTOR_MAX_CANDIDATES+1));
    CHECK(!rc_candidates_create(1, c, SIZE_MAX));
    rc_candidate_registry *r=rc_candidates_create(1, c, RC_SELECTOR_MAX_CANDIDATES);
    CHECK(r); rc_candidates_destroy(r);
    c[1].alias_index=0;
    CHECK(!rc_candidates_create(1, c, 2));
    c[0].context_limit=0;
    CHECK(!rc_candidates_create(1, c, 1));
    rc_candidates_destroy(NULL);
}
static void conservative_baseline(void) {
    rc_candidate c[]={{.alias_index=7, .context_limit=4096},
                      {.alias_index=3, .context_limit=4096}};
    rc_candidate_registry *r=rc_candidates_create(8,c,2);
    rc_candidate_quote quotes[]={{true,10}, {true,1}};
    rc_selection_request q={.registry_version=8, .baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE, .now=10, .context_tokens=10};
    rc_selection out={0};
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK);
    CHECK(out.alias_index==7 && out.reason==RC_SELECT_BASELINE);
    c[0].alias_index=99; /* registry owns its immutable copy */
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.context_usable=true; q.context_observed_at=5; q.context_expires_at=10;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.context_expires_at=20; q.context_observed_at=11;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    quotes[0].permitted=false;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_BLOCKED);
    CHECK(out.alias_index==7); /* failures leave output untouched */
    rc_candidates_destroy(r);
}
static void qualified_ranking(void) {
    rc_candidate c[]={{7,0,4096,3}, {3,1,4096,3}, {2,2,4096,3}, {1,0,4096,3}};
    rc_candidate_quote quotes[]={{true,10},{true,2},{true,0},{true,0}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE,.context_usable=true,
        .now=10,.context_observed_at=9,.context_expires_at=11,
        .task_class=1,.context_tokens=4096,.required_capabilities=3};
    rc_selection out={0};
    rc_candidate_registry *r=rc_candidates_create(1,c,4);
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK);
    CHECK(out.alias_index==3 && out.reason==RC_SELECT_CHEAPEST);
    quotes[1].permitted=false;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    quotes[1].permitted=true;
    q.task_class=0;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.task_class=1; q.context_usable=false;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.context_usable=true; q.now=11;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.now=8;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    rc_candidates_destroy(r);
}
static void hard_requirements(void) {
    rc_candidate c[]={{7,0,4096,3}, {3,1,100,1}};
    rc_candidate_quote quotes[]={{true,10},{true,1}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE,.context_usable=true,
        .now=10,.context_expires_at=11,.task_class=1,
        .context_tokens=101,.required_capabilities=1};
    rc_selection out={0};
    rc_candidate_registry *r=rc_candidates_create(1,c,2);
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.context_tokens=100;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==3);
    q.required_capabilities=2;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.required_capabilities=4;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_BLOCKED);
    q.required_capabilities=0; q.context_tokens=4097;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_BLOCKED);
    q.context_tokens=0;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_INVALID);
    rc_candidates_destroy(r);
}
static void continuity_authority(void) {
    rc_candidate c[]={{7,0,4096,3}, {3,1,4096,3}, {9,0,4096,3}};
    rc_candidate_quote quotes[]={{true,10},{true,1},{true,20}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,.pinned_alias=9,
        .continuity=RC_CONTINUITY_PINNED,.context_usable=true,
        .now=10,.context_expires_at=11,.task_class=1,.context_tokens=1};
    rc_selection out={0};
    rc_candidate_registry *r=rc_candidates_create(1,c,3);
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK);
    CHECK(out.alias_index==9 && out.reason==RC_SELECT_PIN);
    q.context_usable=false; q.now=100; quotes[0].permitted=false;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==9);
    quotes[2].permitted=false;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_BLOCKED && out.alias_index==9);
    quotes[2].permitted=true; q.pinned_alias=99;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_BLOCKED);
    q.pinned_alias=9; q.context_tokens=4097;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_BLOCKED);
    q.context_tokens=1; q.required_capabilities=4;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_BLOCKED);
    q.required_capabilities=0; q.continuity=RC_CONTINUITY_UNKNOWN;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_BLOCKED);
    q.continuity=(rc_continuity)99;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_INVALID);
    rc_candidates_destroy(r);
}
static void invalid_inputs(void) {
    rc_candidate c[]={{7,0,4096,3},{3,1,4096,3}};
    rc_candidate_registry *r=rc_candidates_create(1,c,2);
    rc_candidate_quote quotes[]={{true,10},{true,1}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE,.context_tokens=1};
    rc_selection out={123,RC_SELECT_PIN};
    const double invalid[]={-1,NAN,INFINITY,-INFINITY};
    for (size_t i=0; i<sizeof invalid/sizeof invalid[0]; ++i) {
        quotes[1].expected_task_cost=invalid[i];
        CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_INVALID);
        CHECK(out.alias_index==123 && out.reason==RC_SELECT_PIN);
        quotes[1].permitted=false; /* invalid denied quotes also fail closed */
        CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_INVALID);
        quotes[1]=(rc_candidate_quote){true,1};
        q.minimum_saving=invalid[i];
        CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_INVALID);
        q.minimum_saving=0;
    }
    CHECK(rc_select(NULL,quotes,2,&q,&out)==RC_SELECT_INVALID);
    CHECK(rc_select(r,NULL,2,&q,&out)==RC_SELECT_INVALID);
    CHECK(rc_select(r,quotes,2,NULL,&out)==RC_SELECT_INVALID);
    CHECK(rc_select(r,quotes,2,&q,NULL)==RC_SELECT_INVALID);
    CHECK(rc_select(r,quotes,0,&q,&out)==RC_SELECT_INVALID);
    CHECK(rc_select(r,quotes,1,&q,&out)==RC_SELECT_INVALID);
    CHECK(rc_select(r,quotes,SIZE_MAX,&q,&out)==RC_SELECT_INVALID);
    q.registry_version=2;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_INVALID);
    q.registry_version=1; q.task_class=3;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_INVALID);
    q.task_class=UINT64_C(1)<<63;
    quotes[0].expected_task_cost=DBL_MAX; quotes[1].expected_task_cost=0;
    CHECK(rc_select(r,quotes,2,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    rc_candidates_destroy(r);
}
static void deterministic_hysteresis(void) {
    const rc_candidate c[]={{7,0,4096,0},{5,1,4096,0},{3,1,4096,0}};
    const unsigned permutations[][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE,.context_usable=true,
        .now=10,.context_expires_at=11,.task_class=1,.context_tokens=1};
    for (size_t p=0; p<sizeof permutations/sizeof permutations[0]; ++p) {
        rc_candidate ordered[3]; rc_candidate_quote quotes[3];
        size_t baseline=0;
        for (size_t i=0; i<3; ++i) {
            ordered[i]=c[permutations[p][i]];
            quotes[i]=(rc_candidate_quote){true,ordered[i].alias_index==7 ? 10 : 2};
            if (ordered[i].alias_index==7) baseline=i;
        }
        rc_candidate_registry *r=rc_candidates_create(1,ordered,3);
        rc_selection out={0};
        q.minimum_saving=0;
        CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==3);
        q.minimum_saving=8;
        CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
        q.minimum_saving=7;
        CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==3);
        q.minimum_saving=0; quotes[baseline].expected_task_cost=2;
        CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
        quotes[baseline].expected_task_cost=DBL_MAX; q.minimum_saving=DBL_MAX;
        CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
        rc_candidates_destroy(r);
    }
}
/* Exhaustive finite fixture matrix; independent small reference decision.
 * This extends regression coverage, not evidence of model quality or savings. */
static void safety_matrix(void) {
    size_t cases=0;
    for (unsigned permissions=0; permissions<8; ++permissions)
    for (unsigned qualification=0; qualification<4; ++qualification)
    for (unsigned requirements=0; requirements<4; ++requirements)
    for (unsigned state=0; state<3; ++state)
    for (unsigned freshness=0; freshness<4; ++freshness)
    for (unsigned cost=0; cost<3; ++cost) {
        rc_candidate c[]={{7,0,4096,3},{5,qualification&1 ? 1 : 0,100,1},
                          {3,qualification&2 ? 1 : 0,4096,3}};
        rc_candidate_quote quotes[]={{(permissions&1)!=0,2},
            {(permissions&2)!=0,cost},{(permissions&4)!=0,cost}};
        rc_selection_request q={.registry_version=1,.baseline_alias=7,.pinned_alias=5,
            .continuity=(rc_continuity)state,.context_usable=freshness!=0,
            .now=10,.context_observed_at=freshness==3 ? 11 : 9,
            .context_expires_at=freshness==2 ? 10 : 11,
            .task_class=1,.context_tokens=requirements&1 ? 101 : 100,
            .required_capabilities=requirements&2 ? 2 : 1};
        rc_candidate_registry *r=rc_candidates_create(1,c,3);
        CHECK(r);
        rc_selection out={99,RC_SELECT_PIN};
        rc_select_status expected=RC_SELECT_BLOCKED;
        size_t alias=99; rc_selection_reason reason=RC_SELECT_PIN;
        if (state==RC_CONTINUITY_PINNED && (permissions&2) && requirements==0) {
            expected=RC_SELECT_OK; alias=5;
        } else if (state==RC_CONTINUITY_REPLAYABLE && (permissions&1)) {
            expected=RC_SELECT_OK; alias=7; reason=RC_SELECT_BASELINE;
            if (freshness==1 && cost<2) {
                if ((permissions&2) && (qualification&1) && requirements==0) alias=5;
                if ((permissions&4) && (qualification&2)) alias=3;
                if (alias!=7) reason=RC_SELECT_CHEAPEST;
            }
        }
        CHECK(rc_select(r,quotes,3,&q,&out)==expected);
        CHECK(out.alias_index==alias && out.reason==reason);
        rc_candidates_destroy(r); ++cases;
    }
    printf("safety matrix: %zu cases passed\n",cases);
}
/* S4: escalation is a quality decision for the REPLAYABLE path only.
 * Escalation candidates are those qualified for the escalation class bit (8). */
static void escalation(void) {
    /* baseline 7 ($10), cheap 3 ($1, qualified bit 2), strong 5 ($30, escalation),
     * stronger 9 ($50, escalation). */
    rc_candidate c[]={{7,0,4096,3},{3,2,4096,3},{5,8,4096,3},{9,8,4096,3}};
    rc_candidate_quote quotes[]={{true,10},{true,1},{true,30},{true,50}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,.pinned_alias=9,
        .continuity=RC_CONTINUITY_REPLAYABLE,.now=10,.context_tokens=100,.escalation_class=8};
    rc_candidate_registry *r=rc_candidates_create(1,c,4);CHECK(r);
    rc_selection out={0};
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK);
    CHECK(out.alias_index==5 && out.reason==RC_SELECT_ESCALATE);
    /* Cheapest eligible escalation candidate; ties -> smaller alias index. */
    quotes[3].expected_task_cost=30;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==5);
    quotes[3].expected_task_cost=20;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==9 && out.reason==RC_SELECT_ESCALATE);
    quotes[3].expected_task_cost=50;
    /* Escalation ignores minimum_saving and a cheaper qualified signal. */
    q.minimum_saving=1000; q.signal_class=2;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==5 && out.reason==RC_SELECT_ESCALATE);
    q.minimum_saving=0; q.signal_class=0;
    /* Eligibility still applies: M2 denial, context limit, capabilities. */
    quotes[2].permitted=false;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==9);
    quotes[3].permitted=false;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7 && out.reason==RC_SELECT_BASELINE);
    quotes[2].permitted=quotes[3].permitted=true;
    c[2].context_limit=50; c[3].capabilities=1; rc_candidates_destroy(r);
    r=rc_candidates_create(1,c,4);CHECK(r);
    q.required_capabilities=2;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7 && out.reason==RC_SELECT_BASELINE);
    q.required_capabilities=0;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==9);
    c[2].context_limit=4096; c[3].capabilities=3; rc_candidates_destroy(r);
    r=rc_candidates_create(1,c,4);CHECK(r);
    /* Without an escalation request, escalation qualification never upshifts. */
    q.escalation_class=0;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7 && out.reason==RC_SELECT_BASELINE);
    /* Multi-bit escalation class is invalid. */
    q.escalation_class=12;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_INVALID);
    q.escalation_class=8;
    /* A baseline hard-eligibility failure still blocks (no invented recovery). */
    quotes[0].permitted=false; out=(rc_selection){42,RC_SELECT_PIN};
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_BLOCKED && out.alias_index==42);
    quotes[0].permitted=true;
    /* Pinned still wins over escalation. */
    q.continuity=RC_CONTINUITY_PINNED;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==9 && out.reason==RC_SELECT_PIN);
    q.pinned_alias=7;
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7 && out.reason==RC_SELECT_PIN);
    /* Unknown continuity still blocks. */
    q.continuity=RC_CONTINUITY_UNKNOWN; out=(rc_selection){42,RC_SELECT_PIN};
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_BLOCKED && out.alias_index==42);
    /* Baseline itself escalation-qualified and cheapest: stays baseline. */
    q.continuity=RC_CONTINUITY_REPLAYABLE; c[0].qualified_tasks=8; rc_candidates_destroy(r);
    r=rc_candidates_create(1,c,4);CHECK(r);
    CHECK(rc_select(r,quotes,4,&q,&out)==RC_SELECT_OK && out.alias_index==7 && out.reason==RC_SELECT_BASELINE);
    rc_candidates_destroy(r);
}
/* S4: a structured signal needs no fresh interpreter context but keeps every
 * other gate: qualification for that class, eligibility, minimum_saving. */
static void structured_signal(void) {
    rc_candidate c[]={{7,0,4096,3},{3,2,4096,3},{5,4,4096,3}};
    rc_candidate_quote quotes[]={{true,10},{true,1},{true,2}};
    rc_selection_request q={.registry_version=1,.baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE,.now=10,.context_tokens=100,.signal_class=2};
    rc_candidate_registry *r=rc_candidates_create(1,c,3);CHECK(r);
    rc_selection out={0};
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==3 && out.reason==RC_SELECT_CHEAPEST);
    q.signal_class=4;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==5 && out.reason==RC_SELECT_CHEAPEST);
    /* An unqualified class (bit 8) keeps baseline. */
    q.signal_class=8;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.signal_class=2; q.minimum_saving=9;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    q.minimum_saving=0; quotes[1].permitted=false;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    quotes[1].permitted=true;
    /* Interpreter class and signal class combine (OR): either qualifies. */
    q.context_usable=true; q.context_observed_at=9; q.context_expires_at=11; q.task_class=1;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==3);
    q.signal_class=0;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7);
    /* Pinned ignores signals. */
    q.signal_class=2; q.continuity=RC_CONTINUITY_PINNED; q.pinned_alias=7;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==7 && out.reason==RC_SELECT_PIN);
    q.continuity=RC_CONTINUITY_UNKNOWN;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_BLOCKED);
    /* Multi-bit signal class is invalid, like task_class. */
    q.continuity=RC_CONTINUITY_REPLAYABLE; q.signal_class=6;
    CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_INVALID);
    /* Same class, same costs: repeated decisions are stable (no flip-flop). */
    q.signal_class=2;
    for (int i=0; i<8; ++i)
        CHECK(rc_select(r,quotes,3,&q,&out)==RC_SELECT_OK && out.alias_index==3);
    rc_candidates_destroy(r);
}
int main(void) {
    registry_bounds();
    conservative_baseline();
    qualified_ranking();
    hard_requirements();
    continuity_authority();
    invalid_inputs();
    deterministic_hysteresis();
    safety_matrix();
    escalation();
    structured_signal();
    puts("selector tests passed");
    return 0;
}
