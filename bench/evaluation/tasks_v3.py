"""Task pack v3 additions: 7 original synthetic (CC0) tasks, each with hidden
cases and a reference solution. Same shape as v1: stdin JSON lines -> stdout
JSON lines via solve(). Host-only."""

TASKS_V3 = [
 {'id': 'rle-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Input is {"op":"encode"|"decode","data":...}. encode takes a string and returns a list of [char,count] pairs for maximal runs, in order. decode takes such a list and returns the string. For decode, reject any pair whose count is not a positive integer or whose char is not exactly one character by returning {"error":"invalid"}. Empty inputs return an empty list or empty string. Unicode characters count as one character. Write and run tests; leave solution.py.'''},
 {'id': 'roman-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Input is {"to_roman":n} or {"from_roman":s}. to_roman converts an integer 1..3999 to canonical uppercase Roman numerals. from_roman accepts only canonical uppercase numerals for 1..3999 (reject non-canonical forms such as "IIII", "VX", "IC" or lowercase) and returns the integer. Any invalid input returns {"error":"invalid"}. Write tests covering subtractive forms and bounds; run them and leave solution.py.'''},
 {'id': 'inventory-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Each input is a list of operations applied in order to an empty inventory: {"op":"add","sku":s,"qty":q}, {"op":"remove","sku":s,"qty":q}, {"op":"reserve","sku":s,"qty":q}, {"op":"release","sku":s,"qty":q}. q is a positive integer. Stock available = on_hand - reserved. remove and reserve may not exceed available; release may not exceed reserved. An operation that would violate a rule is skipped and its zero-based index appended to "rejected". Output {"stock":{sku:{"on_hand":n,"reserved":m}},"rejected":[indices]} with skus sorted and skus whose on_hand and reserved are both zero omitted. Write tests and run them; leave solution.py.'''},
 {'id': 'semver-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Input is {"versions":[strings],"range":string}. Versions are MAJOR.MINOR.PATCH with non-negative integers and no leading zeros (except 0 itself); ignore invalid versions. The range is one comparator or several separated by single spaces, all of which must hold; comparators are ">=v", "<=v", ">v", "<v", "=v", "^v" (same major, >= v; for major 0, same minor and >= v) or "~v" (same major and minor, >= v). Return {"matches":[sorted ascending by version, as strings],"max":highest match or null}. An unparseable range returns {"error":"invalid_range"}. Write and run tests; leave solution.py.'''},
 {'id': 'csvsum-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Input is {"csv":string,"group":column,"sum":column}. The CSV has a header row, uses commas, and may contain double-quoted fields with commas and doubled quotes. Group rows by the group column and sum the sum column as integers; rows whose sum value is not an integer (after stripping surrounding whitespace) are counted in "skipped" and excluded. Output {"totals":{group:sum} with groups sorted, "skipped":n}. A missing column returns {"error":"missing_column"}. Empty lines are ignored. Write and run tests; leave solution.py.'''},
 {'id': 'calendar-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Input is {"start":"YYYY-MM-DD","business_days":n,"holidays":["YYYY-MM-DD",...]} with integer n (may be zero or negative). Move from start by n business days (Monday-Friday, excluding holidays): positive moves forward, negative moves backward, counting only business days after (or before) start. If n is zero and start is not a business day, return the next business day. Return {"date":"YYYY-MM-DD"}. Invalid dates return {"error":"invalid_date"}. Write and run tests; leave solution.py.'''},
 {'id': 'matrix-v1', 'prompt': '''Implement /workspace/solution.py using Python stdlib. Read one JSON value per stdin line and print one JSON result per line. Input is {"grid":[[0|1,...],...],"start":[r,c],"goal":[r,c]} where 1 is a wall. Moves are up, down, left and right. Return {"steps":n,"path":[[r,c],...]} for a shortest path from start to goal inclusive; among equal-length paths choose the one that is lexicographically smallest when compared as the list of coordinates. Return {"steps":-1,"path":[]} if unreachable or if start or goal is a wall or out of bounds. Write and run tests; leave solution.py.'''},
]

