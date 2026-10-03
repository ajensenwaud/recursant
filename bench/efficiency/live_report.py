"""Report the live check of the efficiency model (allocation E-ml-live).
usage: python3 -m bench.efficiency.live_report [OUT_DIR]"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

DIR = Path(sys.argv[1] if sys.argv[1:] else '/home/aj/projects/recursant-v4/.hermes/runtime/m3-live/final-e2')


def main():
    rows = json.load(open(DIR / 'outcomes.json'))
    # Episodes refused at the spend cap never reached a model (0 calls): not part of the comparison.
    refused = [r['episode_id'] for r in rows if not r['calls']]
    rows = [r for r in rows if r['calls']]
    if refused: print('excluded, refused at the cap before any call:', ', '.join(refused))
    arms = defaultdict(lambda: dict(n=0, passed=0, usd=0.0, calls=0, models=Counter(), actions=Counter()))
    by_key = {}
    for r in rows:
        a = arms[r['arm_label']]; a['n'] += 1; a['passed'] += bool(r['success'])
        usd = sum(float(c.get('cost_usd') or 0) for c in r['calls']); a['usd'] += usd; a['calls'] += len(r['calls'])
        for c in r['calls']: a['models'][c.get('provider_model') or c.get('requested_model')] += 1
        log = DIR / r['episode_id'] / 'router.private.log'
        if log.exists():
            for line in open(log):
                m = re.match(r'efficiency scope=\S+ p=\S+ action=(\w+)', line)
                if m: a['actions'][m.group(1)] += 1
        by_key[(r['task'], r['repeat'], r['arm_label'])] = (bool(r['success']), usd)
    print('%-11s %8s %9s %7s %8s  %s' % ('arm', 'passed', 'US$', 'calls', 'US$/job', 'model share / efficiency actions'))
    for name, a in sorted(arms.items()):
        share = ', '.join('%s %d%%' % (m.split('/')[-1], 100 * k / max(1, a['calls'])) for m, k in a['models'].most_common())
        print('%-11s %3d/%-4d %9.4f %7d %8.4f  %s | %s' % (name, a['passed'], a['n'], a['usd'], a['calls'], a['usd'] / max(1, a['n']), share, dict(a['actions'])))
    pairs = [(k[0], k[1]) for k in by_key if k[2] == 'signals' and (k[0], k[1], 'efficiency') in by_key]
    both = [p for p in pairs if by_key[p + ('signals',)][0] and by_key[p + ('efficiency',)][0]]
    s = sum(by_key[p + ('signals',)][1] for p in both); e = sum(by_key[p + ('efficiency',)][1] for p in both)
    print('matched task-repeats %d; both passed %d: signals US$%.4f, efficiency US$%.4f (%+.0f%%)' % (len(pairs), len(both), s, e, 100 * (e / s - 1) if s else 0))
    for t, r in sorted(pairs):
        (sp, su), (ep, eu) = by_key[(t, r, 'signals')], by_key[(t, r, 'efficiency')]
        print('  %-14s r%d  signals %s %.4f   efficiency %s %.4f' % (t, r, 'PASS' if sp else 'fail', su, 'PASS' if ep else 'fail', eu))


if __name__ == '__main__':
    main()
