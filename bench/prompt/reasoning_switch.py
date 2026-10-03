"""Reasoning switch evaluation (Phase 2): GLM with thinking off vs on, per question.

Reads graded answers for both arms (errors and timeouts count as wrong: the user got no
answer). Reports the paired disagreement table, accuracy/tokens/latency of always-off,
always-on, the perfect-hindsight oracle and the trained switch (context.prompt features,
label = thinking needed: on right and off wrong), evaluated 5-fold and leave-one-subject-out.
usage: RC_PROMPT_ITEMS=.hermes/runtime/prompt/mmlupro.jsonl python3 -m bench.prompt.reasoning_switch OFF.jsonl ON.jsonl [--out weights.json]"""
import argparse, json, math, random
from collections import defaultdict
from bench.prompt.features import features, score
from bench.prompt.train import ITEMS, auc, fit


def load(path):
    raw = {json.loads(l)['id']: json.loads(l) for l in open(path)}
    graded = {json.loads(l)['id']: json.loads(l) for l in open(path.replace('.jsonl', '.graded.jsonl'))}
    out = {}
    for i, r in raw.items():
        out[i] = dict(ok=bool(graded.get(i, {}).get('correct')), secs=r.get('secs') or 600.0,
                      tokens=r.get('completion_tokens') or 0, error='error' in r)
    return out


def arm(rows, choose):
    n = len(rows); pick = [r['on'] if choose(r, k) else r['off'] for k, r in enumerate(rows)]
    return (100 * sum(p['ok'] for p in pick) / n, sum(p['tokens'] for p in pick) / n,
            sum(p['secs'] for p in pick) / n, sorted(p['secs'] for p in pick)[n // 2],
            100 * sum(choose(r, k) for k, r in enumerate(rows)) / n)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('off'); ap.add_argument('on'); ap.add_argument('--out')
    a = ap.parse_args()
    off, on = load(a.off), load(a.on)
    rows = []
    for i in sorted(set(off) & set(on)):
        d, toks = features(ITEMS[i]['question'])
        rows.append(dict(id=i, subject=ITEMS[i]['subject'], off=off[i], on=on[i], dense=d, toks=toks,
                         y=1.0 if on[i]['ok'] and not off[i]['ok'] else 0.0))
    n = len(rows)
    both = sum(r['on']['ok'] and r['off']['ok'] for r in rows); only_on = sum(r['on']['ok'] and not r['off']['ok'] for r in rows)
    only_off = sum(r['off']['ok'] and not r['on']['ok'] for r in rows); neither = n - both - only_on - only_off
    print('%d questions. both right %d, only thinking-on right %d, only thinking-off right %d, neither %d'
          % (n, both, only_on, only_off, neither))
    print('thinking-on errors/timeouts: %d; hit token cap: off %d, on %d' % (
        sum(r['on']['error'] for r in rows), sum(r['off']['tokens'] >= 4096 for r in rows), sum(r['on']['tokens'] >= 16384 for r in rows)))
    print('\nby subject (accuracy off -> on, only-on vs only-off):')
    by = defaultdict(list)
    for r in rows: by[r['subject']].append(r)
    for s, rs in sorted(by.items()):
        print('  %-17s %5.1f%% -> %5.1f%%   %2d vs %2d' % (s, 100 * sum(r['off']['ok'] for r in rs) / len(rs),
              100 * sum(r['on']['ok'] for r in rs) / len(rs), sum(r['y'] for r in rs),
              sum(r['off']['ok'] and not r['on']['ok'] for r in rs)))

    # Learned switch.
    rnd = random.Random(7); idx = list(range(n)); rnd.shuffle(idx); s5 = [0.0] * n
    for f in range(5):
        test = set(idx[f::5]); m = fit([dict(r) for k, r in enumerate(rows) if k not in test])
        for k in test: s5[k] = score(m, ITEMS[rows[k]['id']]['question'])
    lo = [0.0] * n
    for s in by:
        m = fit([r for r in rows if r['subject'] != s])
        for k, r in enumerate(rows):
            if r['subject'] == s: lo[k] = score(m, ITEMS[r['id']]['question'])
    ys = [r['y'] for r in rows]
    print('\nswitch AUC (label: thinking needed): 5-fold %.3f, leave-one-subject-out %.3f' % (auc(s5, ys), auc(lo, ys)))
    # Subject-level policy (what a domain router can do): think on subjects where on beat off
    # in training folds, evaluated leave-one-subject-out is impossible (the subject is unseen),
    # so evaluate 5-fold by subject-mean of training rows.
    subj = [False] * n
    for f in range(5):
        test = set(idx[f::5]); gain = defaultdict(float)
        for k, r in enumerate(rows):
            if k not in test: gain[r['subject']] += r['y'] - (r['off']['ok'] and not r['on']['ok'])
        for k in test: subj[k] = gain[rows[k]['subject']] > 0
    print('\n%-34s %8s %10s %10s %10s %8s' % ('policy', 'accuracy', 'tokens', 'mean s', 'median s', 'think%'))
    for name, ch in [('always off', lambda r, k: False), ('always on', lambda r, k: True),
                     ('oracle (hindsight)', lambda r, k: r['y'] == 1.0),
                     ('subject switch (5-fold)', lambda r, k: subj[k])] + \
                    [('learned switch p>=%.2f (5-fold)' % t, (lambda t: lambda r, k: s5[k] >= t)(t)) for t in (0.05, 0.1, 0.2, 0.3)]:
        acc, tok, mean_s, med_s, share = arm(rows, ch)
        print('%-34s %7.1f%% %10.0f %10.1f %10.1f %7.0f%%' % (name, acc, tok, mean_s, med_s, share))
    if a.out:
        m = fit(rows); json.dump(m, open(a.out, 'w'), indent=0, sort_keys=True); print('wrote', a.out)


if __name__ == '__main__':
    main()