CASES_V3 = {
 'rle-v1': [({'op':'encode','data':''}, []), ({'op':'encode','data':'aaabcc'}, [['a',3],['b',1],['c',2]]),
            ({'op':'decode','data':[['é',2],['x',1]]}, 'ééx'), ({'op':'decode','data':[['a',0]]}, {'error':'invalid'}),
            ({'op':'decode','data':[['ab',1]]}, {'error':'invalid'}), ({'op':'decode','data':[]}, '')],
 'roman-v1': [({'to_roman':1994}, 'MCMXCIV'), ({'to_roman':3999}, 'MMMCMXCIX'), ({'from_roman':'XLIX'}, 49),
              ({'from_roman':'IIII'}, {'error':'invalid'}), ({'to_roman':0}, {'error':'invalid'}),
              ({'from_roman':'ic'}, {'error':'invalid'}), ({'from_roman':'IC'}, {'error':'invalid'})],
 'inventory-v1': [([], {'stock':{},'rejected':[]}),
   ([{'op':'add','sku':'b','qty':5},{'op':'reserve','sku':'b','qty':3},{'op':'remove','sku':'b','qty':3},{'op':'release','sku':'b','qty':1},{'op':'remove','sku':'b','qty':3}],
    {'stock':{'b':{'on_hand':2,'reserved':2}},'rejected':[2]}),
   ([{'op':'add','sku':'z','qty':1},{'op':'remove','sku':'z','qty':1},{'op':'release','sku':'a','qty':1},{'op':'add','sku':'a','qty':2}],
    {'stock':{'a':{'on_hand':2,'reserved':0}},'rejected':[2]}),
   ([{'op':'reserve','sku':'x','qty':1}], {'stock':{},'rejected':[0]})],
 'semver-v1': [({'versions':['1.2.3','1.10.0','2.0.0','01.0.0','1.2'],'range':'>=1.2.0 <2.0.0'}, {'matches':['1.2.3','1.10.0'],'max':'1.10.0'}),
   ({'versions':['0.2.1','0.2.9','0.3.0'],'range':'^0.2.1'}, {'matches':['0.2.1','0.2.9'],'max':'0.2.9'}),
   ({'versions':['1.4.0','1.4.9','1.5.0'],'range':'~1.4.2'}, {'matches':['1.4.9'],'max':'1.4.9'}),
   ({'versions':['1.0.0'],'range':'>>1'}, {'error':'invalid_range'}),
   ({'versions':['3.0.0'],'range':'<1.0.0'}, {'matches':[],'max':None})],
 'csvsum-v1': [({'csv':'team,pts\na,3\nb,4\na,5\n','group':'team','sum':'pts'}, {'totals':{'a':8,'b':4},'skipped':0}),
   ({'csv':'name,score\n"x, y",2\n"say ""hi""",x\n\n"x, y", 3 \n','group':'name','sum':'score'}, {'totals':{'x, y':5},'skipped':1}),
   ({'csv':'a,b\n1,2\n','group':'c','sum':'b'}, {'error':'missing_column'}),
   ({'csv':'g,v\nz,-2\nz,2\n','group':'g','sum':'v'}, {'totals':{'z':0},'skipped':0})],
 'calendar-v1': [({'start':'2026-09-25','business_days':1,'holidays':[]}, {'date':'2026-09-28'}),
   ({'start':'2026-09-28','business_days':-1,'holidays':['2026-09-25']}, {'date':'2026-09-24'}),
   ({'start':'2026-09-26','business_days':0,'holidays':['2026-09-28']}, {'date':'2026-09-29'}),
   ({'start':'2026-02-30','business_days':1,'holidays':[]}, {'error':'invalid_date'}),
   ({'start':'2026-12-24','business_days':3,'holidays':['2026-12-25','2026-12-28']}, {'date':'2026-12-31'})],
 'matrix-v1': [({'grid':[[0,0],[0,0]],'start':[0,0],'goal':[1,1]}, {'steps':2,'path':[[0,0],[0,1],[1,1]]}),
   ({'grid':[[0,1],[1,0]],'start':[0,0],'goal':[1,1]}, {'steps':-1,'path':[]}),
   ({'grid':[[0,0,0],[1,1,0],[0,0,0]],'start':[2,0],'goal':[0,0]}, {'steps':6,'path':[[2,0],[2,1],[2,2],[1,2],[0,2],[0,1],[0,0]]}),
   ({'grid':[[0]],'start':[0,0],'goal':[0,0]}, {'steps':0,'path':[[0,0]]}),
   ({'grid':[[1,0]],'start':[0,0],'goal':[0,1]}, {'steps':-1,'path':[]})],
}

