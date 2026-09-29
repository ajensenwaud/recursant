"""Frozen synthetic task pack v2 (v1 specifications + explicit artifact instruction). Host-only: never mount in model containers.

Original public-domain (CC0) specifications/data, authored for this benchmark.
These are development tasks, not an uncontaminated third-party holdout.
"""
import hashlib
import json

TASKS = [
    {'id': 'ledger-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. It must read one JSON value per stdin line and print one JSON result per line. Each input is a list of ledger event objects with id (string), version (nonnegative integer), account (string), cents (integer), and void (boolean). Keep the highest version for each id; ties use the LAST event in input order. Remove events whose winning version has void=true. Sum cents per account, retaining accounts with zero sums. Output a JSON object mapping accounts to sums, sorted lexicographically. Do not mutate the input. Handle empty input, negative amounts, changing accounts, duplicate versions, and void/reinstatement. Write tests and run them; leave the executable solution.py artifact.'''},
    {'id': 'intervals-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one result per line. Input has busy: list of [start,end] integer half-open intervals and window: [lo,hi], where lo<=hi. Reject any reversed busy interval by printing {"error":"reversed"}, even if it is outside the window. Otherwise clip busy intervals to the window, drop zero lengths, merge overlaps and touching intervals, and return {"busy":merged,"free":complement} with ascending disjoint lists. Empty windows return empty lists. Inputs may be unsorted, duplicate, nested, negative, or outside the window. Write and run tests; leave solution.py.'''},
    {'id': 'dag-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON object per stdin line and print one JSON result per line. Input maps job names to {"duration":nonnegative integer,"deps":[names]}. Unknown dependencies return {"error":"unknown_dependency"} before any cycle check. Cycles return {"error":"cycle"}. Otherwise use unlimited workers to compute each job's earliest finish and total makespan. Return {"finish":{name:time},"makespan":integer,"order":[names]}, with lexicographically smallest available job chosen at every step of a topological sort. Duplicate dependencies count only once. Empty input yields empty finish/order and makespan zero. Write tests covering ordering, dependencies, cycles and duration zero; run them and leave solution.py.'''},
]

# Expected values do not depend on candidate output or on the fixture solver.
CASES = {
 'ledger-v1': [([], {}),
  ([{'id':'x','version':1,'account':'a','cents':20,'void':False},
    {'id':'x','version':2,'account':'b','cents':-7,'void':False},
    {'id':'y','version':0,'account':'b','cents':7,'void':False}], {'b':0}),
  ([{'id':'x','version':3,'account':'a','cents':10,'void':True},
    {'id':'x','version':2,'account':'a','cents':99,'void':False}], {}),
  ([{'id':'x','version':4,'account':'a','cents':1,'void':True},
    {'id':'x','version':4,'account':'z','cents':4,'void':False},
    {'id':'y','version':0,'account':'a','cents':-2,'void':False}], {'a':-2,'z':4})],
 'intervals-v1': [({'busy':[], 'window':[0,9]}, {'busy':[], 'free':[[0,9]]}),
  ({'busy':[[8,20],[-3,2],[2,4],[1,3],[6,6]],'window':[0,10]}, {'busy':[[0,4],[8,10]],'free':[[4,8]]}),
  ({'busy':[[9,2]],'window':[0,0]}, {'error':'reversed'}),
  ({'busy':[[-5,-2],[4,8]],'window':[1,1]}, {'busy':[],'free':[]}),
  ({'busy':[[1,8],[2,4],[8,9],[1,8]],'window':[0,10]}, {'busy':[[1,9]],'free':[[0,1],[9,10]]})],
 'dag-v1': [({}, {'finish':{},'makespan':0,'order':[]}),
  ({'z':{'duration':3,'deps':['a','a']},'a':{'duration':2,'deps':[]},'b':{'duration':7,'deps':[]},'c':{'duration':0,'deps':['z','b']}}, {'finish':{'a':2,'b':7,'z':5,'c':7},'makespan':7,'order':['a','b','z','c']}),
  ({'a':{'duration':1,'deps':['a']}}, {'error':'cycle'}),
  ({'a':{'duration':1,'deps':['a','missing']}}, {'error':'unknown_dependency'}),
  ({'z':{'duration':0,'deps':[]},'b':{'duration':1,'deps':['z']},'a':{'duration':1,'deps':['b']}}, {'finish':{'z':0,'b':1,'a':2},'makespan':2,'order':['z','b','a']})]
}

CLI = '\nif __name__ == "__main__":\n import sys, json\n for line in sys.stdin:\n  print(json.dumps(solve(json.loads(line)), sort_keys=True))\n'
FIXTURE_SOLUTIONS = {
 'ledger-v1': '''def solve(events):
 latest = {}
 for event in events:
  if event['id'] not in latest or event['version'] >= latest[event['id']]['version']:
   latest[event['id']] = event
 totals = {}
 for e in latest.values():
  if not e['void']: totals[e['account']] = totals.get(e['account'], 0) + e['cents']
 return dict(sorted(totals.items()))
''',
 'intervals-v1': '''def solve(data):
 lo, hi = data['window']
 if any(a>b for a,b in data['busy']): return {'error':'reversed'}
 merged = []
 for a,b in sorted((max(a,lo),min(b,hi)) for a,b in data['busy']):
  if a>=b: continue
  if merged and a<=merged[-1][1]: merged[-1][1] = max(merged[-1][1],b)
  else: merged.append([a,b])
 free = []; cursor=lo
 for a,b in merged:
  if cursor<a: free.append([cursor,a])
  cursor=b
 if cursor<hi: free.append([cursor,hi])
 return {'busy':merged,'free':free}
''',
 'dag-v1': '''def solve(jobs):
 if any(dep not in jobs for job in jobs.values() for dep in job['deps']):
  return {'error':'unknown_dependency'}
 finish = {}; order = []
 while len(finish)<len(jobs):
  ready=sorted(n for n,j in jobs.items() if n not in finish and all(d in finish for d in j['deps']))
  if not ready: return {'error':'cycle'}
  n=ready[0]; j=jobs[n]
  finish[n]=j['duration']+max((finish[d] for d in j['deps']),default=0)
  order.append(n)
 return {'finish':finish,'makespan':max(finish.values(),default=0),'order':order}
'''
}
FIXTURE_SOLUTIONS = {k:v+CLI for k,v in FIXTURE_SOLUTIONS.items()}


# v2 (2026-09-29): pilot-3 showed 6/18 episodes (2 per arm, all on turn-1
# gpt-4.1 before any routing) answering with code in chat and never writing
# the file, which the verifier scores as missing_or_invalid_artifact. The
# instruction is identical for every arm; specifications and cases unchanged.
ARTIFACT_INSTRUCTION = ('\n\nUse your file tools to create /workspace/solution.py on disk. '
                        'Code shown only in a chat reply does not count and will be graded as missing.')
for _task in TASKS:
    _task['prompt'] += ARTIFACT_INSTRUCTION
del _task


def fingerprint():
    return hashlib.sha256(json.dumps({'version':2,'tasks':TASKS,'cases':CASES},
                                    sort_keys=True).encode()).hexdigest()


def grade(task_id, invoke):
    verdicts = []
    for value, expected in CASES[task_id]:
        try:
            actual = invoke(json.loads(json.dumps(value)))
            verdicts.append(type(actual) is type(expected) and actual == expected)
        except Exception:
            verdicts.append(False)
    return {'success': all(verdicts), 'passed':sum(verdicts), 'total':len(verdicts)}
