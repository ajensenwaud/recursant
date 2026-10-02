"""Step features and labels for the efficiency model, from recorded traces and the
counterfactual pair files (.hermes/runtime/m3-live/*counterfactual*.jsonl).

Label: the cheaper model made the same next move (same tool) as gpt-4.1 on that step.
Features: only what the router can see when it decides (the request so far)."""
import ast, glob, json, math, re
from pathlib import Path

LIVE = Path(__file__).resolve().parents[2] / '.hermes/runtime/m3-live'
FAIL = re.compile(r'Traceback \(most recent call last\)|FAILED|ERROR:|Error:|AssertionError|"exit_code": [1-9]|"success": false|"error": "[^"]')
TOOLS = ['terminal', 'read_file', 'write_file', 'patch', 'search_files', 'execute_code', 'delegate_task']
_cache = {}


def traces(run, episode):
    key = (run, episode)
    if key not in _cache:
        p = LIVE / run / episode / 'traces.private.json'
        _cache[key] = json.load(open(p)) if p.exists() else None
    return _cache[key]


def recorded_move(response):
    """Tool names gpt-4.1 actually called (SSE or JSON response text)."""
    names = []
    if isinstance(response, str):
        for m in re.finditer(r'"name":\s*"([A-Za-z0-9_.-]+)"', response): names.append(m.group(1))
    return names


def request_of(t):
    r = t.get('request')
    return json.loads(r) if isinstance(r, str) else r


def features(req):
    msgs = req.get('messages', [])
    tool_msgs = [m for m in msgs if m.get('role') == 'tool']
    results = [m.get('content') if isinstance(m.get('content'), str) else '' for m in tool_msgs]
    calls = [c.get('function', {}).get('name') for m in msgs if m.get('role') == 'assistant' for c in (m.get('tool_calls') or [])]
    last = results[-1] if results else ''
    fails = [bool(FAIL.search(x[:8000])) for x in results[-3:]]
    run = 0
    for f in reversed([bool(FAIL.search(x[:8000])) for x in results]):
        if not f: break
        run += 1
    system = next((m.get('content') for m in msgs if m.get('role') == 'system'), '') or ''
    first_user = next((m.get('content') for m in msgs if m.get('role') == 'user'), '') or ''
    f = {
        'bias': 1.0,
        'last_failed': float(bool(fails and fails[-1])),
        'fails_in_last3': float(sum(fails)),
        'failure_run': float(min(run, 3)),
        'log_messages': math.log1p(len(msgs)),
        'log_tool_results': math.log1p(len(tool_msgs)),
        'log_last_len': math.log1p(len(last)),
        'subagent': float('subagent' in system.lower() or len(first_user) < 600 and 'delegat' in system.lower()),
        'repeat_last_call': float(len(calls) >= 2 and calls[-1] == calls[-2]),
        'no_tools_offered': float(not req.get('tools')),
    }
    lastcall = calls[-1] if calls else 'none'
    for t in TOOLS: f['last_call_' + t] = float(lastcall == t)
    return f


def pairs():
    """(features, label, group, meta) for every counterfactual pair whose step is found."""
    out = []
    for path, model in (('mini-counterfactual-ma2.jsonl', 'mini'), ('mini-counterfactual-helpers.jsonl', 'mini'), ('glm-counterfactual.jsonl', 'glm')):
        for line in open(LIVE / path):
            row = json.loads(line)
            lit = lambda v: ast.literal_eval(v) if isinstance(v, str) else v
            big = [c['name'] for c in lit(row['big']) or []]
            small = [c['name'] for c in lit(row['mini']) or []] if row.get('mini') is not None else None
            if small is None: continue
            found = None
            for run in ('ma1-main3', 'ma1-sig', 'ma1-localcost'):
                ts = traces(run, row['episode'])
                if not ts or int(row['index']) >= len(ts): continue
                t = ts[int(row['index'])]
                if recorded_move(t.get('response'))[:1] == big[:1]:
                    found = t; break
            if not found: continue
            same = (big[:1] == small[:1]) and (row.get('big_final') == row.get('mini_final'))
            meta = {'model': model, 'group': row['group'], 'old': row.get('old'), 'new': row.get('new'),
                    'big': big[:1], 'small': small[:1]}
            out.append((features(request_of(found)), float(same), row['episode'].rsplit('-r', 1)[0], meta))
    return out


if __name__ == '__main__':
    ps = pairs()
    print(len(ps), 'pairs matched;', sum(p[1] for p in ps), 'agree')
