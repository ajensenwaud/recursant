"""Validate the example router_config (as rewritten per episode) against a router binary."""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from bench.evaluation import live
cfg = json.load(open('bench/evaluation/live.example.json'))
for signals in ('off', 'on'):
    cfg['router_signals'] = signals
    rewritten, routes = live.episode_router_config(cfg, 'http://127.0.0.1:9/tok', 18080, 'routed-full')
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(rewritten, f)
    env = dict(PATH=os.environ['PATH'], M3_EPISODE_API='a'*32, M3_EPISODE_SOURCE='b'*32)
    proc = subprocess.run([sys.argv[1], 'validate', f.name, '--test-mode'], env=env, capture_output=True, text=True)
    print('signals=%s routes=%s exit=%d %s' % (signals, routes, proc.returncode, (proc.stdout+proc.stderr).strip()[:200]))
