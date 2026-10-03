"""Grade answers to the single-query set. Multiple choice and numbers by the final
'Answer:' line; code by running the item's tests in a throwaway container (python:3.14-slim,
no network, 10 s per program, 512 MB).
usage: python3 -m bench.prompt.grade ANSWERS.jsonl [...]   (writes ANSWERS.graded.jsonl)"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS = {json.loads(l)['id']: json.loads(l) for l in open(ROOT / '.hermes/runtime/prompt/single.jsonl')}
RUNNER = r'''
import json, os, subprocess, sys
out = {}
for name in sorted(os.listdir('/progs')):
    try:
        p = subprocess.run([sys.executable, '/progs/' + name], capture_output=True, timeout=10)
        out[name] = p.returncode == 0
    except subprocess.TimeoutExpired:
        out[name] = False
print(json.dumps(out))
'''


def final_answer(text):
    m = re.findall(r'answer\s*[:：]\s*\**\s*\(?([^\n*)]+)', text or '', re.I)
    return m[-1].strip() if m else None


def mc_ok(text, gold):
    a = final_answer(text)
    if a is None:
        # No 'Answer:' line: accept a lone option letter opening the first or last line
        # ("C. Smaller inner circles", "(B)"), the same for every model.
        lines = [l.strip().strip('*') for l in (text or '').strip().splitlines() if l.strip()]
        for l in (lines[:1] + lines[-1:]):
            m = re.match(r'^\(?([A-P])(?:[.):]|$)', l)
            if m: a = m.group(1); break
    return bool(a) and a[:1].upper() == gold and (len(a) == 1 or not a[1].isalnum())


def num_ok(text, gold):
    a = final_answer(text)
    if a is None:   # no 'Answer:' line: the last number in the reply, for every model
        lines = [l for l in (text or '').strip().splitlines() if l.strip()]
        a = lines[-1] if lines else None
        if a is not None:
            found = re.findall(r'-?\d[\d,]*\.?\d*', a)
            a = found[-1] if found else None
    if a is None: return False
    nums = re.findall(r'-?\d[\d,]*\.?\d*', a)
    if not nums: return False
    try: return abs(float(nums[0].replace(',', '').rstrip('.')) - float(gold)) < 1e-6
    except ValueError: return False


def code_of(text, item):
    blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', text or '', re.S)
    code = max(blocks, key=len) if blocks else (text or '')
    if item['source'] == 'humaneval' and 'def ' + item['tests'].split('check(')[-1].split(')')[0] not in code:
        code = item['prompt'] + code   # a body-only completion
    return code


def main():
    for path in sys.argv[1:]:
        rows = [json.loads(l) for l in open(path)]
        graded, progs = {}, {}
        for r in rows:
            item = ITEMS[r['id']]
            if 'error' in r: graded[r['id']] = None; continue
            if item['kind'] == 'mc': graded[r['id']] = mc_ok(r.get('text'), item['answer'])
            elif item['kind'] == 'number': graded[r['id']] = num_ok(r.get('text'), item['answer'])
            else: progs['p%05d.py' % r['id']] = code_of(r.get('text'), item) + '\n\n' + item['tests'] + '\n'
        if progs:
            with tempfile.TemporaryDirectory() as d:
                for name, src in progs.items(): open(os.path.join(d, name), 'w').write(src)
                os.chmod(d, 0o755)
                res = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--memory', '512m', '--cpus', '2',
                                      '-v', d + ':/progs:ro', 'python:3.14-slim', 'python3', '-c', RUNNER],
                                     capture_output=True, text=True, timeout=3600)
                ran = json.loads(res.stdout.strip().splitlines()[-1])
                for name, ok in ran.items(): graded[int(name[1:6])] = ok
        out = path.replace('.jsonl', '.graded.jsonl')
        with open(out, 'w') as f:
            for r in rows: f.write(json.dumps({'id': r['id'], 'model': r['model'], 'correct': graded.get(r['id']),
                                               'cost': r.get('cost'), 'secs': r.get('secs'),
                                               'prompt_tokens': r.get('prompt_tokens'), 'completion_tokens': r.get('completion_tokens')}) + '\n')
        ok = [v for v in graded.values() if v is not None]
        print('%s: %d graded, %.1f%% correct, %d errors' % (path, len(ok), 100 * sum(ok) / max(1, len(ok)), sum(v is None for v in graded.values())))


if __name__ == '__main__':
    main()
