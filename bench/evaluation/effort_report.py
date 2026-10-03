"""Summarise an effort_agent.py / effort_lh.py run: per arm passes, hidden tests, US$, calls,
output and reasoning tokens, cached input share and wall time, plus per-task pass table and the
cost on task-repeats every arm passed.
usage: python3 effort_report.py RUN_DIR"""
import json, sys
from collections import defaultdict
from pathlib import Path

d = Path(sys.argv[1]); rows = json.load(open(d / 'outcomes.json'))
arms = sorted({r['arm_label'] for r in rows}, key=lambda a: ['low', 'switch', 'xhigh'].index(a) if a in ('low', 'switch', 'xhigh') else 9)
by = defaultdict(dict)
for r in rows: by[(r['task'], r['repeat'])][r['arm_label']] = r
complete = {k: v for k, v in by.items() if all(a in v and v[a]['calls'] for a in arms)}
def usd(r): return sum(float(c.get('cost_usd') or 0) for c in r['calls'])
def tot(r, k): return sum(c.get(k) or 0 for c in r['calls'])
def wall(r):
    cs = [c for c in r['calls'] if c.get('started_at') and c.get('finished_at')]
    return max(c['finished_at'] for c in cs) - min(c['started_at'] for c in cs) if cs else 0
print('%d task-repeats with every arm run (of %d)' % (len(complete), len(by)))
print('%-7s %7s %9s %9s %6s %9s %9s %8s %8s' % ('arm', 'passed', 'tests', 'US$', 'calls', 'out tok', 'reason', 'cached', 'model s'))
for a in arms:
    rs = [v[a] for v in complete.values()]
    vt = [(r.get('verifier') or {}) for r in rs]
    tin = sum(tot(r, 'input_tokens') for r in rs)
    print('%-7s %3d/%-3d %4s/%-4s %9.3f %6d %9d %9d %7.0f%% %8.0f' % (
        a, sum(r['success'] for r in rs), len(rs),
        sum(v.get('passed') or 0 for v in vt) if any(vt) else '-', sum(v.get('total') or 0 for v in vt) if any(vt) else '-',
        sum(usd(r) for r in rs), sum(len(r['calls']) for r in rs), sum(tot(r, 'output_tokens') for r in rs),
        sum(tot(r, 'reasoning_tokens') for r in rs), 100 * sum(tot(r, 'cached_input_tokens') for r in rs) / max(1, tin),
        sum(sum((c['finished_at'] - c['started_at']) for c in r['calls'] if c.get('finished_at') and c.get('started_at')) for r in rs)))
both = [v for v in complete.values() if all(v[a]['success'] for a in arms)]
print('\ntask-repeats every arm passed: %d; US$ there: %s' % (len(both), ', '.join('%s %.3f' % (a, sum(usd(v[a]) for v in both)) for a in arms)))
print('\nper task (pass marks per repeat):')
for t in sorted({k[0] for k in complete}):
    print('  %-20s %s' % (t, '  '.join('%s %s' % (a, ''.join('P' if complete[k][a]['success'] else '.' for k in sorted(complete) if k[0] == t)) for a in arms)))
