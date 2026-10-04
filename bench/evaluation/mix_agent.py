"""Allocation G-mix (2026-10-04): a cheap current model for routine agent steps, Claude Sonnet 5.5
as the frontier. Anders: "ok do all three" (the ~US$8 live run from the token-lever review).
Cap US$8 public for all of G-mix (docs/evidence/m3-live-budget-allocation.md).

Arms, identical except the router's candidate list and rules (all with Sonnet at effort low on
every step via context.reasoning "steps", and the Claude prompt-cache breakpoint):
  sonnet  Sonnet only
  mix     Sonnet + openai/gpt-6-luna qualified for tool_followup_ok / final_answer (signals as shipped)
  phase   mix + context.phase "on" (the step after a read/search stays on Sonnet)
Quality bar frozen before the run: an arm is "no worse" iff its passes are at least the sonnet
arm's passes minus one over the same task-repeats.
usage: mix_agent.py ROUTER_BINARY ROUTER_COMMIT OUT_NAME CAP_USD REPEATS short|long [TASK_ID ...] [--arms=a,b]"""
import copy, hashlib, json, random, sys, threading
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench.evaluation.run import run_episode, write
from bench.evaluation.live import validate_live, create_allocation
from bench.evaluation.pricing import LIST_PRICES  # one source for list prices

args = [a for a in sys.argv[1:] if not a.startswith('--arms')]
arms_flag = [a for a in sys.argv[1:] if a.startswith('--arms')]
BIN, COMMIT, NAME, CAP, REPEATS, PACK = args[0], args[1], args[2], float(args[3]), int(args[4]), args[5]
ONLY = set(args[6:])
ARMS = arms_flag[0].split('=', 1)[1].split(',') if arms_flag else ['sonnet', 'mix', 'phase']
if PACK == 'short':
    from bench.evaluation.run import SETTINGS
    from bench.evaluation.tasks import TASKS, fingerprint
    hooks = lambda t: {}
    extra = dict(deadline_s=600)
else:
    from bench.longhorizon.run import load_tasks, seeder, verifier, fingerprint, SETTINGS
    TASKS = load_tasks()
    hooks = lambda t: dict(seed_workspace=seeder(t), verifier=verifier(t))
    extra = {}
FRONTIER, ECONOMY = 'anthropic/claude-sonnet-5.5', 'openai/gpt-6-luna'
SHA = hashlib.sha256(Path(BIN).read_bytes()).hexdigest()
ROOT = Path(__file__).resolve().parents[2] / '.hermes/runtime/m3-live'
base = json.load(open(ROOT / 'full-task.pilot.json'))
base.update(router_binary=BIN, router_sha256=SHA, router_source_commit=COMMIT, allocation_id='G-mix',
            paid_cap_usd=CAP, request_cap=3000, context_limit=131072, max_output=16000,
            allocation_path=str(ROOT / (NAME + '.allocation.jsonl')),
            allocation_reference='G-mix: US$8 total, Anders 2026-10-04 ("ok do all three")',
            approval_reference='Anders 2026-10-04 "ok do all three"; docs/evidence/m3-live-budget-allocation.md G-mix',
            baseline_model=FRONTIER,
            budget_review='identical for every arm: %s pack defaults, 16000 output incl. thinking, 131072 context' % PACK)
base['upstreams']['openrouter'].update(
    tokenizer='unknown-recorded-as-unknown (Claude Sonnet 5.5, gpt-6-luna); usage from provider native counts',
    serving_evidence='OpenRouter models list 2026-10-04 (anthropic/claude-sonnet-5.5 US$2/10; openai/gpt-6-luna US$0.1/0.5 per Mtok)')
rc = base['router_config']
for a in rc['aliases']:
    if a['from'] == 'baseline': a['model'] = FRONTIER
    if a['from'] == 'economy': a['model'] = ECONOMY
rc['context']['reasoning'] = 'steps'
rc['context']['reasoning_text'] = 'drop'
caps = {'tool_history': True, 'function_tools': True, 'parallel_tools': True, 'stream_tools': True,
        'nested_tool_schemas': True, 'reasoning_effort': ['low', 'medium', 'high']}
frontier = {'alias': 'baseline', 'quality_evidence': 'HARNESS-DEFAULT-BASELINE-G-mix', 'qualified_tasks': [],
            'context_limit': 131072, 'price': dict(LIST_PRICES[FRONTIER]),
            'reasoning': {'family': 'openrouter', 'low': 'low', 'high': 'low'}}
economy = {'alias': 'economy', 'quality_evidence': 'UNQUALIFIED-CANDIDATE-UNDER-TEST-G-mix',
           'qualified_tasks': ['tool_followup_ok', 'final_answer'], 'context_limit': 131072, 'capabilities': caps,
           'price': dict(LIST_PRICES[ECONOMY])}
configs = {}
for arm in ARMS:
    c = copy.deepcopy(base)
    c['router_config']['context']['candidates'] = [copy.deepcopy(frontier)] + ([copy.deepcopy(economy)] if arm != 'sonnet' else [])
    if arm == 'phase': c['router_config']['context']['phase'] = 'on'
    validate_live(c); configs[arm] = c
out = ROOT / NAME; out.mkdir(mode=0o700)
create_allocation(base)
settings = dict(SETTINGS, context=base['context_limit'], output=16000, model=FRONTIER, **extra)
budget = {'count': 0, 'reserved': Decimal('0'), 'lock': threading.Lock()}
rng = random.Random(1005); plan = []
tasks = [t for t in TASKS if not ONLY or t['id'] in ONLY]
for t in tasks:          # task-major: a cap stop leaves whole matched tasks
    for r in range(REPEATS):
        arms = list(ARMS); rng.shuffle(arms)
        plan += [(t, a, r) for a in arms]
write(out / 'manifest.json', {'task_pack_sha256': fingerprint(), 'router_sha256': SHA, 'router_commit': COMMIT, 'pack': PACK,
      'frontier': FRONTIER, 'economy': ECONOMY, 'arms': ARMS, 'settings': {k: settings[k] for k in ('turns', 'output', 'deadline_s', 'context')},
      'plan': [f"{t['id']}-r{r}-{a}" for t, a, r in plan],
      'quality_bar': 'an arm is no worse iff passes >= sonnet passes - 1 over the same task-repeats'})
rows = []
for task, arm, r in plan:
    eid = f"{task['id']}-r{r}-{arm}"
    try:
        row = run_episode(task, 'routed-structured', out / eid, settings, live_config=configs[arm], budget=budget, **hooks(task))
    except Exception as e:
        row = dict(success=False, failure='orchestration_' + type(e).__name__ + ': ' + str(e)[:200], calls=[])
    row.update(episode_id=eid, arm_label=arm, task=task['id'], repeat=r); rows.append(row)
    write(out / 'outcomes.json', rows)
    v = row.get('verifier') or {}
    models = sorted({c.get('provider_model') for c in row['calls']})
    print(eid, 'PASS' if row['success'] else 'FAIL', row.get('failure'), '%s/%s' % (v.get('passed'), v.get('total')),
          'usd=%.4f' % sum(float(c.get('cost_usd') or 0) for c in row['calls']), 'n=%d' % len(row['calls']),
          'economy_calls=%d' % sum(c.get('provider_model') == ECONOMY for c in row['calls']), flush=True)
print('requests', budget['count'], 'settled_reserved', budget['reserved'])
