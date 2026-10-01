"""Fail-closed task denominators and actual-attempt accounting, never a release certifier."""
from collections import Counter
import math
import random
from decimal import Decimal
from bench.accounting import aggregate_calls
from .live import CANONICAL_ARMS as ARMS, canonical_arm
from .pricing import call_cost, METHOD, PRICE_SOURCE, SOURCES


def paired_ci(episodes, treatment):
    """Cluster by task (not repeated episodes); missing usage => no token CI."""
    tasks=sorted({e['task_id'] for e in episodes})
    token_deltas=[]; quality_deltas=[]
    for task in tasks:
        b=[e for e in episodes if e['task_id']==task and e['arm']=='baseline-direct']
        t=[e for e in episodes if e['task_id']==task and e['arm']==treatment]
        if not b or len(b)!=len(t): return None
        quality_deltas.append(sum(e['success'] for e in t)/len(t)-sum(e['success'] for e in b)/len(b))
        if all(e['usage']['complete'] for e in b+t):
            token_deltas.append(sum(e['usage']['total_tokens'] for e in b)/len(b)-
                                sum(e['usage']['total_tokens'] for e in t)/len(t))
    def interval(values):
        if len(values)!=len(tasks) or len(values)<2: return None
        rng=random.Random(917)
        draws=sorted(sum(rng.choices(values,k=len(values)))/len(values) for _ in range(2000))
        return {'mean':sum(values)/len(values),'percentile_95':[draws[49],draws[1949]]}
    return {'independent_tasks':len(tasks),'resamples':2000,
            'baseline_minus_treatment_tokens':interval(token_deltas),
            'treatment_minus_baseline_success':interval(quality_deltas),
            'warning':'development tasks; tiny-sample bootstrap is descriptive, not acceptance proof'}


def summarize(assignments, outcomes):
    ids=[a['episode_id'] for a in assignments]
    if len(set(ids))!=len(ids): raise ValueError('duplicate assignment')
    by_id={r['episode_id']:r for r in outcomes}
    if len(by_id)!=len(outcomes) or set(by_id)-set(ids): raise ValueError('duplicate/orphan outcome')
    episodes=[]; global_ids=set(); blockers=set()
    assignments=[dict(a,arm=canonical_arm(a['arm'])) for a in assignments]
    for assignment in assignments:
        row=by_id.get(assignment['episode_id'],{})
        calls=[dict(c,arm=canonical_arm(c['arm'])) if 'arm' in c else c for c in row.get('calls',[])]
        unique={c['dispatch_id']:c for c in calls}
        usage=aggregate_calls(calls)
        if global_ids.intersection(unique): raise ValueError('cross-episode dispatch reuse')
        global_ids.update(unique)
        for call in unique.values():
            if call.get('role')=='router-private-unclassified':
                blockers.add('interpreter_role_attribution_unresolved')
            if call.get('role')=='interpreter':
                # Request-shape signature, not an authenticated discriminator.
                blockers.add('interpreter_role_by_request_signature_not_authenticated')
            if call.get('evidence_kind')!='actual': blockers.add('non_actual_evidence')
            if call['task_id']!=assignment['task_id'] or call['arm']!=assignment['arm']:
                raise ValueError('call attribution mismatch')
        inventory=row.get('collection_complete') is True and set(row.get('dispatch_ids',[]))==set(unique)
        complete=usage['complete'] and inventory
        if not complete:
            usage=dict(usage,complete=False,total_tokens=None)
            blockers.add('incomplete_usage_or_dispatch_inventory')
        success=row.get('success') is True
        episodes.append(dict(assignment,success=success,missing=not row,usage=usage,inventory_complete=inventory,
                             calls=list(unique.values()),
                             failure=row.get('failure') or (None if success else 'missing_or_failed_outcome')))
        if row.get('evidence_kind')!='actual': blockers.add('non_actual_evidence')
    arms={}
    for arm in ARMS:
        selected=[e for e in episodes if e['arm']==arm]
        calls=[c for e in selected for c in e['calls']]
        usage=aggregate_calls(calls)
        complete=bool(selected) and all(e['usage']['complete'] for e in selected)
        total=usage['total_tokens'] if complete else None
        known=usage['known_tokens']; count=len(selected); successes=sum(e['success'] for e in selected)
        # Reported dollars: one formula for every arm (pricing.call_cost), never
        # the admission liability. Unknown anywhere => arm total unknown.
        priced=[call_cost(c) for c in calls]
        sources=dict(Counter(src for _,src in priced))
        known_cost=sum(v for v,_ in priced if v is not None)
        # Dollars need a complete dispatch inventory, not private token usage.
        inventory=bool(selected) and all(e['inventory_complete'] for e in selected)
        cost=known_cost if inventory and priced and all(v is not None for v,_ in priced) else None
        if cost is None: blockers.add('unknown_provider_cost')
        if sources.get('list_price_tokens'): blockers.add('list_price_fallback_used_not_provider_billed')
        liability=sum((Decimal(str(c['liability_reserved_usd'])) for c in calls
                       if c.get('liability_reserved_usd') is not None),Decimal('0'))
        role_counts=Counter(c['role'] for c in calls)
        interpreter=[c for c in calls if c['role']=='interpreter']
        components={k:sum(c[k] for c in calls) if calls and all(c.get(k) is not None for c in calls) else None
                    for k in ('input_tokens','output_tokens','reasoning_tokens','cached_input_tokens')}
        roles={role:aggregate_calls(c for c in calls if c['role']==role)
               for role in sorted({c['role'] for c in calls})}
        arms[arm]=dict(assigned_tasks=count,successes=successes,pass_rate=successes/count if count else None,
                      total_tokens=total,known_tokens=known,complete=complete,
                      tokens_per_assigned_task=total/count if total is not None and count else None,
                      tokens_per_successful_task=total/successes if total is not None and successes else None,
                      public_cost_usd=cost,public_cost_known_usd=known_cost if priced else None,
                      cost_sources=sources,cost_usd=cost,
                      cost_per_successful_task_usd=cost/successes if cost is not None and successes else None,
                      admission_liability_usd=str(liability),
                      requests={'total':len(calls),'main':role_counts.get('main',0),
                                'interpreter':role_counts.get('interpreter',0),
                                'unclassified':len(calls)-role_counts.get('main',0)-role_counts.get('interpreter',0)},
                      interpreter={'requests':len(interpreter),'usage':aggregate_calls(interpreter) if interpreter else None,
                                   'public_cost_usd':0.0 if interpreter else None,
                                   'note':'private-trust GLM; counted in this arm total; private economics unknown'},
                      private_resource_cost_usd=None,collector_cost_usd=None,
                      components=components,by_role=roles,
                      failures=dict(Counter(e['failure'] for e in selected if not e['success'])))
    blockers.update(('independent_source_and_metrics_review_required','mechanism_and_safety_evidence_required',
                     'private_and_collector_economics_unknown','development_pack_not_sufficient_holdout'))
    return dict(assigned=len(episodes),successes=sum(e['success'] for e in episodes),
                missing_outcomes=sum(e['missing'] for e in episodes),physical_attempts=len(global_ids),
                arms=arms,episodes=[{k:v for k,v in e.items() if k not in ('calls','inventory_complete')} for e in episodes],
                paired_uncertainty={arm:paired_ci(episodes,arm) for arm in ARMS if arm!='baseline-direct'},
                cost_method=METHOD,price_source=PRICE_SOURCE,cost_source_labels=list(SOURCES),
                metric='gross provider tokens; different tokenizers are not equivalent work',
                release_gate=False,blockers=sorted(blockers))
