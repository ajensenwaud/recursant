"""Gross provider token accounting, not equivalent work across tokenizers."""

import hashlib
import json


def aggregate_calls(calls):
    known = 0
    calls = list(calls)
    complete = bool(calls)
    seen = {}
    for c in calls:
        for field in ('dispatch_id', 'task_id', 'arm', 'role'):
            if not isinstance(c.get(field), str) or not c[field]:
                raise ValueError('missing identity: ' + field)
        if type(c.get('attempt')) is not int or c['attempt'] < 1:
            raise ValueError('attempt must be a positive integer')
        for field in ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_input_tokens'):
            value = c.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('invalid token count: ' + field)
        if c.get('reasoning_semantics', 'unknown') not in ('inclusive', 'additive', 'unknown'):
            raise ValueError('invalid reasoning semantics')
        if (c.get('input_tokens') is not None and c.get('cached_input_tokens') is not None
                and c['cached_input_tokens'] > c['input_tokens']):
            raise ValueError('cached input must be a subset')
        if (c.get('reasoning_semantics') == 'inclusive' and c.get('reasoning_tokens') is not None
                and c.get('output_tokens') is not None and c['reasoning_tokens'] > c['output_tokens']):
            raise ValueError('inclusive reasoning must be a subset')
        key = c['dispatch_id']
        if key in seen:
            if seen[key] != c:
                raise ValueError('conflicting dispatch_id: ' + key)
            continue
        seen[key] = c
        semantics = c.get('reasoning_semantics', 'unknown')
        required = ['input_tokens', 'output_tokens']
        if semantics == 'additive':
            required.append('reasoning_tokens')
        if semantics == 'unknown' or any(c.get(k) is None for k in required):
            complete = False
        # Lower bound from reported components, even when full usage is unknown.
        # Unknown overlap: max(output, reasoning), not their potentially doubled sum.
        known += c.get('input_tokens') or 0
        output = c.get('output_tokens') or 0
        reasoning = c.get('reasoning_tokens') or 0
        known += output + reasoning if semantics == 'additive' else max(output, reasoning)
    return {'total_tokens': known if complete else None, 'complete': complete,
            'known_tokens': known}


