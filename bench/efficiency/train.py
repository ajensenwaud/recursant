"""Leave-one-task-out evaluation of a small logistic-regression efficiency model.

Score = AUC: how well the predicted probability separates steps where the cheaper model
agrees with gpt-4.1 from steps where it does not (0.5 = coin flip, 1.0 = perfect). Compared
with today's rule (the step's signal class) on the same steps.
usage: python3 -m bench.efficiency.train"""
import math
from collections import defaultdict
from bench.efficiency.features import pairs


def auc(scores, labels):
    pos = [s for s, y in zip(scores, labels) if y]; neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg: return float('nan')
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def fit(rows, l2=1.0, steps=3000, rate=0.1):
    keys = sorted(rows[0][0]); w = {k: 0.0 for k in keys}
    for _ in range(steps):
        grad = {k: l2 * w[k] / len(rows) if k != 'bias' else 0.0 for k in keys}
        for x, y, *_ in rows:
            p = 1 / (1 + math.exp(-sum(w[k] * x[k] for k in keys)))
            for k in keys: grad[k] += (p - y) * x[k] / len(rows)
        for k in keys: w[k] -= rate * grad[k]
    return w


def predict(w, x):
    return 1 / (1 + math.exp(-sum(w[k] * x.get(k, 0.0) for k in w)))


def main():
    data = pairs()
    tasks = sorted({g for _, _, g, _ in data})
    scores, labels, rule, by_model = [], [], [], defaultdict(lambda: ([], []))
    for held in tasks:
        train = [r for r in data if r[2] != held]; test = [r for r in data if r[2] == held]
        w = fit(train)
        for x, y, _, meta in test:
            s = predict(w, x); scores.append(s); labels.append(y)
            rule.append(1.0 if meta['new'] not in (0, '0', None) else 0.0)   # rules would downshift
            by_model[meta['model']][0].append(s); by_model[meta['model']][1].append(y)
    print('steps %d, cheaper model agrees on %.0f%%' % (len(labels), 100 * sum(labels) / len(labels)))
    print('AUC, unseen task:  learned model %.2f   today\'s rule %.2f   (Jev judge on its own label: 0.64)' % (auc(scores, labels), auc(rule, labels)))
    for m, (s, y) in sorted(by_model.items()): print('  %s pairs: %d, AUC %.2f' % (m, len(y), auc(s, y)))
    # What a threshold would do: downshift only when predicted agreement >= t.
    for t in (0.6, 0.7, 0.8, 0.9):
        chosen = [y for s, y in zip(scores, labels) if s >= t]
        if chosen: print('  threshold %.1f: downshift %3d%% of steps, cheaper model agrees on %3.0f%% of them' % (t, 100 * len(chosen) / len(labels), 100 * sum(chosen) / len(chosen)))
    w = fit(data)
    print('weights (all data):', ', '.join('%s %+.2f' % (k, v) for k, v in sorted(w.items(), key=lambda kv: -abs(kv[1]))[:8]))


if __name__ == '__main__':
    main()
