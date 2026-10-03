"""Build the single-query evaluation set from benchmark datasets already in gx10's HF cache
(no downloads). Run on gx10 with a Python that has pyarrow (~/venvs/lmeval).

Each item: {id, source, kind, question, answer, tests?} where `question` is exactly what a
chat user would type (the answer-format instruction goes in a system message at ask time,
so the router's classifier never sees it).
usage: python3 build_single.py OUT.jsonl"""
import glob, json, os, random, sys
import pyarrow.parquet as pq

HUB = os.path.expanduser('~/.cache/huggingface/hub')
r = random.Random(20261003)


def rows(pattern):
    files = sorted(glob.glob(os.path.join(HUB, pattern)))
    if not files: raise SystemExit('missing ' + pattern)
    out = []
    for f in files: out += pq.read_table(f).to_pylist()
    return out


def pick(items, n):
    items = list(items); r.shuffle(items); return items[:n]


def mc(q, choices):
    return q.strip() + '\n\n' + '\n'.join('%s. %s' % ('ABCDEFGHIJKLMNOP'[i], c) for i, c in enumerate(choices))


out = []
# MMLU: 400 test questions spread over all subjects.
mm = rows('datasets--cais--mmlu/snapshots/*/*/test-*.parquet')
for x in pick([m for m in mm if m.get('subject')], 400):
    out.append(dict(source='mmlu', kind='mc', subject=x['subject'], question=mc(x['question'], x['choices']), answer='ABCD'[x['answer']]))
for name, n in (('ARC-Challenge', 150), ('ARC-Easy', 100)):
    for x in pick(rows('datasets--allenai--ai2_arc/snapshots/*/%s/test-*.parquet' % name), n):
        out.append(dict(source=name.lower(), kind='mc', question=mc(x['question'], x['choices']['text']),
                        answer='ABCDEFGHIJ'[x['choices']['label'].index(x['answerKey'])]))
for x in pick(rows('datasets--openai--gsm8k/snapshots/*/main/test-*.parquet'), 250):
    out.append(dict(source='gsm8k', kind='number', question=x['question'], answer=x['answer'].split('####')[-1].strip().replace(',', '')))
for x in pick(rows('datasets--google-research-datasets--mbpp/snapshots/*/full/test-*.parquet'), 150):
    out.append(dict(source='mbpp', kind='code', question=x['text'] + '\nYour function must pass tests like:\n' + x['test_list'][0],
                    answer='', tests=x['test_setup_code'] + '\n' + '\n'.join(x['test_list'])))
for x in pick(rows('datasets--openai--openai_humaneval/snapshots/*/openai_humaneval/test-*.parquet'), 100):
    out.append(dict(source='humaneval', kind='code', question='Complete this Python function:\n\n' + x['prompt'],
                    answer='', tests=x['test'] + '\ncheck(%s)\n' % x['entry_point'], prompt=x['prompt']))
for x in pick(rows('datasets--Rowan--hellaswag/snapshots/*/data/validation-*.parquet'), 100):
    out.append(dict(source='hellaswag', kind='mc', question=mc('Which ending is most plausible?\n\n' + x['ctx'], x['endings']), answer='ABCD'[int(x['label'])]))
for x in pick(rows('datasets--allenai--winogrande/snapshots/*/winogrande_xl/validation-*.parquet'), 100):
    out.append(dict(source='winogrande', kind='mc', question=mc('Fill in the blank (_):\n\n' + x['sentence'], [x['option1'], x['option2']]), answer='AB'[int(x['answer']) - 1]))
tq = rows('datasets--truthful_qa/snapshots/*/multiple_choice/validation-*.parquet')
for x in pick(tq, 100):
    ch = list(x['mc1_targets']['choices']); lab = list(x['mc1_targets']['labels'])
    if len(ch) > 16: continue
    idx = list(range(len(ch))); r.shuffle(idx)
    out.append(dict(source='truthfulqa', kind='mc', question=mc(x['question'], [ch[i] for i in idx]), answer='ABCDEFGHIJKLMNOP'[[lab[i] for i in idx].index(1)]))
for i, x in enumerate(out): x['id'] = i
with open(sys.argv[1], 'w') as f:
    for x in out: f.write(json.dumps(x) + '\n')
from collections import Counter
print(len(out), Counter(x['source'] for x in out))