SOLUTIONS_V3 = {
 'rle-v1': '''def solve(d):
 data=d['data']
 if d['op']=='encode':
  out=[]
  for ch in data:
   if out and out[-1][0]==ch: out[-1][1]+=1
   else: out.append([ch,1])
  return out
 s=[]
 for p in data:
  if not (isinstance(p,list) and len(p)==2 and isinstance(p[0],str) and len(p[0])==1 and type(p[1]) is int and p[1]>0): return {'error':'invalid'}
  s.append(p[0]*p[1])
 return ''.join(s)
''',
 'roman-v1': '''V=[(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
def to(n):
 s=''
 for v,r in V:
  while n>=v: s+=r; n-=v
 return s
def solve(d):
 if 'to_roman' in d:
  n=d['to_roman']
  return to(n) if type(n) is int and 1<=n<=3999 else {'error':'invalid'}
 s=d.get('from_roman')
 if isinstance(s,str):
  for n in range(1,4000):
   if to(n)==s: return n
 return {'error':'invalid'}
''',
 'inventory-v1': '''def solve(ops):
 st={}; rej=[]
 for i,o in enumerate(ops):
  s=st.setdefault(o['sku'],[0,0]); q=o['qty']
  if o['op']=='add': s[0]+=q
  elif o['op']=='remove':
   if q<=s[0]-s[1]: s[0]-=q
   else: rej.append(i)
  elif o['op']=='reserve':
   if q<=s[0]-s[1]: s[1]+=q
   else: rej.append(i)
  elif o['op']=='release':
   if q<=s[1]: s[1]-=q
   else: rej.append(i)
 return {'stock':{k:{'on_hand':v[0],'reserved':v[1]} for k,v in sorted(st.items()) if v!=[0,0]},'rejected':rej}
''',
 'semver-v1': '''import re
P=re.compile(r'(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$')
def pv(s):
 m=P.match(s) if isinstance(s,str) else None
 return tuple(map(int,m.groups())) if m else None
def solve(d):
 comps=[]
 for c in d['range'].split(' '):
  m=re.match(r'(>=|<=|>|<|=|\\^|~)(.*)$',c); v=pv(m.group(2)) if m else None
  if v is None: return {'error':'invalid_range'}
  comps.append((m.group(1),v))
 def ok(x):
  for op,v in comps:
   if op=='>=' and not x>=v: return False
   if op=='<=' and not x<=v: return False
   if op=='>' and not x>v: return False
   if op=='<' and not x<v: return False
   if op=='=' and not x==v: return False
   if op=='^' and not (x>=v and x[0]==v[0] and (v[0]!=0 or x[1]==v[1])): return False
   if op=='~' and not (x>=v and x[:2]==v[:2]): return False
  return True
 ms=sorted({pv(s) for s in d['versions'] if pv(s) and ok(pv(s))})
 out=['%d.%d.%d'%m for m in ms]
 return {'matches':out,'max':out[-1] if out else None}
''',
 'csvsum-v1': '''import csv,io
def solve(d):
 rows=[r for r in csv.reader(io.StringIO(d['csv'])) if r]
 if not rows: return {'error':'missing_column'}
 h=rows[0]
 if d['group'] not in h or d['sum'] not in h: return {'error':'missing_column'}
 g,s=h.index(d['group']),h.index(d['sum']); tot={}; skip=0
 for r in rows[1:]:
  try: v=int(r[s].strip(),10); assert r[s].strip().lstrip('-').isdigit()
  except Exception: skip+=1; continue
  tot[r[g]]=tot.get(r[g],0)+v
 return {'totals':dict(sorted(tot.items())),'skipped':skip}
''',
 'calendar-v1': '''import datetime as dt
def solve(d):
 try:
  day=dt.date.fromisoformat(d['start']); hol={dt.date.fromisoformat(h) for h in d['holidays']}
 except Exception: return {'error':'invalid_date'}
 biz=lambda x: x.weekday()<5 and x not in hol
 n=d['business_days']
 if n==0:
  while not biz(day): day+=dt.timedelta(days=1)
 step=dt.timedelta(days=1 if n>0 else -1)
 for _ in range(abs(n)):
  day+=step
  while not biz(day): day+=step
 return {'date':day.isoformat()}
''',
 'matrix-v1': '''def solve(d):
 g=d['grid']; R=len(g); C=len(g[0]) if R else 0
 s=tuple(d['start']); t=tuple(d['goal'])
 inb=lambda p: 0<=p[0]<R and 0<=p[1]<C and g[p[0]][p[1]]==0
 if not inb(s) or not inb(t): return {'steps':-1,'path':[]}
 dist={t:0}; q=[t]
 for p in q:
  for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)):
   n=(p[0]+dr,p[1]+dc)
   if inb(n) and n not in dist: dist[n]=dist[p]+1; q.append(n)
 if s not in dist: return {'steps':-1,'path':[]}
 path=[s]; p=s
 while p!=t:
  p=min(n for n in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1)) if n in dist and dist[n]==dist[p]-1)
  path.append(p)
 return {'steps':len(path)-1,'path':[list(x) for x in path]}
''',
}
