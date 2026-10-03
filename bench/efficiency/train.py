"""Leave-one-task-out evaluation of a small logistic-regression efficiency model.

Score = AUC: how well the predicted probability separates steps where the cheaper model
agrees with gpt-4.1 from steps where it does not (0.5 = coin flip, 1.0 = perfect). Compared
with today's rule (the step's signal class) on the same steps.
usage: python3 -m bench.efficiency.train"""
import json, math
from collections import defaultdict
from bench.efficiency.features import pairs


def auc(scores, labels):
    pos = [s for s, y in zip(scores, labels) if y]; neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg: return float('nan')
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def fit(rows, l2=1.0, iters=25):
    """L2-regularised logistic regression by Newton steps (fast enough for a few thousand
    rows in pure Python; gradient descent took minutes per fold)."""
    keys = sorted(rows[0][0]); n = len(keys)
    X = [[x.get(k, 0.0) for k in keys] for x, *_ in rows]; Y = [y for _, y, *_ in rows]
    w = [0.0] * n
    reg = [0.0 if k == 'bias' else l2 for k in keys]
    for _ in range(iters):
        g = [reg[j] * w[j] for j in range(n)]
        H = [[(reg[i] if i == j else 0.0) for j in range(n)] for i in range(n)]
        for x, y in zip(X, Y):
            z = sum(a * b for a, b in zip(w, x))
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
            s = p * (1 - p) + 1e-9
            for i in range(n):
                if x[i] == 0.0: continue
                g[i] += (p - y) * x[i]
                xi = s * x[i]; Hi = H[i]
                for j in range(n): Hi[j] += xi * x[j]
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(b) for b in step) < 1e-6: break
    return dict(zip(keys, w))


def solve(A, b):
    """Gaussian elimination with partial pivoting (A is small and positive definite)."""
    n = len(b); M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            if f:
                for k in range(c, n + 1): M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))) / M[r][r]
    return x


def predict(w, x):
    return 1 / (1 + math.exp(-sum(w[k] * x.get(k, 0.0) for k in w)))


def policies(scores, labels, strict, metas, data, tasks):
    """Today's signals rule (class f/a from bench/efficiency/classify_turns.c, held after a
    delegate_task result as gateway_context does) against the model, as a veto on the rule
    and as an addition to it. 'Agrees' is the cheaper model making gpt-4.1's move."""
    from bench.efficiency.features import LIVE
    cls = {}
    p = LIVE / 'signal-classes.txt'
    if not p.exists(): return
    for line in open(p):
        f, i, c = line.split()
        run, ep = f.split('/')[:2]; cls[(run, ep, int(i))] = c
    rows = [r for held in tasks for r in data if r[2] == held]   # same order as scores
    idx = [k for k, m in enumerate(metas) if m['key'] in cls]
    rule = {k: cls[metas[k]['key']] in 'fa' and not rows[k][0].get('last_call_delegate_task') for k in idx}
    def show(name, chosen):
        if not chosen: return
        print('  %-34s downshift %3d%%, agrees %3.0f%%, same target %3.0f%%' % (
            name, 100 * len(chosen) / len(idx), 100 * sum(labels[k] for k in chosen) / len(chosen), 100 * sum(strict[k] for k in chosen) / len(chosen)))
    print('policies on %d steps with a signal class (cheaper model agrees on %.0f%% overall):' % (len(idx), 100 * sum(labels[k] for k in idx) / len(idx)))
    show('rule (today)', [k for k in idx if rule[k]])
    show('rule not taken', [k for k in idx if not rule[k]])
    for t in (0.7, 0.8, 0.9):
        show('model >= %.1f' % t, [k for k in idx if scores[k] >= t])
        show('rule AND model >= %.1f (veto)' % t, [k for k in idx if rule[k] and scores[k] >= t])
        show('rule OR model >= %.1f (add)' % t, [k for k in idx if rule[k] or scores[k] >= t])


