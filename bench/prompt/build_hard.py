"""Build the hard reasoning set (2026-10-04): questions where thinking should matter.
  - AIME 2024 (HuggingFaceH4/aime_2024) and AIME 2025 I+II (opencompass/AIME2025): 60, integer answers;
  - MATH-500 (HuggingFaceH4/MATH-500) level 4-5 problems whose answer is an integer: 156;
  - MMLU-Pro (TIGER-Lab/MMLU-Pro) math, physics, chemistry, engineering: 50 each, seeded, none of
    the 980 questions in mmlupro.jsonl (excluded by question_id).
Run on gx10 with ~/venvs/lmeval (datasets, pyarrow).
usage: python3 build_hard.py MMLUPRO_980.jsonl OUT.jsonl"""
import glob, json, os, random, re, sys
from collections import Counter, defaultdict
import pyarrow.parquet as pq
from datasets import load_dataset

used = {json.loads(l)['src_id'] for l in open(sys.argv[1])}
out = []
for x in load_dataset('HuggingFaceH4/aime_2024', split='train'):
    out.append(dict(source='aime', subject='aime', kind='number', question=x['problem'].strip(), answer=str(int(x['answer'])), src_id='2024-' + str(x['id'])))
for part in ('AIME2025-I', 'AIME2025-II'):
    for k, x in enumerate(load_dataset('opencompass/AIME2025', part, split='test')):
        out.append(dict(source='aime', subject='aime', kind='number', question=x['question'].strip(), answer=str(int(re.match(r'\d+', str(x['answer'])).group())), src_id='%s-%d' % (part, k)))
for x in load_dataset('HuggingFaceH4/MATH-500', split='test'):
    if x['level'] >= 4 and re.fullmatch(r'-?\d+', x['answer'].strip()):
        out.append(dict(source='math500', subject='math500-' + x['subject'].lower().replace(' ', '-'), kind='number',
                        question=x['problem'].strip(), answer=x['answer'].strip(), src_id=x['unique_id']))
f = glob.glob(os.path.expanduser('~/.cache/huggingface/hub/datasets--TIGER-Lab--MMLU-Pro/snapshots/*/data/test-*.parquet'))[0]
by = defaultdict(list)
for x in pq.read_table(f).to_pylist():
    if x['category'] in ('math', 'physics', 'chemistry', 'engineering') and x['question_id'] not in used: by[x['category']].append(x)
r = random.Random(20261004)
for cat in sorted(by):
    rows = by[cat]; r.shuffle(rows)
    for x in rows[:50]:
        q = x['question'].strip() + '\n\n' + '\n'.join('%s. %s' % ('ABCDEFGHIJ'[i], o) for i, o in enumerate(x['options']))
        out.append(dict(source='mmlu-pro', subject='mmlupro-' + cat, kind='mc', question=q, answer=x['answer'], src_id=x['question_id']))
for i, x in enumerate(out): x['id'] = i
with open(sys.argv[2], 'w') as fh:
    for x in out: fh.write(json.dumps(x) + '\n')
print(len(out), Counter(x['source'] for x in out))
