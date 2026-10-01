"""Multi-agent M2+M3 benchmark: Hermes delegating to subagents, three arms.

  baseline-direct   Hermes straight to the baseline model (no router, no compliance)
  routed-request    plain Hermes through Recursant; sessions come from the request stream
  routed-telemetry  same router config, plus session-id headers and subagent hints

Compliance scanning is ON in both routed arms (text_mode "agent"). Two tasks carry a
synthetic personal-data file that exactly one subagent must read.

Fixture mode (default) needs a router binary and no inference: a scripted provider
plays the parent and the children (delegates, reads the data file, applies the
reference solution, runs the tests) behind the real router, so routing, lineage and
placement are exercised end to end for free.
  python3 -m bench.multiagent.run --router /path/to/recursant --out DIR
Live mode is parent-only and needs an approved config (see bench/evaluation/README.md).
"""
import argparse
import base64
import copy
import hashlib
import io
import json
import os
import random
import re
import tarfile
import tempfile
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path

from bench.evaluation import run as base
from bench.evaluation.live import INTEGRATION
from bench.evaluation.meter import Meter, serve
from bench.longhorizon.check import grade, materialise

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / 'tasks'
ARMS = ('baseline-direct', 'routed-request', 'routed-telemetry')
BASELINE, ECONOMY, LOCAL = 'openai/gpt-4.1', 'openai/gpt-4.1-mini', 'GLM-5.3-Flash-EXL3'
# Identical harness settings in every arm. reasoning_effort "low": the local model
# spends its whole output budget on reasoning at "medium" (measured 2026-09-30).
SETTINGS = dict(base.SETTINGS, turns=60, output=4096, deadline_s=2400, context=131072, request_cap=200,
                reasoning_effort='low', delegation={'max_iterations': 30, 'max_concurrent_children': 3},
                # Used only by the telemetry arm's plugin: label a session restricted before
                # any tool touches the task's data files.
                restricted_paths=['data/*', '/workspace/data/*'])
EFFORTS = ['low', 'medium', 'high']
CAPS = {'tool_history': True, 'function_tools': True, 'parallel_tools': True, 'stream_tools': True,
        'nested_tool_schemas': True, 'reasoning_effort': EFFORTS}
# The router's built-in email rule and the configured account-id rule.
PII = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+|ACCOUNT-[0-9]{4,}")


def router_config(judge=None):
    """One config for both routed arms. Endpoints/keys are rewritten per episode."""
    context = {
        'mode': 'active', 'tenant': 'local', 'project': 'evaluation', 'source_key_env': 'M3_EPISODE_SOURCE',
        'auto_alias': 'auto', 'baseline_alias': 'baseline', 'ttl_ms': 180000,
        'signals': 'on', 'sessions': 'request',
        'candidates': [
            {'alias': 'baseline', 'quality_evidence': 'HARNESS-DEFAULT-BASELINE-multiagent-v1',
             'qualified_tasks': [], 'context_limit': 131072,
             'price': {'input_per_mtok': 2.0, 'output_per_mtok': 8.0, 'cached_input_per_mtok': 0.5}},
            {'alias': 'economy', 'quality_evidence': 'UNQUALIFIED-CANDIDATE-UNDER-TEST-multiagent-v1',
             'qualified_tasks': ['tool_followup_ok', 'final_answer', 'delegated_start'], 'context_limit': 131072,
             'capabilities': copy.deepcopy(CAPS),
             'price': {'input_per_mtok': 0.4, 'output_per_mtok': 1.6, 'cached_input_per_mtok': 0.1}},
            # Private destination for requests compliance keeps off public providers.
            # Not qualified for any cost class: it is chosen only by compliance.
            {'alias': 'local', 'quality_evidence': 'PRIVATE-PLACEMENT-ONLY-multiagent-v1',
             'qualified_tasks': [], 'context_limit': 131072, 'capabilities': copy.deepcopy(CAPS),
             'price': {'input_per_mtok': 0.0, 'output_per_mtok': 0.0}}]}
    if judge: context['judge'] = judge
    return {
        'listen': {'host': '127.0.0.1', 'port': 1},
        'providers': [{'name': 'gx10', 'trust': 'private', 'url': 'http://127.0.0.1/v1', 'adapter': 'openai-compatible'},
                      {'name': 'openrouter', 'trust': 'public', 'url': 'https://openrouter.ai/api/v1',
                       'key_env': 'M3_EPISODE_API', 'adapter': 'openrouter'}],
        'private_default': {'provider': 'gx10', 'model': LOCAL},
        'auth': {'api_key_env': 'M3_EPISODE_API'},
        'aliases': [{'from': 'baseline', 'provider': 'openrouter', 'model': BASELINE},
                    {'from': 'economy', 'provider': 'openrouter', 'model': ECONOMY},
                    {'from': 'local', 'provider': 'gx10', 'model': LOCAL}],
        'limits': {'max_body_bytes': 4194304, 'max_connections': 32, 'request_timeout_seconds': 600},
        'compliance': {'enabled': True, 'public_allowed': True, 'patterns': ['ACCOUNT-[0-9]{4,}'],
                       'text_mode': 'agent'},
        'context': context}


