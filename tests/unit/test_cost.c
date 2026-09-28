/* S3 cost model: pure unit tests (no network, no inference). */
#include "recursant/cost.h"
#include "recursant/selector.h"
#include <jansson.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
#define NEAR(a,b) (fabs((a)-(b)) < 1e-12)

static void prices(void) {
    rc_price ok={3,15,0.3};
    CHECK(rc_price_valid(&ok));
    rc_price same={1,2,1}; CHECK(rc_price_valid(&same));
    rc_price zero={0,0,0}; CHECK(rc_price_valid(&zero));
    rc_price bad[]={{-1,1,0},{1,-1,0},{1,1,-0.1},{1,1,2},{NAN,1,0},{1,INFINITY,0},{1,1,NAN}};
    for (size_t i=0;i<sizeof bad/sizeof *bad;i++) CHECK(!rc_price_valid(&bad[i]));
    CHECK(!rc_price_valid(NULL));
    /* 1M uncached input at $3 + 1M output at $15 = $18. */
    CHECK(NEAR(rc_turn_cost(&ok,1000000,0,1000000),18.0));
    /* 1000 prompt of which 800 cached: 200*3e-6 + 800*0.3e-6 + 100*15e-6. */
    CHECK(NEAR(rc_turn_cost(&ok,1000,800,100),200*3e-6+800*0.3e-6+100*15e-6));
    /* cached tokens clamp to prompt tokens. */
    CHECK(NEAR(rc_turn_cost(&ok,100,500,0),100*0.3e-6));
    CHECK(rc_turn_cost(&bad[0],1,0,1)<0);
    CHECK(rc_turn_cost(NULL,1,0,1)<0);
    CHECK(NEAR(rc_turn_cost(&zero,1000,0,1000),0));
}

static void estimates(void) {
    rc_usage_observation none={0};
    /* No usage evidence: ceil(bytes/4). */
    CHECK(rc_estimate_prompt_tokens(&none,999,4000)==1000);
    CHECK(rc_estimate_prompt_tokens(&none,0,4001)==1001);
    CHECK(rc_estimate_prompt_tokens(NULL,0,1)==1);
    CHECK(rc_estimate_prompt_tokens(&none,0,0)==0);
    /* Usage evidence: last prompt + last completion + ceil(appended/4),
     * independent of total request bytes. */
    rc_usage_observation last={true,5000,300,4096};
    CHECK(rc_estimate_prompt_tokens(&last,10,999999)==5000+300+3);
    CHECK(rc_estimate_prompt_tokens(&last,0,999999)==5300);
    rc_usage_observation huge={true,UINT64_MAX,5,0};
    CHECK(rc_estimate_prompt_tokens(&huge,100,1)==UINT64_MAX);
    /* Output estimate. */
    CHECK(rc_estimate_output_tokens(128,0)==128);
    CHECK(rc_estimate_output_tokens(4096,0)==RC_COST_DEFAULT_OUTPUT_TOKENS);
    CHECK(rc_estimate_output_tokens(4096,1000)==1000);
    CHECK(rc_estimate_output_tokens(10,1000)==10);
    /* Cache assumption: owner with evidence only. */
    CHECK(rc_cached_input_tokens(true,&last,6000)==5000);
    CHECK(rc_cached_input_tokens(true,&last,4000)==4000);
    CHECK(rc_cached_input_tokens(false,&last,6000)==0);
    rc_usage_observation cold={true,5000,300,0};
    CHECK(rc_cached_input_tokens(true,&cold,6000)==0);
    CHECK(rc_cached_input_tokens(true,&none,6000)==0);
    CHECK(rc_cached_input_tokens(true,NULL,6000)==0);
}

/* Owner "frontier" has a warm cache; "cheap" is nominally cheaper per token. */
static size_t choose(const rc_price *owner, const rc_price *cheap,
        const rc_usage_observation *last, uint64_t appended, double minimum_saving,
        double *owner_cost, double *cheap_cost) {
    uint64_t prompt=rc_estimate_prompt_tokens(last,appended,0);
    uint64_t out=rc_estimate_output_tokens(4096,0);
    *owner_cost=rc_turn_cost(owner,prompt,rc_cached_input_tokens(true,last,prompt),out);
    *cheap_cost=rc_turn_cost(cheap,prompt,rc_cached_input_tokens(false,last,prompt),out);
    rc_candidate c[]={{7,0,1000000,0},{3,1,1000000,0}};
    rc_candidate_quote q[]={{true,*owner_cost},{true,*cheap_cost}};
    rc_selection_request req={.registry_version=1,.baseline_alias=7,
        .continuity=RC_CONTINUITY_REPLAYABLE,.context_usable=true,.now=10,
        .context_observed_at=9,.context_expires_at=11,.task_class=1,
        .context_tokens=prompt+4096,.minimum_saving=minimum_saving};
    rc_candidate_registry *r=rc_candidates_create(1,c,2);CHECK(r);
    rc_selection sel={0};
    CHECK(rc_select(r,q,2,&req,&sel)==RC_SELECT_OK);
    rc_candidates_destroy(r);
    return sel.alias_index;
}

