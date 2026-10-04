"""Allocation H-sub (2026-10-04): subagent sessions on the cheap current model. Anders: "Do 1, 2, 3."
(item 3 of the token-lever follow-up, quoted US$3-5). Cap US$5 public.

Pack bench/multiagent (the three plain delegate tasks; the two PII tasks test compliance placement,
not routing, and need the slow private GPU). Hermes delegates to subagents; the router recognises
them from the request stream (class delegated_start). Arms, same Sonnet 5.5 at effort low with the
cache breakpoint, same harness limits:
  sonnet   Sonnet only (every session)
  mix      Sonnet + gpt-6-luna for tool_followup_ok / final_answer (today's G-mix winner)
  sub      mix + luna for delegated_start: a subagent's whole first turn starts on luna
Quality bar frozen before the run: an arm is no worse iff passes >= sonnet passes - 1.
usage: sub_agent.py ROUTER_BINARY ROUTER_COMMIT OUT_NAME CAP_USD REPEATS [--arms=a,b]
CAP_USD is split equally across the arms (one allocation file per arm; a file is never reused)."""
import copy, hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench.multiagent import run as ma
from bench.evaluation.pricing import LIST_PRICES  # one source for list prices

args = [a for a in sys.argv[1:] if not a.startswith('--arms')]
arms_flag = [a for a in sys.argv[1:] if a.startswith('--arms')]
BIN, COMMIT, NAME, CAP, REPEATS = args[0], args[1], args[2], float(args[3]), int(args[4])
ARMS = arms_flag[0].split('=', 1)[1].split(',') if arms_flag else ['sonnet', 'mix', 'sub']
FRONTIER, ECONOMY = 'anthropic/claude-sonnet-5.5', 'openai/gpt-6-luna'
ROOT = Path(__file__).resolve().parents[2] / '.hermes/runtime/m3-live'
pilot = json.load(open(ROOT / 'full-task.pilot.json'))
SHA = hashlib.sha256(Path(BIN).read_bytes()).hexdigest()
# Every arm is plain Hermes through the router (canonical arm routed-request); the arm label
# lives in the output directory and the manifest's 'label'.
tasks = [t for t in ma.load_tasks() if not t['pii']]
settings = dict(ma.SETTINGS, turns=40, output=16000, delegation={'max_iterations': 15, 'max_concurrent_children': 3},
                reasoning_effort='low', context=131072, request_cap=400, model=FRONTIER)
caps = dict(ma.CAPS)
for arm in ARMS:
    rc = ma.router_config()
    rc['aliases'] = [{'from': 'baseline', 'provider': 'openrouter', 'model': FRONTIER},
                     {'from': 'economy', 'provider': 'openrouter', 'model': ECONOMY},
                     {'from': 'local', 'provider': 'gx10', 'model': ma.LOCAL}]
    ctx = rc['context']; ctx['reasoning'] = 'steps'; ctx['reasoning_text'] = 'drop'
    base_c, econ, local = ctx['candidates']
    base_c.update(price=dict(LIST_PRICES[FRONTIER]),
                  reasoning={'family': 'openrouter', 'low': 'low', 'high': 'low'}, quality_evidence='HARNESS-DEFAULT-BASELINE-H-sub')
    econ.update(price=dict(LIST_PRICES[ECONOMY]),
                quality_evidence='UNQUALIFIED-CANDIDATE-UNDER-TEST-H-sub',
                qualified_tasks={'sonnet': [], 'mix': ['tool_followup_ok', 'final_answer'],
                                 'sub': ['tool_followup_ok', 'final_answer', 'delegated_start']}[arm])
    if arm == 'sonnet': ctx['candidates'] = [base_c, local]; rc['aliases'] = [a for a in rc['aliases'] if a['from'] != 'economy']
    config = dict(approved=True, approval_reference='Anders 2026-10-04 "Do 1, 2, 3."; docs/evidence/m3-live-budget-allocation.md H-sub',
                  allocation_id='H-sub', allocation_reference='H-sub: US$5 total, Anders 2026-10-04',
                  allocation_path=str(ROOT / ('%s-%s.allocation.jsonl' % (NAME, arm))),
                  paid_cap_usd=CAP / len(ARMS), request_cap=400, context_limit=131072, max_output=16000,
                  budget_review='identical in every arm: 40 parent turns, 15 child iterations, 3 concurrent children, 16000 output incl. thinking, effort low, 2400 s',
                  token_bound_evidence=pilot['token_bound_evidence'],
                  source_and_metrics_review='NOT independently reviewed. Router 8316190+tool_report, ctest signals/reasoning OK.',
                  isolation_reviewed=True, router_binary=BIN, router_sha256=SHA, router_source_commit=COMMIT,
                  router_signals='on', baseline_endpoint='public', baseline_provider='openrouter', baseline_model=FRONTIER,
                  upstreams=copy.deepcopy(pilot['upstreams']), router_config=rc)
    config['upstreams']['openrouter'].update(tokenizer='unknown-recorded-as-unknown (Claude Sonnet 5.5, gpt-6-luna)',
        serving_evidence='OpenRouter models list 2026-10-04 (Sonnet US$2/10; luna US$0.1/0.5 per Mtok)')
    config['upstreams']['gx10']['timeout_s'] = 300
    rows = ma.run(tasks, ['routed-request'], REPEATS, 4417, ROOT / NAME / arm, config=config, settings=settings)
    print(arm, json.dumps(ma.summarize(rows, ['routed-request'])['routed-request']), flush=True)
