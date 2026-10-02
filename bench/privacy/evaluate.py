"""Score detectors on the privacy test set.

A detector maps text -> set of kinds. For routing what matters is whether an item is
flagged at all (any kind): recall on items with personal data, and false alarms on items
without. Per-kind recall says what each detector can see. Predictions from model runs on
gx11 are read from JSONL files {"id", "kinds"}.
usage: python3 -m bench.privacy.evaluate [predictions.jsonl ...]"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
from bench.privacy import rules
from bench.privacy.build import OUT

UNSTRUCTURED = {'name', 'address', 'dob'}


def score(name, items, predict):
    pos = [i for i in items if i['kinds']]; neg = [i for i in items if not i['kinds']]
    flagged = {i['id']: bool(predict(i)) for i in items}
    found_kind, total_kind = Counter(), Counter()
    for i in pos:
        got = predict(i)
        for k in i['kinds']:
            total_kind[k] += 1
            if k in got: found_kind[k] += 1
    only_free = [i for i in pos if set(i['kinds']) <= UNSTRUCTURED]
    fa = defaultdict(lambda: [0, 0])
    for i in neg:
        src = 'recorded' if i['source'].startswith('recorded') else 'decoys'
        fa[src][0] += flagged[i['id']]; fa[src][1] += 1
    row = {
        'detector': name,
        'recall': sum(flagged[i['id']] for i in pos) / len(pos),
        'recall_free_text_only': sum(flagged[i['id']] for i in only_free) / max(1, len(only_free)),
        'false_alarm_recorded': fa['recorded'][0] / max(1, fa['recorded'][1]),
        'false_alarm_decoys': fa['decoys'][0] / max(1, fa['decoys'][1]),
        'per_kind': {k: round(found_kind[k] / total_kind[k], 2) for k in sorted(total_kind)},
    }
    return row


def show(row):
    print('%-28s recall %5.1f%%  free-text-only %5.1f%%  false alarms: real agent text %5.1f%%, decoys %5.1f%%' % (
        row['detector'], 100 * row['recall'], 100 * row['recall_free_text_only'],
        100 * row['false_alarm_recorded'], 100 * row['false_alarm_decoys']))
    print('%-28s %s' % ('', '  '.join('%s %d%%' % (k, 100 * v) for k, v in row['per_kind'].items())))


def main():
    items = [json.loads(l) for l in open(OUT)]
    results = [score('today (email rule)', items, lambda i: rules.today(i['text'])),
               score('rules (AU identifiers)', items, lambda i: rules.rules(i['text']))]
    for path in sys.argv[1:]:
        preds = {p['id']: set(p['kinds']) for p in map(json.loads, open(path))}
        name = Path(path).stem
        results.append(score(name, items, lambda i, preds=preds: preds.get(i['id'], set())))
        results.append(score(name + ' + rules', items, lambda i, preds=preds: preds.get(i['id'], set()) | rules.rules(i['text'])))
    for r in results: show(r)
    return results


if __name__ == '__main__':
    main()
