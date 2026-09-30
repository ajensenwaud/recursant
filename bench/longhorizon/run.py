"""Long-horizon M3 runner: seeded multi-file workspaces, hidden-test grading, same
pinned Hermes harness, sandbox, meter and live routing arms as bench.evaluation.

Fixture mode (default) replays a scripted agent that explores, applies the reference
solution and runs the real test suite, so tool latencies and lifecycle telemetry are
real while inference is scripted and free."""
import argparse
import base64
import hashlib
import io
import json
import os
import random
import shutil
import tarfile
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path

from bench.evaluation import run as base
from bench.evaluation.meter import Meter
from bench.longhorizon.check import grade, materialise

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / 'tasks'
SETTINGS = dict(base.SETTINGS, turns=80, output=4096, deadline_s=1500, context=131072, request_cap=120)


def load_tasks():
    tasks = []
    for d in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
        tasks.append(dict(id=d.name, dir=d, prompt=(d / 'TASK.md').read_text()))
    return tasks


def fingerprint():
    h = hashlib.sha256()
    for p in sorted(TASKS_DIR.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(str(p.relative_to(TASKS_DIR)).encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()


def seeder(task):
    def seed(workspace: Path):
        shutil.copytree(task['dir'] / 'seed', workspace, dirs_exist_ok=True)
        (workspace / 'TASK.md').write_text(task['prompt'])
    return seed


def verifier(task):
    def verify(workspace: Path, out: Path):
        v = grade(task['dir'], workspace)
        (out / 'grader-output.private').write_text(v.pop('tail', '') or '')
        return v
    return verify


def reference_tarball(task):
    with tempfile_dir() as tmp:
        ref = materialise(task['dir'], Path(tmp) / 'r', True)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            for p in sorted(ref.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:
                    tf.add(p, arcname=str(p.relative_to(ref)))
        deletes = (task['dir'] / 'reference' / 'DELETE')
        return base64.b64encode(buf.getvalue()).decode(), (deletes.read_text().split() if deletes.exists() else [])


class tempfile_dir:
    def __enter__(self):
        import tempfile
        self.t = tempfile.TemporaryDirectory(); return self.t.name

    def __exit__(self, *a):
        self.t.cleanup()


class ScriptedLongMeter(Meter):
    """Scripted multi-step agent: explore, read every file, apply reference, run tests."""

    def __init__(self, task, request_cap):
        super().__init__(mode='fixture', request_cap=request_cap)
        blob, deletes = reference_tarball(task)
        files = sorted(str(p.relative_to(task['dir'] / 'seed')) for p in (task['dir'] / 'seed').rglob('*')
                       if p.is_file())
        self.steps = [('terminal', {'command': 'pwd && ls -R'})]
        self.steps += [('read_file', {'path': '/workspace/' + f}) for f in files]
        self.steps += [('terminal', {'command': 'python -m unittest discover -s tests 2>&1 | tail -5'})]
        rm = ''.join(f"; rm -f {d}" for d in deletes)
        self.steps += [('terminal', {'command': "python -c \"import base64,io,tarfile; tarfile.open(fileobj=io.BytesIO("
                                                "base64.b64decode('" + blob + "')),mode='r:gz').extractall('.', filter='data')\"" + rm})]
        self.steps += [('terminal', {'command': 'python -m unittest discover -s tests 2>&1 | tail -5'})]

    def dispatch(self, body, task_id, arm):
        with self.lock:
            if len(self.calls) >= self.request_cap:
                return 429, b'{"error":"request_cap"}', 'application/json'
            index = len(self.calls)
            call = dict(dispatch_id=uuid.uuid4().hex, task_id=task_id, arm=arm, attempt=index + 1, role='main',
                        evidence_kind='fixture', input_tokens=None, output_tokens=None, reasoning_tokens=None,
                        cached_input_tokens=None, reasoning_semantics='unknown', cost_usd=None, tokenizer=None,
                        started_at=time.time())
            self.calls.append(call)
            self.traces.append({'dispatch_id': call['dispatch_id'], 'request': body})
        message = {'role': 'assistant', 'content': 'Scripted long-horizon step; no inference.'}
        finish = 'stop'
        if index < len(self.steps):
            name, args = self.steps[index]
            message['tool_calls'] = [dict(index=0, id='fx_%d' % index, type='function',
                                          function=dict(name=name, arguments=json.dumps(args)))]
            finish = 'tool_calls'
        else:
            message['content'] = 'Done: reference applied and tests run.'
        chunks = [dict(id=call['dispatch_id'], object='chat.completion.chunk', created=1, model='fixture',
                       choices=[dict(index=0, delta=message, finish_reason=None)]),
                  dict(id=call['dispatch_id'], object='chat.completion.chunk', created=1, model='fixture',
                       choices=[dict(index=0, delta={}, finish_reason=finish)])]
        if body.get('stream'):
            raw = (''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n').encode()
            mime = 'text/event-stream'
        else:
            raw = json.dumps(dict(id=call['dispatch_id'], object='chat.completion', created=1, model='fixture',
                                  choices=[dict(index=0, message=message, finish_reason=finish)])).encode()
            mime = 'application/json'
        call['finished_at'] = time.time(); call['status'] = 200
        self.traces[-1]['response'] = raw.decode()
        return 200, raw, mime


def plan(tasks, arms, repeats, seed):
    rng = random.Random(seed); out = []
    for r in range(repeats):
        for t in tasks:
            order = list(arms); rng.shuffle(order)
            for a in order:
                pair = f"{t['id']}-r{r}"
                out.append(dict(episode_id=f'{pair}-{a}', pair_id=pair, task_id=t['id'], arm=a))
    return out


def main(argv=None):
    from bench.evaluation.report import summarize
    from bench.evaluation.live import validate_live, create_allocation
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', choices=['fixture', 'live'], default='fixture')
    ap.add_argument('--config', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=1)
    ap.add_argument('--seed', type=int, default=9107)
    ap.add_argument('--tasks', nargs='*')
    ap.add_argument('--arms', nargs='*')
    args = ap.parse_args(argv)
    tasks = [t for t in load_tasks() if not args.tasks or t['id'] in args.tasks]
    config = None
    if args.mode == 'live':
        if args.config is None: ap.error('--config required for live')
        config = json.loads(args.config.read_text()); validate_live(config)
    arms = args.arms or (list(config.get('arms', base.ARMS)) if config else ['baseline-direct'])
    assignments = plan(tasks, arms, args.repeats, args.seed)
    os.umask(0o077); args.out.mkdir(parents=True, exist_ok=False)
    if config: create_allocation(config)
    settings = dict(SETTINGS)
    if config: settings['context'] = config['context_limit']
    manifest = dict(version=1, kind='longhorizon', evidence_kind=args.mode, task_pack_sha256=fingerprint(),
                    image=base.IMAGE, settings=settings, arms=arms, repeats=args.repeats, seed=args.seed,
                    assignments=assignments,
                    configuration_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest() if config else None)
    base.write(args.out / 'manifest.json', manifest)
    rows = []; budget = {'count': 0, 'reserved': Decimal('0'), 'lock': threading.Lock()}
    byid = {t['id']: t for t in tasks}
    for a in assignments:
        t = byid[a['task_id']]
        try:
            row = base.run_episode(t, a['arm'], args.out / a['episode_id'], settings, live_config=config,
                                   budget=budget, seed_workspace=seeder(t), verifier=verifier(t),
                                   fixture_meter=(lambda t=t: ScriptedLongMeter(t, settings['request_cap']))
                                   if not config else None)
        except Exception as exc:
            row = dict(success=False, calls=[], collection_complete=False,
                       failure='orchestration_' + type(exc).__name__ + ':' + str(exc)[:200])
        row.update(a); rows.append(row)
        base.write(args.out / 'outcomes.json', rows)
        v = row.get('verifier') or {}
        usd = sum(float(c.get('cost_usd') or 0) for c in row.get('calls', []))
        print(a['episode_id'], 'PASS' if row['success'] else 'FAIL', row.get('failure'),
              f"{v.get('passed')}/{v.get('total')}", 'usd=%.4f' % usd, 'n=%d' % len(row.get('calls', [])), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
