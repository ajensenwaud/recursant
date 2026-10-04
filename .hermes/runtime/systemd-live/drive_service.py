"""Run real Hermes workloads through an INSTALLED Recursant service (systemd), not a router
the harness starts itself. Each episode uses the pinned Hermes image in the standard sandbox
(network none; the bridge socket is the only way out). Every model request is forwarded to
the service at RECURSANT_URL with the client key from RECURSANT_API_KEY; the response and the
router's decision headers are recorded. Tasks are graded by their hidden tests.

usage: RECURSANT_URL=http://127.0.0.1:8080/v1 RECURSANT_API_KEY=... python3 drive_service.py OUT [task ...]
"""
import json, os, sys, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from bench import taskpack
from bench.evaluation import run as base
from bench.evaluation.tasks import TASKS as EVAL_TASKS
from bench.multiagent import run as ma

URL, KEY = os.environ['RECURSANT_URL'].rstrip('/'), os.environ['RECURSANT_API_KEY']


def usage_of(raw, mime):
    """Provider usage (incl. OpenRouter usage.cost) from a JSON body or the SSE usage tail."""
    try:
        if 'event-stream' not in mime:
            return json.loads(raw).get('usage') or {}
        found = {}
        for line in raw.decode(errors='replace').splitlines():
            if line.startswith('data: {'):
                chunk = json.loads(line[6:])
                if chunk.get('usage'): found = chunk['usage']
        return found
    except (ValueError, AttributeError):
        return {}


class ServiceMeter:
    """Bridge endpoint: forwards chat completions to the installed service, records each call."""
    def __init__(self, request_cap):
        self.request_cap, self.calls, self.traces, self.context_events = request_cap, [], [], []
        self.lock = threading.Lock()

    def handle(self, path, body, headers):
        if path == '/v1/context/open':
            return 201, json.dumps(dict(body, generation=uuid.uuid4().hex)).encode(), 'application/json'
        return (202, b'{}', 'application/json') if path.startswith('/v1/context') else (404, b'{}', 'application/json')

    def dispatch(self, body, task_id, arm):
        with self.lock:
            if len(self.calls) >= self.request_cap:
                return 429, b'{"error":"request_cap"}', 'application/json'
            call = dict(dispatch_id=uuid.uuid4().hex, task_id=task_id, arm=arm, attempt=len(self.calls) + 1,
                        requested=body.get('model'), messages=len(body.get('messages') or []), started_at=time.time())
            self.calls.append(call)
        req = urllib.request.Request(URL + '/chat/completions', data=json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                status, raw, headers = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            status, raw, headers = e.code, e.read(), e.headers
        except OSError as e:
            status, raw, headers = 502, b'{"error":{"message":"service unreachable"}}', {}
            call['transport_error'] = type(e).__name__
        mime = headers.get('Content-Type', 'application/json')
        u = usage_of(raw, mime)
        call.update(status=status, finished_at=time.time(), model=headers.get('X-Recursant-Model'),
                    decision=headers.get('X-Recursant-Decision'), chosen=headers.get('X-Recursant-Chosen'),
                    est_cost=headers.get('X-Recursant-Cost-USD'), routing_us=headers.get('X-Recursant-Routing-Us'),
                    prompt_tokens=u.get('prompt_tokens'), completion_tokens=u.get('completion_tokens'),
                    cached_tokens=(u.get('prompt_tokens_details') or {}).get('cached_tokens'), cost_usd=u.get('cost'))
        with self.lock:
            self.traces.append({'dispatch_id': call['dispatch_id'], 'request': body})
        return status, raw, mime


def episodes(names):
    single = dict(base.SETTINGS, model='auto', turns=30, deadline_s=900, context=131072, request_cap=60, integration='none')
    multi = dict(ma.SETTINGS, model='auto', integration='none', request_cap=120, deadline_s=1500)
    packs = {t['id']: t for t in ma.load_tasks()}
    for name in names:
        if name in packs:
            t = packs[name]
            yield t, multi, taskpack.seeder(t), taskpack.verifier(t)
        else:
            yield next(t for t in EVAL_TASKS if t['id'] == name), single, None, None


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or ['ledger-v1', 'intervals-v1', 'dag-v1', 'statkit-delegate', 'auditkit-pii-delegate']
    for task, settings, seed, verify in episodes(names):
        meter = ServiceMeter(settings['request_cap'])
        t0 = time.time()
        row = base.run_episode(task, 'systemd', out / task['id'], settings, seed_workspace=seed, verifier=verify,
                               fixture_meter=lambda: meter)
        calls = meter.calls
        line = dict(task=task['id'], success=row['success'], seconds=round(time.time() - t0), requests=len(calls),
                    models={m: sum(1 for c in calls if c.get('model') == m) for m in sorted({c.get('model') or '?' for c in calls})},
                    decisions={d: sum(1 for c in calls if c.get('decision') == d) for d in sorted({c.get('decision') or '?' for c in calls})},
                    errors=sum(1 for c in calls if c.get('status') != 200),
                    cost_usd=round(sum(c.get('cost_usd') or 0 for c in calls), 4))
        print(json.dumps(line), flush=True)
        with open(out / 'summary.jsonl', 'a') as f: f.write(json.dumps(line) + '\n')


if __name__ == '__main__':
    main()
