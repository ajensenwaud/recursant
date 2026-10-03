"""Can the prompt classifier predict, from an agent task's opening instruction alone, whether
the economy model makes the same first move as gpt-4.1? Leave-one-task-out over the recorded
counterfactual pairs whose newest message is a user message (bench/efficiency pairs).
usage: python3 -m bench.prompt.openings"""
import math
from collections import defaultdict
from bench.efficiency.features import pairs, request_of, traces
from bench.prompt.features import features, message_text, score
from bench.prompt.train import auc, fit


def main():
    rows = []
    for _, same, task, m in pairs():
        if m['model'] != 'mini': continue
        run, ep, idx = m['key']; req = request_of(traces(run, ep)[idx])
        text = message_text(req)
        if text is None: continue
        d, toks = features(text)
        rows.append(dict(task=task, text=text, dense=d, toks=toks, y=same))
    tasks = sorted({r['task'] for r in rows})
    print('%d opening-instruction pairs over %d tasks; economy makes the same first move in %.0f%%'
          % (len(rows), len(tasks), 100 * sum(r['y'] for r in rows) / len(rows)))
    scores = [0.0] * len(rows)
    for t in tasks:
        m = fit([r for r in rows if r['task'] != t])
        for i, r in enumerate(rows):
            if r['task'] == t: scores[i] = score(m, r['text'])
    print('leave-one-task-out AUC %.3f (0.5 = no better than chance)' % auc(scores, [r['y'] for r in rows]))
    by = defaultdict(list)
    for r in rows: by[r['task']].append(r['y'])
    print('per task same-first-move rate: ' + ', '.join('%s %.0f%%' % (t, 100 * sum(v) / len(v)) for t, v in sorted(by.items())))


if __name__ == '__main__':
    main()
