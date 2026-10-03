"""Counterfactual pairs for the efficiency model (phase 3 of docs/proposals/ml-guided-routing.md).

Every recorded request that gpt-4.1 served is resent unchanged to a cheaper model (model
swapped, non-streaming, no routing); the cheaper model's move is recorded next to gpt-4.1's
recorded move. Cheaper than live shadow dispatch: the gpt-4.1 half already exists, so only
the cheaper call is paid.

Excluded: steps already paired (bench/efficiency/features.py PAIR_FILES) and the PII tasks
(their requests hold planted personal data; the router would keep them private).
Steps are taken round-robin across tasks (seeded), so a cap reached early still covers
every task. Resumable: keys already in OUT are skipped. Hard USD cap on provider usage.cost
plus the in-flight reserve.
usage: OPENROUTER_API_KEY=... python3 -m bench.efficiency.replay --model openai/gpt-4.1-mini \\
           --cap 3.00 --out .hermes/runtime/m3-live/mini-counterfactual-e1.jsonl"""
import argparse, collections, glob, json, os, random, re, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bench.efficiency.features import LIVE, PAIR_FILES

RUNS = ['final-d', 'lh1b', 'pilot-1', 'pilot-2', 'pilot-3', 'jev-check', 'interp-check', 'ma1-pilot',
        'ma1-smoke-fb67154', 'ma1-main', 'ma1-main2', 'ma1-main3', 'ma1-sig', 'ma1-localcost', 'ma1-localthink']
BIG = 'openai/gpt-4.1'


def served(resp):
    m = re.search(r'"model":\s*"([^"]+)"', resp if isinstance(resp, str) else json.dumps(resp or {}))
    return m.group(1) if m else None


def recorded_action(raw):
    """Tool calls and text from a recorded SSE (or JSON) response."""
    if not isinstance(raw, str): raw = json.dumps(raw or {})
    calls, text = {}, ''
    if raw.lstrip().startswith('{'):
        try:
            msg = json.loads(raw)['choices'][0]['message']
            return [{'name': c['function']['name'], 'arguments': c['function'].get('arguments')} for c in msg.get('tool_calls') or []], msg.get('content') or ''
        except (ValueError, KeyError, IndexError):
            return [], ''
    for line in raw.split('\n'):
        if not line.startswith('data: {'): continue
        try: o = json.loads(line[6:])
        except ValueError: continue
        for ch in o.get('choices', []):
            d = ch.get('delta', {})
            text += d.get('content') or ''
            for tc in d.get('tool_calls') or []:
                c = calls.setdefault(tc.get('index', 0), {'name': '', 'arguments': ''})
                f = tc.get('function') or {}
                c['name'] += f.get('name') or ''; c['arguments'] += f.get('arguments') or ''
    return [calls[k] for k in sorted(calls)], text


def target(call):
    try: a = json.loads(call.get('arguments') or '{}')
    except (ValueError, TypeError): a = {}
    if not isinstance(a, dict): return None, None
    for k in ('path', 'file_path', 'pattern', 'command', 'code'):
        if isinstance(a.get(k), str): return k, ' '.join(a[k].split())[:400]
    if call['name'] == 'delegate_task': return 'tasks', len(a.get('tasks') or [a])
    return None, None


def candidates():
    done = set()
    for path, _ in PAIR_FILES:
        p = LIVE / path
        if p.exists():
            for line in open(p): r = json.loads(line); done.add((r['episode'], int(r['index'])))
    by_task = collections.defaultdict(list)
    for run in RUNS:
        for f in sorted(glob.glob(str(LIVE / run / '*/traces.private.json'))):
            episode = Path(f).parent.name
            task = re.sub(r'-r\d+-.*$', '', episode)
            if '-pii-' in task: continue
            for i, t in enumerate(json.load(open(f))):
                if served(t.get('response')) == BIG and (episode, i) not in done:
                    by_task[task].append((run, episode, i))
    rng = random.Random(20261003)
    for v in by_task.values(): rng.shuffle(v)
    order, tasks = [], sorted(by_task)
    while any(by_task.values()):
        for t in tasks:
            if by_task[t]: order.append(by_task[t].pop())
    return order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True); ap.add_argument('--cap', type=float, required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--reserve', type=float, default=0.03, help='USD held per in-flight call')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    order = candidates()
    done = set()
    if os.path.exists(a.out):
        for line in open(a.out): r = json.loads(line); done.add((r['run'], r['episode'], r['index']))
    todo = [c for c in order if c not in done]
    print('%d candidate steps over %d tasks; %d already in %s' % (len(order), len({re.sub(r"-r\d+-.*$", "", e) for _, e, _ in order}), len(done), a.out))
    if a.dry_run: return
    spent = sum(json.loads(l).get('cost') or 0 for l in open(a.out)) if os.path.exists(a.out) else 0.0
    lock, state = threading.Lock(), {'spent': spent, 'inflight': 0, 'stop': False}
    key = os.environ['OPENROUTER_API_KEY']
    out = open(a.out, 'a')
    cache = {}

    def trace(run, ep):
        with lock:
            if (run, ep) not in cache: cache[(run, ep)] = json.load(open(LIVE / run / ep / 'traces.private.json'))
            return cache[(run, ep)]

    def one(c):
        run, ep, i = c
        with lock:
            if state['stop'] or state['spent'] + (state['inflight'] + 1) * a.reserve > a.cap:
                state['stop'] = True; return
            state['inflight'] += 1
        try:
            t = trace(run, ep)[i]
            body = t['request'] if isinstance(t['request'], dict) else json.loads(t['request'])
            big_calls, _ = recorded_action(t['response'])
            rec = dict(run=run, episode=ep, index=i, group='replay_e1', small_model=a.model,
                       big=[{'name': x['name'], 'target': target(x)} for x in big_calls], big_final=not big_calls)
            b = dict(body, model=a.model, stream=False, provider={'allow_fallbacks': False})
            b.pop('stream_options', None)
            req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(b).encode(),
                                         headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
            start = time.time()
            try:
                with urllib.request.urlopen(req, timeout=180) as resp: ans = json.loads(resp.read())
                cost = float((ans.get('usage') or {}).get('cost') or 0)
                msg = ans['choices'][0]['message']
                small = [{'name': x['function']['name'], 'arguments': x['function'].get('arguments')} for x in msg.get('tool_calls') or []]
                rec.update(cost=cost, secs=round(time.time() - start, 1), mini=[{'name': x['name'], 'target': target(x)} for x in small],
                           mini_final=not small)
            except Exception as e:   # unknown cost on failure: keep the reserve as spent
                cost = a.reserve; rec.update(error=type(e).__name__, cost=None, cost_assumed=a.reserve)
            with lock:
                state['spent'] += cost; out.write(json.dumps(rec) + '\n'); out.flush()
        finally:
            with lock: state['inflight'] -= 1

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, todo))
    n = sum(1 for _ in open(a.out))
    print('rows %d, spent US$%.4f (cap %.2f)%s' % (n, state['spent'], a.cap, ', cap reached' if state['stop'] else ''))


if __name__ == '__main__':
    main()
