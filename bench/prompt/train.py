"""Train and evaluate the prompt classifier on graded single-query answers.

Label: downshifting is safe (the economy model is correct, or the baseline is wrong too).
Model: logistic regression over the dense features plus a bag of words (tokens seen in at
least MIN_DF training questions), fitted with AdaGrad and L2.

Evaluation is the routing policy, not just AUC: at each threshold, the share of questions
sent to the economy model, the policy's accuracy against always-baseline, and its cost
(billed tokens of whichever model answered). Two splits:
  - random: 5-fold over all questions;
  - leave-one-source-out: train without a whole benchmark, test on it (does it generalise
    to a kind of question it never saw?).
usage: python3 -m bench.prompt.train ECONOMY.graded.jsonl BASELINE.graded.jsonl [--out weights.json]"""
import argparse, json, math, random
from collections import Counter, defaultdict
from pathlib import Path
from bench.prompt.features import DENSE, features, score

ROOT = Path(__file__).resolve().parents[2]
ITEMS = {json.loads(l)['id']: json.loads(l) for l in open(ROOT / '.hermes/runtime/prompt/single.jsonl')}
MIN_DF, VOCAB_MAX = 3, 20000


def load(econ, base):
    e = {json.loads(l)['id']: json.loads(l) for l in open(econ)}
    b = {json.loads(l)['id']: json.loads(l) for l in open(base)}
    rows = []
    for i in sorted(set(e) & set(b)):
        if e[i]['correct'] is None or b[i]['correct'] is None: continue
        d, toks = features(ITEMS[i]['question'])
        rows.append(dict(id=i, source=ITEMS[i]['source'], dense=d, toks=toks,
                         y=1.0 if (e[i]['correct'] or not b[i]['correct']) else 0.0,
                         ec=e[i]['correct'], bc=b[i]['correct'],
                         ecost=e[i].get('cost') or 0.0, bcost=b[i].get('cost') or 0.0))
    return rows


def fit(rows, l2=1e-3, epochs=40, lr=0.3, seed=1):
    df = Counter(t for r in rows for t in r['toks'])
    vocab = [t for t, c in df.most_common(VOCAB_MAX) if c >= MIN_DF]
    w = {k: 0.0 for k in DENSE}; v = {t: 0.0 for t in vocab}
    gw = defaultdict(lambda: 1e-8); gv = defaultdict(lambda: 1e-8)
    rnd = random.Random(seed); order = list(range(len(rows)))
    # Standardise nothing: dense features are already small (logs and fractions).
    for _ in range(epochs):
        rnd.shuffle(order)
        for idx in order:
            r = rows[idx]; toks = [t for t in r['toks'] if t in v]
            z = sum(w[k] * x for k, x in r['dense'].items()) + sum(v[t] for t in toks)
            p = 1 / (1 + math.exp(-max(-30, min(30, z)))); g = p - r['y']
            for k, x in r['dense'].items():
                grad = g * x + (0 if k == 'bias' else l2 * w[k]); gw[k] += grad * grad; w[k] -= lr * grad / math.sqrt(gw[k])
            for t in toks:
                grad = g + l2 * v[t]; gv[t] += grad * grad; v[t] -= lr * grad / math.sqrt(gv[t])
    v = {t: round(x, 6) for t, x in v.items() if abs(x) >= 1e-4}
    return {'weights': {k: round(x, 6) for k, x in w.items()}, 'vocab': v}


def auc(scores, labels):
    pairs = sorted(zip(scores, labels)); pos = sum(labels); neg = len(labels) - pos
    if not pos or not neg: return float('nan')
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]: j += 1
        rank_sum += sum(1 for k in range(i, j) if pairs[k][1]) * (i + j + 1) / 2; i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def policy(rows, scores, t):
    sent = [s >= t for s in scores]
    acc = sum((r['ec'] if s else r['bc']) for r, s in zip(rows, sent)) / len(rows)
    cost = sum((r['ecost'] if s else r['bcost']) for r, s in zip(rows, sent))
    return sum(sent) / len(rows), acc, cost


def report(name, rows, scores):
    base_acc = sum(r['bc'] for r in rows) / len(rows); econ_acc = sum(r['ec'] for r in rows) / len(rows)
    base_cost = sum(r['bcost'] for r in rows); econ_cost = sum(r['ecost'] for r in rows)
    print('\n== %s: %d questions; AUC %.3f' % (name, len(rows), auc(scores, [r['y'] for r in rows])))
    print('   always baseline: accuracy %.1f%%, cost US$%.3f; always economy: %.1f%%, US$%.3f'
          % (100 * base_acc, base_cost, 100 * econ_acc, econ_cost))
    # Oracle: economy wherever it is safe.
    oracle = [1.0 if r['y'] else 0.0 for r in rows]; share, acc, cost = policy(rows, oracle, 0.5)
    print('   oracle:          to economy %4.0f%%  accuracy %.1f%%  cost %3.0f%% of baseline' % (100 * share, 100 * acc, 100 * cost / base_cost))
    for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
        share, acc, cost = policy(rows, scores, t)
        print('   threshold %.2f:  to economy %4.0f%%  accuracy %.1f%% (%+.1f pts)  cost %3.0f%% of baseline'
              % (t, 100 * share, 100 * acc, 100 * (acc - base_acc), 100 * cost / base_cost))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('economy'); ap.add_argument('baseline'); ap.add_argument('--out')
    a = ap.parse_args()
    rows = load(a.economy, a.baseline)
    print('%d paired questions; safe-to-downshift %.1f%%' % (len(rows), 100 * sum(r['y'] for r in rows) / len(rows)))
    rnd = random.Random(7); idx = list(range(len(rows))); rnd.shuffle(idx)
    scores = [0.0] * len(rows)
    for f in range(5):
        test = set(idx[f::5]); m = fit([r for i, r in enumerate(rows) if i not in test])
        for i in test: scores[i] = score(m, ITEMS[rows[i]['id']]['question'])
    report('random 5-fold', rows, scores)
    lo = [0.0] * len(rows)
    for src in sorted({r['source'] for r in rows}):
        m = fit([r for r in rows if r['source'] != src])
        for i, r in enumerate(rows):
            if r['source'] == src: lo[i] = score(m, ITEMS[r['id']]['question'])
    report('leave-one-source-out', rows, lo)
    print('\n   by held-out source at threshold 0.8:')
    by = defaultdict(list)
    for i, r in enumerate(rows): by[r['source']].append(i)
    for src, ix in sorted(by.items()):
        rs = [rows[i] for i in ix]; share, acc, cost = policy(rs, [lo[i] for i in ix], 0.8)
        b = sum(r['bc'] for r in rs) / len(rs)
        print('   %-14s n=%3d  to economy %4.0f%%  accuracy %.1f%% vs %.1f%%  cost %3.0f%%'
              % (src, len(rs), 100 * share, 100 * acc, 100 * b, 100 * cost / max(1e-9, sum(r['bcost'] for r in rs))))
    if a.out:
        m = fit(rows); json.dump(m, open(a.out, 'w'), indent=0, sort_keys=True)
        print('\nwrote %s: %d vocabulary weights' % (a.out, len(m['vocab'])))


if __name__ == '__main__':
    main()