def evaluate(data):
    """Evaluate declared records; evidence references are not authenticated here."""
    episodes, calls = data['episodes'], data['calls']
    aggregate_calls(calls)  # Global dispatch conflicts must never hide across arms.
    blockers = set()
    reports = []
    identities = set()
    for e in episodes:
        identity = (e['pair_id'], e['arm'])
        if identity in identities:
            raise ValueError('duplicate episode identity')
        identities.add(identity)
        selected = [c for c in calls if (c.get('pair_id'), c['task_id'], c['arm']) ==
                    (e.get('pair_id'), e.get('task_id'), e.get('arm'))]
        usage = aggregate_calls(selected)
        observed = {c['dispatch_id'] for c in selected}
        expected = e.get('dispatch_ids')
        if (not isinstance(expected, list) or not expected or set(expected) != observed
                or e.get('collection_complete') is not True):
            usage['complete'] = False
        if not usage['complete']:
            usage['total_tokens'] = None
            blockers.add('incomplete_usage_or_dispatch_inventory')
        if type(e.get('success')) is not bool:
            blockers.add('missing_success_verdict')
        if e['arm'] not in ('baseline', 'routed'):
            blockers.add('unknown_arm')
        manifest = e.get('manifest')
        common = manifest.get('common') if isinstance(manifest, dict) else None
        valid_manifest = (isinstance(common, dict) and common.get('task_set')
                          and common.get('harness')
                          and all(isinstance(common.get(k), str) and common[k] for k in
                                  ('prompt_fingerprint', 'toolset_fingerprint',
                                   'workspace_fingerprint', 'telemetry_fingerprint'))
                          and all(isinstance(common.get(k), dict) and common[k] for k in
                                  ('reasoning', 'sampling'))
                          and isinstance(common.get('budgets'), dict)
                          and all(k in common['budgets'] for k in
                                  ('context', 'output', 'turns', 'deadline_s'))
                          and all(v is None or (type(v) in (int, float) and v > 0)
                                  for v in common['budgets'].values()))
        fingerprint = None
        if valid_manifest:
            fingerprint = hashlib.sha256(json.dumps(common, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        else:
            blockers.add('missing_manifest_or_budget')
        reports.append(dict(usage, arm=e['arm'], task_id=e['task_id'], pair_id=e['pair_id'],
                            success=e.get('success'), manifest_fingerprint=fingerprint))
    covered = {(e['pair_id'], e['task_id'], e['arm']) for e in episodes}
    if any((c.get('pair_id'), c['task_id'], c['arm']) not in covered for c in calls):
        blockers.add('orphan_calls')
    if any(not c.get('tokenizer') for c in calls):
        blockers.add('missing_tokenizer')
    if any(x.get('evidence_kind') != 'actual' or not x.get('evidence_ref')
           for x in episodes + calls):
        blockers.add('non_actual_or_missing_evidence')
    arms = {}
    for arm in ('baseline', 'routed'):
        rows = [e for e in reports if e['arm'] == arm]
        usage = aggregate_calls(c for c in calls if c['arm'] == arm)
        complete = usage['complete'] and bool(rows) and all(e['complete'] for e in rows)
        total = usage['total_tokens'] if complete else None
        count, successes = len(rows), sum(e['success'] is True for e in rows)
        arms[arm] = dict(complete=complete, total_tokens=total, known_tokens=usage['known_tokens'],
            assigned_tasks=count, successes=successes,
            tokens_per_assigned_task=total / count if total is not None and count else None,
            tokens_per_successful_task=total / successes if total is not None and successes else None)
    pairs = [{e['pair_id'] for e in reports if e['arm'] == arm}
             for arm in ('baseline', 'routed')]
    if pairs[0] != pairs[1]:
        blockers.add('unmatched_assignments')
    matched = []
    for pair_id in sorted(pairs[0] & pairs[1]):
        b = next(e for e in reports if e['arm'] == 'baseline' and e['pair_id'] == pair_id)
        r = next(e for e in reports if e['arm'] == 'routed' and e['pair_id'] == pair_id)
        same = (b['manifest_fingerprint'] is not None and
                b['manifest_fingerprint'] == r['manifest_fingerprint'] and b['task_id'] == r['task_id'])
        if not same:
            blockers.add('unequal_manifests_or_tasks')
        if same and b['complete'] and r['complete']:
            matched.append(dict(pair_id=pair_id, baseline_fingerprint=b['manifest_fingerprint'],
                                routed_fingerprint=r['manifest_fingerprint']))
    if not matched:
        blockers.add('no_complete_matched_pairs')
    if any(a['successes'] == 0 for a in arms.values()):
        blockers.add('no_successful_tasks')
    if arms['routed']['successes'] < arms['baseline']['successes']:
        blockers.add('fewer_successful_tasks')
    baseline = arms['baseline']['total_tokens']
    routed = arms['routed']['total_tokens']
    savings = (baseline - routed) / baseline if baseline and routed is not None else None
    return dict(arms=arms, episodes=reports, matched_pairs=len(matched), pairs=matched,
                usage_records=list({c['dispatch_id']: {k: v for k, v in c.items() if k in {
                    'dispatch_id', 'task_id', 'pair_id', 'arm', 'attempt', 'role',
                    'input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_input_tokens',
                    'reasoning_semantics', 'tokenizer', 'evidence_kind', 'evidence_ref'
                }} for c in calls}.values()),
                metric='gross provider tokens; not equivalent work across tokenizers',
                savings_fraction=savings, blockers=sorted(blockers),
                comparison_eligible=not blockers,
                observed_token_reduction=savings is not None and savings > 0,
                savings_passed=False, release_gate='not_evaluated',
                evidence_status='caller_declared_not_independently_verified')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json_file')
    args = parser.parse_args(argv)
    with open(args.json_file, encoding='utf-8') as stream:
        result = evaluate(json.load(stream))
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
