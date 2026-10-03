"""Score the privacy pipeline stages on the design set and both held-out sets.

Stages (each adds to the previous):
  rules            compliance.identifiers (check digits, phone, BSB, passport, licence, DOB)
  + address rules  bench/privacy/addresses.py
  + model          a model's entities (names; addresses and the rest as the model labels them)
  + filters        bench/privacy/filters.drop
  + gate           keep only entities on lines the gate passes (bench/privacy/filters.gate)
The model ran on whole texts; the gate is applied to its entities afterwards, which is close
to, not identical with, running the model on gated lines only (context differs).

Held-out real conversations (bench/privacy/holdout.py) are scored per conversation: one
flag moves the conversation private for good, so that is the false-alarm rate that costs
money. Latency per request = gated characters x the model's measured ms per character.
usage: python3 -m bench.privacy.pipeline MODEL [MODEL ...]   (span files in .hermes/runtime/privacy/spans)"""
import json, sys
from collections import defaultdict
from bench.privacy import rules
from bench.privacy.addresses import addresses
from bench.privacy.build import ROOT
from bench.privacy.filters import drop, gate, merge

DIR = ROOT / '.hermes/runtime/privacy'
SETS = {'design': DIR / 'testset.jsonl', 'synth-holdout': DIR / 'synth-holdout.jsonl', 'holdout': DIR / 'holdout.jsonl'}
FREE = {'name', 'address', 'dob'}


def load(path):
    return [json.loads(l) for l in open(path)] if path.exists() else []


def detector(stage, spans):
    def run(item):
        text = item['text']
        kinds = rules.rules(text)
        if stage >= 1 and addresses(text): kinds.add('address')
        if stage >= 2 and spans is not None:
            ents = spans.get(item['id'], [])
            if stage >= 3: ents = [e for e in merge(ents, text) if not drop(e['kind'], e['text'], text, e['start'], e['end'])]
            if stage >= 4:
                rs = gate(text)
                ents = [e for e in ents if any(s <= e['start'] < t for s, t in rs)]
            kinds |= {e['kind'] for e in ents}
        return kinds
    return run


STAGES = ['rules', '+ address rules', '+ model', '+ filters', '+ gate']


def score_items(items, run):
    pos = [i for i in items if i['kinds']]; neg = [i for i in items if not i['kinds']]
    free = [i for i in pos if set(i['kinds']) <= FREE]
    flag = {i['id']: bool(run(i)) for i in items}
    names = [i for i in pos if 'name' in i['kinds']]
    fa = defaultdict(lambda: [0, 0])
    for i in neg:
        src = 'real' if i['source'].startswith('recorded') else 'decoys'
        fa[src][0] += flag[i['id']]; fa[src][1] += 1
    pct = lambda a, b: 100.0 * a / b if b else float('nan')
    return (pct(sum(flag[i['id']] for i in pos), len(pos)), pct(sum(flag[i['id']] for i in free), len(free)),
            pct(sum('name' in run(i) for i in names), len(names)), pct(*fa['real']), pct(*fa['decoys']))


def conversations(texts, steps, run, ms_per_char):
    by_id = {t['id']: t for t in texts}
    flagged = {t['id']: bool(run(t)) for t in texts}
    eps = defaultdict(list)
    for s in steps: eps[(s['episode'], s['pii_task'])].append(s)
    clean = [k for k in eps if not k[1]]; pii = [k for k in eps if k[1]]
    fa_conv = sum(any(flagged[i] for s in eps[k] for i in s['new']) for k in clean)
    pii_hit = sum(any(flagged[i] for s in eps[k] for i in s['new']) for k in pii)
    fa_text = sum(flagged[t['id']] for t in texts if not any(e.split('/')[1].find('-pii-') >= 0 for e in t['episodes']))
    n_clean_text = sum(1 for t in texts if not any('-pii-' in e for e in t['episodes']))
    lat = sorted(sum(sum(e - s for s, e in gate(by_id[i]['text'])) for i in st['new']) * ms_per_char for st in steps)
    full = sorted(sum(by_id[i]['chars'] for i in st['new']) * ms_per_char for st in steps)
    q = lambda xs, p: xs[int(p * (len(xs) - 1))]
    return fa_conv, len(clean), pii_hit, len(pii), fa_text, n_clean_text, (q(lat, .5), q(lat, .9), q(lat, .99)), (q(full, .5), q(full, .9), q(full, .99))


def main():
    models = sys.argv[1:] or ['bert-ner-i0']
    data = {k: load(p) for k, p in SETS.items()}
    steps = load(DIR / 'holdout-steps.jsonl')
    for model in models:
        spans, speed = {}, {}
        for k in SETS:
            p = DIR / 'spans' / ('span-%s-%s.jsonl' % (model, 'testset' if k == 'design' else k))
            rows = load(p)
            spans[k] = {r['id']: r['ents'] for r in rows} if rows else None
            if rows: speed[k] = sum(r['ms'] for r in rows) / sum(r['chars'] for r in rows)
        ms_per_char = speed.get('holdout') or speed.get('design') or 0.0
        print('\n== %s  (%.0f ms per 1,000 chars on 8 gx11 cores)' % (model, 1000 * ms_per_char))
        print('%-17s | design: recall  free-text  names  FA real  FA decoys | synth-holdout: recall  names  FA decoys | holdout real: FA conv  FA texts  PII convs flagged' % 'stage')
        for stage, name in enumerate(STAGES):
            d = score_items(data['design'], detector(stage, spans['design']))
            h = score_items(data['synth-holdout'], detector(stage, spans['synth-holdout'])) if data['synth-holdout'] else None
            row = '%-17s | %13.1f%% %9.1f%% %5.1f%% %7.1f%% %8.1f%% |' % ((name,) + d)
            if h and (stage < 2 or spans['synth-holdout'] is not None): row += ' %20.1f%% %5.1f%% %8.1f%% |' % (h[0], h[2], h[4])
            else: row += ' %37s |' % 'n/a'
            if steps and (stage < 2 or spans['holdout'] is not None):
                fc, nc, ph, npii, ft, nt, lat, full = conversations(data['holdout'], steps, detector(stage, spans['holdout']), ms_per_char)
                row += ' %3d/%d (%.1f%%) %4d/%d %6d/%d' % (fc, nc, 100.0 * fc / nc, ft, nt, ph, npii)
            print(row)
        if steps:
            *_, lat, full = conversations(data['holdout'], steps, detector(4, spans['holdout'] or {}), ms_per_char)
            print('model time per request, held-out conversations (p50/p90/p99 ms): whole new text %.0f/%.0f/%.0f, gated %.0f/%.0f/%.0f (estimated from ms per char)' % (full + lat))
            ms = {r['id']: r['ms'] for r in load(DIR / 'spans' / ('span-%s-holdout.jsonl' % model))}
            if ms:
                per = sorted(sum(ms.get(i, 0.0) for i in st['new']) for st in steps)
                q = lambda p: per[int(p * (len(per) - 1))]
                print('measured time per request in this run (p50/p90/p99/max ms): %.0f/%.0f/%.0f/%.0f' % (q(.5), q(.9), q(.99), per[-1]))


if __name__ == '__main__':
    main()
