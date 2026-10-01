"""Offline validation of the M3 pilot config: no network egress beyond loopback."""
import copy, json, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, '/home/aj/projects/recursant-v4-m3-full-task-evaluation')
from bench.evaluation import live

P = '/home/aj/projects/recursant-v4/.hermes/runtime/m3-live/full-task.pilot.json'
cfg = json.load(open(P))
BIN = cfg['router_binary']
env = {'PATH': os.environ['PATH'], 'M3_EPISODE_API': 'dummy-api', 'M3_EPISODE_SOURCE': 'dummy-source',
       'OPENROUTER_API_KEY': 'dummy-not-a-key'}

def validate(router_cfg, label):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(router_cfg, f); path = f.name
    r = subprocess.run([BIN, 'validate', path, '--test-mode'], env=env, capture_output=True, text=True)
    os.unlink(path)
    print(f'[{label}] exit={r.returncode} stdout={r.stdout.strip()!r} stderr={r.stderr.strip()!r}')
    return r.returncode

# 1. raw router_config as written in the pilot
validate(cfg['router_config'], 'router_config as written')
# 2. the exact per-episode rewrite the runner produces for each routed arm
for arm in ('routed-structured', 'routed-full'):
    ep, trust = live.episode_router_config(cfg, 'http://127.0.0.1:9/token', 18080, arm)
    validate(ep, f'episode rewrite {arm}')
    print('   signals=', ep['context'].get('signals'), 'provider urls=', [p['url'] for p in ep['providers']], 'trust=', trust)

# 3. runner preflight as written (approved=false must be rejected)
for label, c in (('as written (approved=false)', cfg),
                 ('approved flipped in memory only', dict(cfg, approved=True))):
    try:
        live.validate_live(c); print(f'[validate_live {label}] PASS')
    except Exception as e:
        print(f'[validate_live {label}] REJECT {type(e).__name__}: {e}')
live.validate_allocation_limits(cfg); print('[validate_allocation_limits] PASS')
print('allocation_path exists:', Path(cfg['allocation_path']).exists())
print('baseline upstream:', live.resolve_upstream(cfg, cfg['baseline_endpoint'], cfg.get('baseline_provider')))

# 4. admission for the measured real Hermes profile (36,501 bytes, 19 tools, stream, reasoning_effort)
tools = [{'type': 'function', 'function': {'name': f't{i}', 'description': 'x' * 1800,
          'parameters': {'type': 'object', 'properties': {}}}} for i in range(19)]
body = {'model': 'openai/gpt-4.1', 'messages': [{'role': 'system', 'content': 's' * 3000},
        {'role': 'user', 'content': 'u' * 1500}], 'max_tokens': 4096, 'stream': True,
        'stream_options': {'include_usage': True}, 'reasoning_effort': 'medium', 'tools': tools}
n = len(json.dumps(body).encode())
for model in ('openai/gpt-4.1', 'openai/gpt-4.1-mini'):
    liab, upper = live.admission(cfg, 'public', dict(body, model=model))
    print(f'[admission {model}] body_bytes={n} upper={upper} liability=${float(liab):.4f} '
          f'max_calls_at_cap={int(cfg["paid_cap_usd"] / float(liab))}')
room = cfg['context_limit'] - 4096 - upper
print(f'[context headroom] {room} bytes of conversation growth before admission rejects (common to all arms)')
interp = {'model': 'GLM-5.3-Flash-EXL3', 'stream': False, 'max_tokens': 4096,
          'messages': [{'role': 'system', 'content': live.INTERPRETER_PREFIX + '...'}, {'role': 'user', 'content': '{}'}],
          'response_format': {'type': 'json_schema', 'json_schema': {'name': 'trajectory_state', 'schema': {}}}}
print('[admission interpreter]', live.admission(cfg, 'private', interp, 'gx10'),
      live.classify_role('routed-full', 'private', interp))
