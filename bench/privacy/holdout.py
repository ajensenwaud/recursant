"""Held-out real agent conversations for the privacy detectors, scored per conversation.

The test set (bench/privacy/build.py) samples single texts from ma1-main3 and ma1-sig, and
the false-alarm filters (bench/privacy/filters.py) were written against it. This set comes
from runs that were not used for either: single-agent tasks (final-d, pilot-1..3, jev-check),
long-horizon tasks (lh1b) and the multi-agent runs ma1-main2/ma1-localcost.

The router only has to check text it has not seen in the conversation, so each request
contributes its NEW tool results and user messages (full length, not truncated). A
conversation (episode) is flagged if any of its new texts is flagged; once flagged it stays
private, so that is the unit that costs money.

Output (.hermes/runtime/privacy, never committed):
  holdout.jsonl        one unique text per line {id, text, chars, episodes}
  holdout-steps.jsonl  one request per line {episode, run, task, pii_task, step, new: [text ids]}
usage: python3 -m bench.privacy.holdout"""
import glob, json, re
from pathlib import Path
from bench.privacy.build import LIVE, ROOT

RUNS = ['final-d', 'pilot-1', 'pilot-2', 'pilot-3', 'jev-check', 'lh1b', 'ma1-main2', 'ma1-localcost']
OUT = ROOT / '.hermes/runtime/privacy/holdout.jsonl'
STEPS = ROOT / '.hermes/runtime/privacy/holdout-steps.jsonl'


def contents(req):
    for m in (req or {}).get('messages', []):
        c = m.get('content')
        if isinstance(c, list):   # content parts: keep the text parts
            c = '\n'.join(p.get('text', '') for p in c if isinstance(p, dict))
        if m.get('role') in ('tool', 'user') and isinstance(c, str) and c.strip():
            yield c


def main():
    texts, steps = {}, []
    for run in RUNS:
        for f in sorted(glob.glob(str(LIVE / run / '*/traces.private.json'))):
            episode = Path(f).parent.name
            task = re.sub(r'-r\d+-.*$', '', episode)
            seen = set()
            for n, t in enumerate(json.load(open(f))):
                req = t.get('request')
                if isinstance(req, str): req = json.loads(req)
                new = []
                for c in contents(req):
                    if c in seen: continue
                    seen.add(c)
                    tid = texts.setdefault(c, {'id': len(texts), 'text': c, 'chars': len(c), 'episodes': []})
                    if run + '/' + episode not in tid['episodes']: tid['episodes'].append(run + '/' + episode)
                    new.append(tid['id'])
                steps.append({'run': run, 'episode': run + '/' + episode, 'task': task, 'pii_task': '-pii-' in task,
                              'step': n, 'new': new})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as fh:
        for v in texts.values(): fh.write(json.dumps(v) + '\n')
    with open(STEPS, 'w') as fh:
        for s in steps: fh.write(json.dumps(s) + '\n')
    eps = {s['episode'] for s in steps}
    print('%d unique texts, %d chars, %d requests, %d conversations (%d from PII tasks)' % (
        len(texts), sum(v['chars'] for v in texts.values()), len(steps), len(eps),
        len({s['episode'] for s in steps if s['pii_task']})))


if __name__ == '__main__':
    main()
