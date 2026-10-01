"""Descriptive analysis of a multi-agent run directory (outcomes.json). No inference.

  python3 -m bench.multiagent.analyse RUN_DIR [RUN_DIR ...]

Dollars are provider-billed public cost. Private (local) calls have no public charge;
their resource cost is not estimated here. Paired statistics match episodes of the same
task and repeat; the bootstrap is descriptive, not an acceptance test."""
import json
import random
import sys
from pathlib import Path

BASE = 'baseline-direct'


def load(dirs):
    rows = []
    for d in dirs:
        for r in json.loads((Path(d) / 'outcomes.json').read_text()):
            r['run'] = Path(d).name; rows.append(r)
    return rows


def usd(r):
    return r['facts']['public_usd']


def wall(r):
    return r.get('elapsed_seconds') or 0.0


def table(rows):
    arms = [a for a in (BASE, 'routed-request', 'routed-telemetry') if any(r['arm'] == a for r in rows)]
    out = {}
    for label, keep in (('all', lambda r: True), ('plain', lambda r: not r['task_id'].endswith('-pii-delegate')),
                        ('pii', lambda r: r['task_id'].endswith('-pii-delegate'))):
        block = {}
        for arm in arms:
            mine = [r for r in rows if r['arm'] == arm and keep(r)]
            if not mine: continue
            cost = [usd(r) for r in mine]
            models = {}
            for r in mine:
                for m, n in r['facts']['models'].items(): models[m] = models.get(m, 0) + n
            total = sum(models.values()) or 1
            block[arm] = dict(
                episodes=len(mine), passed=sum(bool(r['success']) for r in mine),
                public_usd=None if any(c is None for c in cost) else round(sum(cost), 4),
                requests=sum(models.values()), share={m: round(n / total, 3) for m, n in sorted(models.items())},
                pii_requests_public=sum(r['facts']['pii_requests_public'] for r in mine),
                pii_requests_private=sum(r['facts']['pii_requests_private'] for r in mine),
                subagents=sum(r['facts']['subagents_started'] for r in mine),
                recognised=sum(r['facts']['delegated_by_request'] + r['facts']['delegated_by_hint'] for r in mine),
                rejected=sum(r['facts']['rejected'] for r in mine),
                wall_minutes=round(sum(wall(r) for r in mine) / 60, 1))
        out[label] = block
    return out


def paired(rows, arm, keep=lambda r: True, resamples=4000, seed=917):
    base = {(r['run'], r['pair_id']): r for r in rows if r['arm'] == BASE and keep(r)}
    pairs = [(base[(r['run'], r['pair_id'])], r) for r in rows
             if r['arm'] == arm and keep(r) and (r['run'], r['pair_id']) in base]
    pairs = [(b, t) for b, t in pairs if usd(b) is not None and usd(t) is not None]
    if not pairs: return None
    rng = random.Random(seed)
    def ratio(sample):
        b = sum(usd(x) for x, _ in sample)
        return sum(usd(y) for _, y in sample) / b if b else float('nan')
    def diff(sample):
        return sum(bool(y['success']) - bool(x['success']) for x, y in sample)
    draws = [[rng.choice(pairs) for _ in pairs] for _ in range(resamples)]
    ratios = sorted(ratio(d) for d in draws); diffs = sorted(diff(d) for d in draws)
    lo, hi = int(0.025 * resamples), int(0.975 * resamples) - 1
    both = [(b, t) for b, t in pairs if b['success'] and t['success']]
    return dict(pairs=len(pairs), cost_ratio=round(ratio(pairs), 3), cost_ratio_95=[round(ratios[lo], 3), round(ratios[hi], 3)],
                pass_difference=diff(pairs), pass_difference_95=[diffs[lo], diffs[hi]],
                both_pass_pairs=len(both), both_pass_cost_ratio=round(ratio(both), 3) if both else None)


def per_task(rows):
    out = {}
    for r in rows:
        t = out.setdefault(r['task_id'], {}).setdefault(r['arm'], dict(passed=0, n=0, usd=0.0, private=0))
        t['n'] += 1; t['passed'] += bool(r['success']); t['usd'] = round(t['usd'] + (usd(r) or 0), 4)
        t['private'] += r['facts']['private_requests']
    return out


def main(argv=None):
    rows = load((argv or sys.argv)[1:])
    plain = lambda r: not r['task_id'].endswith('-pii-delegate')
    report = dict(arms=table(rows), per_task=per_task(rows),
                  paired_all={a: paired(rows, a) for a in ('routed-request', 'routed-telemetry')},
                  paired_plain={a: paired(rows, a, plain) for a in ('routed-request', 'routed-telemetry')})
    print(json.dumps(report, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
