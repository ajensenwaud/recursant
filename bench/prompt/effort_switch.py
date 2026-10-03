"""Reasoning-effort switch on a public reasoning model (Phase 5 follow-up).

For each question, two answers from the same model: low effort and high effort. Can the
router's local encoder (plus the dense features) predict where high effort is needed, and is
the switch better than sending a random share of questions to high effort?

Label: high effort right and low effort wrong. Errors count as wrong. Out-of-fold scores,
5-fold and leave-one-subject-out, from bench/prompt/train.py's fitter on the router's own
embeddings (bench/prompt/embed_dump.c). Costs are OpenRouter's billed usage.cost.
usage: RC_PROMPT_ITEMS=.hermes/runtime/prompt/mmlupro.jsonl python3 -m bench.prompt.effort_switch
         LOW.jsonl HIGH.jsonl EMB.jsonl [--words]"""
import argparse, json, random
from collections import defaultdict
import bench.prompt.train as T


def load(path):
    raw = {json.loads(l)['id']: json.loads(l) for l in open(path)}
    graded = {json.loads(l)['id']: json.loads(l) for l in open(path.replace('.jsonl', '.graded.jsonl'))}
    return {i: dict(ok=bool(graded.get(i, {}).get('correct')), cost=r.get('cost') or 0.0, secs=r.get('secs') or 600.0,
                    tokens=r.get('completion_tokens') or 0, reasoning=r.get('reasoning_tokens') or 0, error='error' in r)
            for i, r in raw.items()}


def policy(rows, pick):
    n = len(rows); ch = [r['high'] if p else r['low'] for r, p in zip(rows, pick)]
    return dict(share=100 * sum(pick) / n, acc=100 * sum(c['ok'] for c in ch) / n, cost=sum(c['cost'] for c in ch),
                tokens=sum(c['tokens'] for c in ch) / n, mean=sum(c['secs'] for c in ch) / n, median=sorted(c['secs'] for c in ch)[n // 2])


def line(name, p, base_cost):
    return '  %-34s high %4.0f%%  correct %5.1f%%  cost US$%.4f (%3.0f%% of always-high)  %5.0f tok  %5.1f s mean  %4.1f s median' % (
        name, p['share'], p['acc'], p['cost'], 100 * p['cost'] / (base_cost or 1), p['tokens'], p['mean'], p['median'])


def oof(rows, groups):
    scores = [0.0] * len(rows)
    for g in groups:
        test = set(g); m = T.fit([r for k, r in enumerate(rows) if k not in test])
        for k in test: scores[k] = T.model_score(m, rows[k])
    return scores


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('low'); ap.add_argument('high'); ap.add_argument('emb')
    ap.add_argument('--words', action='store_true', help='word features instead of the encoder')
    a = ap.parse_args()
    if not a.words:
        for l in open(a.emb):
            r = json.loads(l); T.EMB[r['id']] = r['emb']
    low, high = load(a.low), load(a.high)
    rows = []
    for i in sorted(set(low) & set(high)):
        d, toks = T.features(T.ITEMS[i]['question'])
        if T.EMB: toks = []; d = dict(d); d.update(('e%d' % k, x) for k, x in enumerate(T.EMB[i]))
        rows.append(dict(id=i, subject=T.ITEMS[i]['subject'], low=low[i], high=high[i], dense=d, toks=toks,
                         y=1.0 if high[i]['ok'] and not low[i]['ok'] else 0.0))
    n = len(rows)
    only_hi = sum(r['y'] for r in rows); only_lo = sum(r['low']['ok'] and not r['high']['ok'] for r in rows)
    both = sum(r['low']['ok'] and r['high']['ok'] for r in rows)
    print('%d questions: both right %d, only high right %d, only low right %d, neither %d; errors low %d high %d' % (
        n, both, only_hi, only_lo, n - both - only_hi - only_lo, sum(r['low']['error'] for r in rows), sum(r['high']['error'] for r in rows)))
    print('reasoning tokens per answer: low %.0f, high %.0f' % (sum(r['low']['reasoning'] for r in rows) / n, sum(r['high']['reasoning'] for r in rows) / n))
    by = defaultdict(list)
    for r in rows: by[r['subject']].append(r)
    print('by subject (correct low -> high; only-high vs only-low):')
    for s, rs in sorted(by.items()):
        print('  %-17s %5.1f%% -> %5.1f%%   %2d vs %2d' % (s, 100 * sum(r['low']['ok'] for r in rs) / len(rs), 100 * sum(r['high']['ok'] for r in rs) / len(rs),
              sum(r['y'] for r in rs), sum(r['low']['ok'] and not r['high']['ok'] for r in rs)))
    base = policy(rows, [True] * n)['cost']
    print('\npolicies:')
    print(line('always low', policy(rows, [False] * n), base))
    print(line('always high', policy(rows, [True] * n), base))
    print(line('hindsight oracle', policy(rows, [bool(r['y']) for r in rows]), base))
    rnd = random.Random(7); idx = list(range(n)); rnd.shuffle(idx)
    splits = {'5-fold': [idx[f::5] for f in range(5)],
              'unseen subject': [[k for k, r in enumerate(rows) if r['subject'] == s] for s in sorted(by)]}
    for name, groups in splits.items():
        sc = oof(rows, groups)
        print('\n%s switch (%s): AUC %.3f' % ('word' if a.words else 'encoder', name, T.auc(sc, [r['y'] for r in rows])))
        order = sorted(range(n), key=lambda k: -sc[k])
        for share in (0.1, 0.2, 0.3, 0.5):
            top = set(order[:int(share * n)]); pick = [k in top for k in range(n)]
            print(line('top %d%% by score -> high' % (100 * share), policy(rows, pick), base))
            # Random mix at the same share, averaged over 200 draws.
            acc = cost = 0.0
            for d in range(200):
                rs = random.Random(1000 + d); chosen = set(rs.sample(range(n), int(share * n)))
                p = policy(rows, [k in chosen for k in range(n)]); acc += p['acc'] / 200; cost += p['cost'] / 200
            print('  %-34s           correct %5.1f%%  cost US$%.4f (%3.0f%% of always-high)' % ('  random %d%% -> high' % (100 * share), acc, cost, 100 * cost / (base or 1)))


if __name__ == '__main__':
    main()
