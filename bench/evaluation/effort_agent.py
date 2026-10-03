"""Allocation F-agent: reasoning effort per agent step on Claude Sonnet 5.5 (2026-10-04).
Anders: "You need to test it on agentic workflows as well" (after approving the hard-question
test). Cap US$15 public in total for F-agent, recorded in docs/evidence/m3-live-budget-allocation.md.

Arms (all routed through the same Recursant binary, same Hermes fb67154, same model; identical
except the router's effort table, context.reasoning "steps"):
  low     every step effort low
  xhigh   every step effort xhigh
  switch  routine steps (signals: tool_followup_ok / final_answer) low; first step, failures
          and unclassified steps xhigh
Harness limits (identical for every arm, ASSISTANT-SELECTED, disclosed): 8 turns, max output
16000 tokens per request including thinking (4096 would cut xhigh thinking), 600 s task deadline,
131072 context bound. The router adds OpenRouter's automatic prompt-cache breakpoint for
Anthropic models in every arm.
Quality bar frozen before the run: an arm is "no worse" iff its passes are at least the xhigh
arm's passes minus one over the same task-repeats.
usage: effort_agent.py ROUTER_BINARY ROUTER_COMMIT OUT_NAME CAP_USD REPEATS [TASK_ID ...] [--arms a,b]"""
import copy, hashlib, json, random, sys, threading
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench.evaluation.run import run_episode, SETTINGS, write
from bench.evaluation.tasks import TASKS, fingerprint
from bench.evaluation.live import validate_live, create_allocation

args = [a for a in sys.argv[1:] if not a.startswith('--arms')]
arms_flag = [a for a in sys.argv[1:] if a.startswith('--arms')]
BIN, COMMIT, NAME, CAP, REPEATS = args[0], args[1], args[2], float(args[3]), int(args[4])
ONLY = set(args[5:])
ARMS = arms_flag[0].split('=', 1)[1].split(',') if arms_flag else ['low', 'xhigh', 'switch']
MODEL = 'anthropic/claude-sonnet-5.5'
SHA = hashlib.sha256(Path(BIN).read_bytes()).hexdigest()
ROOT = Path(__file__).resolve().parents[2] / '.hermes/runtime/m3-live'
base = json.load(open(ROOT / 'full-task.pilot.json'))
base.update(router_binary=BIN, router_sha256=SHA, router_source_commit=COMMIT, allocation_id='F-agent',
            paid_cap_usd=CAP, request_cap=3000, context_limit=131072, max_output=16000,
            allocation_path=str(ROOT / (NAME + '.allocation.jsonl')),
            allocation_reference='F-agent: US$15 total, Anders 2026-10-04 (agentic effort test)',
            approval_reference='Anders 2026-10-04 "You need to test it on agentic workflows as well"; docs/evidence/m3-live-budget-allocation.md F-agent',
            baseline_model=MODEL,
            budget_review='ASSISTANT-SELECTED, identical for every arm: 8 turns, 16000 output incl. thinking, 600 s deadline, 131072 context')
base['upstreams']['openrouter'].update(
    tokenizer='unknown-recorded-as-unknown (Claude Sonnet 5.5); usage from provider native counts',
    serving_evidence='OpenRouter models list 2026-10-04 (anthropic/claude-sonnet-5.5, US$2/US$10 per Mtok); probes in docs/evidence/m3-reasoning-effort-hard.md')
rc = base['router_config']
for a in rc['aliases']:
    if a['from'] == 'baseline': a['model'] = MODEL
rc['context']['reasoning'] = 'steps'
rc['context']['reasoning_text'] = 'drop'   # Claude streams reasoning_details; Hermes does not replay them
rc['context']['candidates'] = [{
    'alias': 'baseline', 'quality_evidence': 'HARNESS-DEFAULT-BASELINE-F-agent', 'qualified_tasks': [],
    'context_limit': 131072, 'price': {'input_per_mtok': 2.0, 'output_per_mtok': 10.0, 'cached_input_per_mtok': 0.2},
    'reasoning': None}]
TABLE = {'low': ('low', 'low'), 'xhigh': ('xhigh', 'xhigh'), 'switch': ('low', 'xhigh')}
configs = {}
for arm in ARMS:
    c = copy.deepcopy(base)
    lo, hi = TABLE[arm]
    c['router_config']['context']['candidates'][0]['reasoning'] = {'family': 'openrouter', 'low': lo, 'high': hi}
    validate_live(c); configs[arm] = c
out = ROOT / NAME; out.mkdir(mode=0o700)
create_allocation(base)
settings = dict(SETTINGS, context=base['context_limit'], output=16000, deadline_s=600, model=MODEL)
budget = {'count': 0, 'reserved': Decimal('0'), 'lock': threading.Lock()}
rng = random.Random(1004); plan = []
tasks = [t for t in TASKS if not ONLY or t['id'] in ONLY]
for r in range(REPEATS):
    for t in tasks:
        arms = list(ARMS); rng.shuffle(arms)
        plan += [(t, a, r) for a in arms]
write(out / 'manifest.json', {'task_pack_sha256': fingerprint(), 'router_sha256': SHA, 'router_commit': COMMIT, 'model': MODEL,
      'arms': {a: TABLE[a] for a in ARMS}, 'settings': {k: settings[k] for k in ('turns', 'output', 'deadline_s', 'context')},
      'plan': [f"{t['id']}-r{r}-{a}" for t, a, r in plan],
      'quality_bar': 'an arm is no worse iff passes >= xhigh passes - 1 over the same task-repeats'})
rows = []
for task, arm, r in plan:
    eid = f"{task['id']}-r{r}-{arm}"
    try:
        row = run_episode(task, 'routed-structured', out / eid, settings, live_config=configs[arm], budget=budget)
    except Exception as e:
        row = dict(success=False, failure='orchestration_' + type(e).__name__ + ': ' + str(e)[:200], calls=[])
    row.update(episode_id=eid, arm_label=arm, task=task['id'], repeat=r); rows.append(row)
    write(out / 'outcomes.json', rows)
    print(eid, 'PASS' if row['success'] else 'FAIL', row.get('failure'),
          'usd=%.4f' % sum(float(c.get('cost_usd') or 0) for c in row['calls']), 'n=%d' % len(row['calls']), flush=True)
print('requests', budget['count'], 'settled_reserved', budget['reserved'])