static void switching_penalty(void) {
    /* Owner $3 in / $0.30 cached / $15 out; cheap $2 in / $2 cached / $10 out.
     * Warm 100k-token cache: owner input is mostly at $0.30, cheap pays $2 on
     * every token, so the cheaper list price LOSES. */
    rc_price owner={3,15,0.3}, cheap={2,10,2};
    rc_usage_observation warm={true,100000,200,100000};
    double oc,cc;
    CHECK(choose(&owner,&cheap,&warm,400,0,&oc,&cc)==7);
    CHECK(oc<cc);
    /* Same prices without cache evidence: the saving survives and cheap wins. */
    rc_usage_observation cold={true,100000,200,0};
    CHECK(choose(&owner,&cheap,&cold,400,0,&oc,&cc)==3);
    CHECK(cc<oc);
    /* A much cheaper model still wins despite losing the warm cache. */
    rc_price tiny={0.05,0.2,0.05};
    CHECK(choose(&owner,&tiny,&warm,400,0,&oc,&cc)==3);
    /* ...unless minimum_saving exceeds the surviving saving. */
    CHECK(choose(&owner,&tiny,&warm,400,1.0,&oc,&cc)==7);
}

static json_t *candidate(const char *extra) {
    char buf[512];
    snprintf(buf,sizeof buf,"{\"alias\":\"a\"%s%s}",*extra?",":"",extra);
    json_error_t e; json_t *v=json_loads(buf,0,&e); CHECK(v); return v;
}
static bool parse(const char *extra, rc_candidate_cost *out) {
    json_t *v=candidate(extra); bool ok=rc_candidate_cost_parse(v,out); json_decref(v); return ok;
}

static void config_validation(void) {
    rc_candidate_cost c;
    CHECK(parse("\"expected_task_cost\":2.5",&c) && !c.priced && c.fixed==2.5);
    CHECK(parse("\"expected_task_cost\":0",&c) && !c.priced && c.fixed==0);
    CHECK(parse("\"price\":{\"input_per_mtok\":3,\"output_per_mtok\":15}",&c) &&
          c.priced && c.price.input_per_mtok==3 && c.price.output_per_mtok==15 &&
          c.price.cached_input_per_mtok==3);
    CHECK(parse("\"price\":{\"input_per_mtok\":3,\"output_per_mtok\":15,\"cached_input_per_mtok\":0.3}",&c) &&
          c.priced && c.price.cached_input_per_mtok==0.3);
    CHECK(parse("\"price\":{\"input_per_mtok\":0,\"output_per_mtok\":0,\"cached_input_per_mtok\":0}",&c) && c.priced);
    const char *bad[]={
        "",                                                     /* neither */
        "\"expected_task_cost\":1,\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":1}", /* both */
        "\"expected_task_cost\":-1",
        "\"expected_task_cost\":true",
        "\"expected_task_cost\":\"1\"",
        "\"expected_task_cost\":null",
        "\"price\":null",
        "\"price\":[]",
        "\"price\":{}",
        "\"price\":{\"input_per_mtok\":1}",
        "\"price\":{\"output_per_mtok\":1}",
        "\"price\":{\"input_per_mtok\":-1,\"output_per_mtok\":1}",
        "\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":-0.5}",
        "\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":1,\"cached_input_per_mtok\":2}",
        "\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":1,\"cached_input_per_mtok\":-1}",
        "\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":1,\"cached_input_per_mtok\":null}",
        "\"price\":{\"input_per_mtok\":true,\"output_per_mtok\":1}",
        "\"price\":{\"input_per_mtok\":\"1\",\"output_per_mtok\":1}",
        "\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":1,\"currency\":\"USD\"}",
        "\"price\":{\"input_per_mtok\":1,\"output_per_mtok\":1e400}",
    };
    for (size_t i=0;i<sizeof bad/sizeof *bad;i++) {
        json_error_t e; char buf[512];
        snprintf(buf,sizeof buf,"{\"alias\":\"a\"%s%s}",*bad[i]?",":"",bad[i]);
        json_t *v=json_loads(buf,0,&e);
        if (!v) continue; /* e.g. 1e400 rejected by the JSON parser itself */
        bool ok=rc_candidate_cost_parse(v,&c); json_decref(v);
        if (ok) { fprintf(stderr,"accepted bad case %zu: %s\n",i,bad[i]); exit(1); }
    }
    CHECK(!rc_candidate_cost_parse(NULL,&c));
}

int main(void) {
    prices();
    estimates();
    switching_penalty();
    config_validation();
    puts("cost tests passed");
    return 0;
}