def load_tasks(names=None):
    tasks = []
    for d in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
        if names and d.name not in names: continue
        tasks.append(dict(id=d.name, dir=d, prompt=(d / 'TASK.md').read_text(), pii=d.name.endswith('-pii-delegate')))
    return tasks


def fingerprint():
    h = hashlib.sha256()
    for p in sorted(TASKS_DIR.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(str(p.relative_to(TASKS_DIR)).encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()


def seeder(task):
    def seed(workspace: Path):
        import shutil
        shutil.copytree(task['dir'] / 'seed', workspace, dirs_exist_ok=True)
        (workspace / 'TASK.md').write_text(task['prompt'])
    return seed


def verifier(task):
    def verify(workspace: Path, out: Path):
        v = grade(task['dir'], workspace)
        (out / 'grader-output.private').write_text(v.pop('tail', '') or '')
        return v
    return verify


def reference_blob(task):
    with tempfile.TemporaryDirectory() as tmp:
        ref = materialise(task['dir'], Path(tmp) / 'r', True)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            for p in sorted(ref.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts and p.name != 'TASK.md':
                    tf.add(p, arcname=str(p.relative_to(ref)))
        return base64.b64encode(buf.getvalue()).decode()


class ScriptedTeam(Meter):
    """Scripted parent and children. No inference. Identifies the speaker from the
    request itself (first user message), as a real provider would have to."""
    GOAL = 'Scripted subagent %d for %s: implement your module from the reference and report back.'

    def __init__(self, task, request_cap):
        super().__init__(mode='fixture', request_cap=request_cap)
        self.task = task
        data = sorted(str(p.relative_to(task['dir'] / 'seed')) for p in (task['dir'] / 'seed').rglob('*')
                      if p.is_file() and 'data' in p.parts)
        self.data_file = data[0] if data else None
        self.goals = [self.GOAL % (i, task['id']) for i in range(3)]
        extract = ("python -c \"import base64,io,tarfile; tarfile.open(fileobj=io.BytesIO(base64.b64decode('"
                   + reference_blob(task) + "')),mode='r:gz').extractall('.', filter='data')\"")
        self.parent = [('delegate_task', {'tasks': [{'goal': g, 'context': 'Work in /workspace.'} for g in self.goals]}),
                       ('terminal', {'command': extract}),
                       ('terminal', {'command': 'python -m unittest discover -s tests 2>&1 | tail -3'})]
        # Child 0 owns the data-reading module when the task has a data file.
        self.child = {g: [('terminal', {'command': 'ls'})] for g in self.goals}
        if self.data_file:
            self.child[self.goals[0]] = [('terminal', {'command': 'head -n 6 ' + self.data_file}),
                                         ('terminal', {'command': 'wc -l ' + self.data_file})]

    def handle(self, path, body, headers):
        if path == '/v1/chat/completions': return self.dispatch(body, self.task['id'], 'fixture')
        return super().handle(path, body, headers)

    def dispatch(self, body, task_id, arm):
        msgs = body.get('messages') or []
        first = next((m.get('content') for m in msgs if m.get('role') == 'user'), '')
        first = first if isinstance(first, str) else ''
        who = 'parent' if self.task['prompt'].strip() in first else 'child'
        script = self.parent if who == 'parent' else next((s for g, s in self.child.items() if g in first), [])
        step = sum(1 for m in msgs if m.get('role') == 'assistant')
        with self.lock:
            if len(self.calls) >= self.request_cap:
                return 429, b'{"error":"request_cap"}', 'application/json'
            call = dict(dispatch_id=uuid.uuid4().hex, task_id=task_id, arm=arm, attempt=len(self.calls) + 1,
                        role='main', evidence_kind='fixture', cost_usd=None, started_at=time.time(),
                        who=who, step=step, model=body.get('model'), pii=bool(PII.search(json.dumps(msgs))))
            self.calls.append(call)
            self.traces.append({'dispatch_id': call['dispatch_id'], 'request': body})
        message = {'role': 'assistant', 'content': 'Scripted step; no inference.'}
        finish = 'stop'
        if step < len(script):
            name, args = script[step]
            message['tool_calls'] = [dict(index=0, id='s%d_%s' % (step, uuid.uuid4().hex[:6]), type='function',
                                          function=dict(name=name, arguments=json.dumps(args)))]
            finish = 'tool_calls'
        else:
            message['content'] = 'Module written.' if who == 'child' else 'Done: integrated and tested.'
        # Usage lets the router's cost model and the report work as in a live run.
        prompt = len(json.dumps(body)) // 4
        usage = {'prompt_tokens': prompt, 'completion_tokens': 40, 'total_tokens': prompt + 40}
        if body.get('stream'):
            chunk = dict(id=call['dispatch_id'], object='chat.completion.chunk', created=1, model=body.get('model'))
            chunks = [dict(chunk, choices=[dict(index=0, delta=message, finish_reason=None)]),
                      dict(chunk, choices=[dict(index=0, delta={}, finish_reason=finish)])]
            if (body.get('stream_options') or {}).get('include_usage'):
                chunks.append(dict(chunk, choices=[], usage=usage))
            raw = (''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n').encode()
            mime = 'text/event-stream'
        else:
            raw = json.dumps(dict(id=call['dispatch_id'], object='chat.completion', created=1, model=body.get('model'),
                                  choices=[dict(index=0, message=message, finish_reason=finish)], usage=usage)).encode()
            mime = 'application/json'
        call['finished_at'] = time.time(); call['status'] = 200
        return 200, raw, mime


def fixture_config(url, binary):
    upstream = {'url': url, 'reasoning_semantics': 'inclusive', 'tokenizer': 'fixture', 'serving_evidence': 'fixture'}
    return {'request_cap': 400, 'liability_usd_per_dispatch': 0.0, 'paid_cap_usd': 1, 'context_limit': 131072,
            'baseline_endpoint': 'public', 'baseline_provider': 'openrouter', 'baseline_model': BASELINE,
            'router_binary': binary, 'router_signals': 'on', 'router_config': router_config(),
            'upstreams': {'gx10': dict(upstream, model=LOCAL), 'openrouter': dict(upstream)}}


def episode_facts(row, out, task):
    """Routing facts for one episode, from the egress ledger and the router log only."""
    calls, traces = row.get('calls', []), {}
    try: traces = {t['dispatch_id']: t for t in json.loads((out / 'traces.private.json').read_text())}
    except (OSError, ValueError): pass
    models, pii_public, pii_private, parent, child = {}, 0, 0, 0, 0
    for c in calls:
        if c.get('role') != 'main': continue
        model = c.get('requested_model') or 'unknown'
        models[model] = models.get(model, 0) + 1
        body = (traces.get(c['dispatch_id']) or {}).get('request') or {}
        msgs = body.get('messages') or []
        first = next((m.get('content') for m in msgs if m.get('role') == 'user'), None)
        if isinstance(first, str) and task['prompt'].strip() in first: parent += 1
        else: child += 1
        if PII.search(json.dumps(body)):
            if c.get('endpoint') == 'public': pii_public += 1
            else: pii_private += 1
    log = ''
    try: log = (out / 'router.private.log').read_text()
    except OSError: pass
    sessions = [l for l in log.splitlines() if l.startswith('session ')]
    decisions = [l for l in log.splitlines() if l.startswith('route_decision ')]
    reasons = {}
    for l in decisions:
        m = re.search(r' reason=(\w+)', l)
        if m: reasons[m.group(1)] = reasons.get(m.group(1), 0) + 1
    usd = [c.get('cost_usd') for c in calls if c.get('endpoint') == 'public']
    return dict(models=models, parent_requests=parent, child_requests=child,
                pii_requests_public=pii_public, pii_requests_private=pii_private,
                sessions=len(sessions), delegated_by_request=sum(' lineage=request' in l for l in sessions),
                delegated_by_hint=sum(' lineage=hint' in l for l in sessions), reasons=reasons,
                public_usd=None if any(u is None for u in usd) else float(sum(Decimal(str(u)) for u in usd)),
                private_requests=sum(1 for c in calls if c.get('endpoint') == 'private'),
                subagents_started=(row.get('hook_counts') or {}).get('subagent_start', 0),
                rejected=sum(1 for c in calls if c.get('status') not in (200, None)))


def plan(tasks, arms, repeats, seed):
    rng = random.Random(seed); out = []
    for r in range(repeats):
        for t in tasks:
            order = list(arms); rng.shuffle(order)
            for a in order:
                out.append(dict(episode_id=f"{t['id']}-r{r}-{a}", pair_id=f"{t['id']}-r{r}", task_id=t['id'], arm=a, repeat=r))
    return out


def run(tasks, arms, repeats, seed, out, *, config=None, router=None, settings=None):
    """config: approved live config (parent only). router: binary path for fixture mode."""
    from bench.evaluation.live import validate_live, create_allocation
    settings = dict(settings or SETTINGS)
    if config:
        validate_live(config); settings['context'] = config['context_limit']
    assignments = plan(tasks, arms, repeats, seed)
    os.umask(0o077); out.mkdir(parents=True, exist_ok=False)
    if config: create_allocation(config)
    base.write(out / 'manifest.json', dict(version=1, kind='multiagent', evidence_kind='live' if config else 'fixture',
               task_pack_sha256=fingerprint(), image=base.IMAGE, settings=settings, arms=list(arms), repeats=repeats,
               seed=seed, assignments=assignments,
               router_sha256=hashlib.sha256(Path(config['router_binary'] if config else router).read_bytes()).hexdigest()))
    rows = []; budget = {'count': 0, 'reserved': Decimal('0'), 'lock': threading.Lock()}
    byid = {t['id']: t for t in tasks}
    for a in assignments:
        t = byid[a['task_id']]; episode = out / a['episode_id']
        per_arm = dict(settings, integration=INTEGRATION[a['arm']])
        try:
            if config:
                row = base.run_episode(t, a['arm'], episode, per_arm, live_config=config, budget=budget,
                                       seed_workspace=seeder(t), verifier=verifier(t))
            else:
                team = ScriptedTeam(t, per_arm['request_cap'])
                with serve(team, task_id=t['id'], arm=a['arm']) as url:
                    row = base.run_episode(t, a['arm'], episode, per_arm, live_config=fixture_config(url, router),
                                           protocol_fixture=True, seed_workspace=seeder(t), verifier=verifier(t))
                row['scripted'] = [dict(who=c['who'], step=c['step'], model=c['model'], pii=c['pii']) for c in team.calls]
        except Exception as exc:
            row = dict(success=False, calls=[], collection_complete=False,
                       failure='orchestration_' + type(exc).__name__ + ':' + str(exc)[:300])
        row.update(a); row['facts'] = episode_facts(row, episode, t); rows.append(row)
        base.write(out / 'outcomes.json', rows)
        f = row['facts']; v = row.get('verifier') or {}
        print(a['episode_id'], 'PASS' if row['success'] else 'FAIL', row.get('failure'),
              f"{v.get('passed')}/{v.get('total')}", 'usd=%s' % f['public_usd'], 'models=%s' % f['models'],
              'pii_public=%d pii_private=%d' % (f['pii_requests_public'], f['pii_requests_private']),
              'children=%d lineage(request=%d hint=%d)' % (f['subagents_started'], f['delegated_by_request'], f['delegated_by_hint']),
              flush=True)
    base.write(out / 'summary.json', summarize(rows, arms))
    return rows


def summarize(rows, arms):
    out = {}
    for arm in arms:
        mine = [r for r in rows if r['arm'] == arm]
        facts = [r['facts'] for r in mine]
        models = {}
        for f in facts:
            for m, n in f['models'].items(): models[m] = models.get(m, 0) + n
        usd = [f['public_usd'] for f in facts]
        out[arm] = dict(episodes=len(mine), passed=sum(bool(r['success']) for r in mine),
                        public_usd=None if any(u is None for u in usd) else round(sum(usd), 6),
                        requests_by_model=models, private_requests=sum(f['private_requests'] for f in facts),
                        pii_requests_public=sum(f['pii_requests_public'] for f in facts),
                        pii_requests_private=sum(f['pii_requests_private'] for f in facts),
                        subagents_started=sum(f['subagents_started'] for f in facts),
                        delegated_by_request=sum(f['delegated_by_request'] for f in facts),
                        delegated_by_hint=sum(f['delegated_by_hint'] for f in facts),
                        rejected_requests=sum(f['rejected'] for f in facts))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--router', type=Path, help='recursant binary (fixture mode)')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=1)
    ap.add_argument('--seed', type=int, default=4417)
    ap.add_argument('--tasks', nargs='*')
    ap.add_argument('--arms', nargs='*', default=list(ARMS))
    args = ap.parse_args(argv)
    if not args.router or not args.router.is_file(): ap.error('--router must be the recursant binary')
    rows = run(load_tasks(args.tasks), args.arms, args.repeats, args.seed, args.out, router=str(args.router.resolve()))
    print(json.dumps(summarize(rows, args.arms), indent=2))
    return 0 if all(r['success'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
