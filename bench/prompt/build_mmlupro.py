"""Build the reasoning-switch evaluation set from MMLU-Pro (TIGER-Lab/MMLU-Pro, test split, in
gx10's HF cache): a seeded sample of PER_CATEGORY questions from each of the 14 categories,
up to 10 options (A-J). Run on gx10 with a Python that has pyarrow (~/venvs/lmeval).
usage: python3 build_mmlupro.py OUT.jsonl [PER_CATEGORY]"""
import glob, json, os, random, sys
from collections import Counter, defaultdict
import pyarrow.parquet as pq

f = glob.glob(os.path.expanduser('~/.cache/huggingface/hub/datasets--TIGER-Lab--MMLU-Pro/snapshots/*/data/test-*.parquet'))[0]
per = int(sys.argv[2]) if len(sys.argv) > 2 else 70
by = defaultdict(list)
for x in pq.read_table(f).to_pylist(): by[x['category']].append(x)
r = random.Random(20261003); out = []
for cat in sorted(by):
    rows = by[cat]; r.shuffle(rows)
    for x in rows[:per]:
        q = x['question'].strip() + '\n\n' + '\n'.join('%s. %s' % ('ABCDEFGHIJ'[i], o) for i, o in enumerate(x['options']))
        out.append(dict(source='mmlu-pro', subject=cat, kind='mc', question=q, answer=x['answer'], src_id=x['question_id']))
for i, x in enumerate(out): x['id'] = i
with open(sys.argv[1], 'w') as fh:
    for x in out: fh.write(json.dumps(x) + '\n')
print(len(out), Counter(x['subject'] for x in out))