def export(path, exclude):
    """Fit on every pair except the excluded tasks and write a context.efficiency section."""
    from bench.efficiency.features import KEYS
    data = [r for r in pairs() if r[2] not in exclude]
    w = fit(data)
    section = {'weights': {k: round(w.get(k, 0.0), 6) for k in KEYS}, 'downshift_min': 0.8, 'veto_below': 0.8}
    with open(path, 'w') as f: json.dump(section, f, indent=1); f.write('\n')
    print('trained on %d pairs from %d tasks (excluded %d tasks) -> %s' % (len(data), len({r[2] for r in data}), len(exclude), path))


def main():
    import sys
    if sys.argv[1:2] == ['--export']:
        exclude = set(sys.argv[4].split(',')) if sys.argv[3:4] == ['--exclude'] else set()
        return export(sys.argv[2], exclude)
    from bench.efficiency.features import PAIR_FILES
    files = PAIR_FILES[:3] if sys.argv[1:] == ['old'] else PAIR_FILES   # 'old' = the 362 pairs before phase 3
    data = pairs(files)
    tasks = sorted({g for _, _, g, _ in data})
    scores, labels, rule, by_model, metas = [], [], [], defaultdict(lambda: ([], [])), []
    for held in tasks:
        train = [r for r in data if r[2] != held]; test = [r for r in data if r[2] == held]
        w = fit(train)
        for x, y, _, meta in test:
            s = predict(w, x); scores.append(s); labels.append(y); metas.append(meta)
            rule.append(None if meta['new'] is None else 1.0 if meta['new'] not in (0, '0') else 0.0)   # rules would downshift
            by_model[meta['model']][0].append(s); by_model[meta['model']][1].append(y)
    print('steps %d over %d tasks, cheaper model agrees on %.0f%%' % (len(labels), len(tasks), 100 * sum(labels) / len(labels)))
    known = [i for i, r in enumerate(rule) if r is not None]
    print('AUC, unseen task:  learned model %.2f   (Jev judge on its own label: 0.64)' % auc(scores, labels))
    print('  steps where today\'s rule is known (%d): learned %.2f, rule %.2f' % (
        len(known), auc([scores[i] for i in known], [labels[i] for i in known]), auc([rule[i] for i in known], [labels[i] for i in known])))
    old = [i for i, m in enumerate(metas) if m['file'] != 'mini-counterfactual-e1.jsonl']
    print('  the original pairs only (%d): AUC %.2f' % (len(old), auc([scores[i] for i in old], [labels[i] for i in old])))
    strict = [m['same_target'] for m in metas]
    print('  stricter label, same tool AND same target (agree %.0f%%): AUC %.2f' % (100 * sum(strict) / len(strict), auc(scores, strict)))
    for m, (s, y) in sorted(by_model.items()): print('  %s pairs: %d, AUC %.2f' % (m, len(y), auc(s, y)))
    # Pooled AUC also rewards telling easy tasks from hard ones; within-task AUC is what a
    # per-step decision inside one job can use.
    per = defaultdict(lambda: ([], []))
    for (x, y, g, meta), s in zip([r for held in tasks for r in data if r[2] == held], scores):
        per[g][0].append(s); per[g][1].append(y)
    vals = [(len(y), auc(s, y)) for s, y in per.values() if 0 < sum(y) < len(y)]
    print('  within-task AUC, step-weighted over %d tasks with both outcomes: %.2f' % (len(vals), sum(n * a for n, a in vals) / sum(n for n, _ in vals)))
    # What a threshold would do: downshift only when predicted agreement >= t.
    for t in (0.6, 0.7, 0.8, 0.9):
        chosen = [i for i, s in enumerate(scores) if s >= t]
        if chosen: print('  threshold %.1f: downshift %3d%% of steps, cheaper model agrees on %3.0f%% of them (same target %3.0f%%)' % (
            t, 100 * len(chosen) / len(labels), 100 * sum(labels[i] for i in chosen) / len(chosen), 100 * sum(strict[i] for i in chosen) / len(chosen)))
    policies(scores, labels, strict, metas, data, tasks)
    w = fit(data)
    print('weights (all data):', ', '.join('%s %+.2f' % (k, v) for k, v in sorted(w.items(), key=lambda kv: -abs(kv[1]))[:8]))


if __name__ == '__main__':
    main()
