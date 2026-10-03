"""Ask every single-query item to one model and record the answer, tokens and billed cost.
Public models go through OpenRouter (hard USD cap on usage.cost plus in-flight reserve);
the private GLM goes to gx10 (no cost). Resumable: ids already in OUT are skipped.

The answer-format instruction is a system message, so the user message is exactly the
question a chat user would type (that is all the router's prompt classifier reads).
usage: OPENROUTER_API_KEY=... python3 -m bench.prompt.ask --model openai/gpt-4.1-mini --cap 2 \\
           --out .hermes/runtime/prompt/answers-mini.jsonl [--private-url http://gx10:8888/v1]"""
import argparse, json, os, random, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / '.hermes/runtime/prompt/single.jsonl'
SYSTEM = {
    'mc': "Answer the multiple-choice question. Think briefly if you need to, then end with a final line 'Answer: <letter>'.",
    'number': "Solve the problem. Show brief working, then end with a final line 'Answer: <number>'.",
    'code': 'Write a Python solution. Reply with one Python code block containing the complete function and any imports it needs.',
}


def messages(item):
    return [{'role': 'system', 'content': SYSTEM[item['kind']]}, {'role': 'user', 'content': item['question']}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--cap', type=float, default=0.0); ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--private-url'); ap.add_argument('--limit', type=int)
    ap.add_argument('--reserve', type=float, default=0.02); ap.add_argument('--shuffle', action='store_true')
    a = ap.parse_args()
    items = [json.loads(l) for l in open(ITEMS)]
    if a.limit: items = items[:a.limit]
    done = {json.loads(l)['id'] for l in open(a.out)} if os.path.exists(a.out) else set()
    spent = sum(json.loads(l).get('cost') or 0 for l in open(a.out)) if os.path.exists(a.out) else 0.0
    todo = [i for i in items if i['id'] not in done]
    if a.shuffle: random.Random(20261003).shuffle(todo)   # a partial run is a random sample
    print('%d items, %d done, %d to ask; spent so far US$%.4f' % (len(items), len(done), len(todo), spent), flush=True)
    private = bool(a.private_url)
    url = (a.private_url.rstrip('/') if private else 'https://openrouter.ai/api/v1') + '/chat/completions'
    headers = {'Content-Type': 'application/json'}
    if not private: headers['Authorization'] = 'Bearer ' + os.environ['OPENROUTER_API_KEY']
    lock, state = threading.Lock(), {'spent': spent, 'inflight': 0, 'stop': False}
    out = open(a.out, 'a')

    def one(item):
        with lock:
            if not private and (state['stop'] or state['spent'] + (state['inflight'] + 1) * a.reserve > a.cap):
                state['stop'] = True; return
            state['inflight'] += 1
        rec = {'id': item['id'], 'model': a.model}
        try:
            body = {'model': a.model, 'messages': messages(item), 'max_tokens': 1024, 'temperature': 0}
            if not private: body['provider'] = {'allow_fallbacks': False}
            else: body['chat_template_kwargs'] = {'enable_thinking': False}   # fast mode for single questions
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
            start = time.time()
            try:
                with urllib.request.urlopen(req, timeout=600) as resp: ans = json.loads(resp.read())
                u = ans.get('usage') or {}
                msg = ans['choices'][0]['message']
                rec.update(text=msg.get('content') or '', secs=round(time.time() - start, 2),
                           prompt_tokens=u.get('prompt_tokens'), completion_tokens=u.get('completion_tokens'),
                           cost=0.0 if private else float(u.get('cost') or 0))
            except Exception as e:
                rec.update(error=type(e).__name__, cost=None if private else a.reserve)
            with lock:
                state['spent'] += rec.get('cost') or 0
                out.write(json.dumps(rec) + '\n'); out.flush()
        finally:
            with lock: state['inflight'] -= 1

    with ThreadPoolExecutor(a.workers) as ex: list(ex.map(one, todo))
    print('spent US$%.4f%s' % (state['spent'], ' (cap reached)' if state['stop'] else ''))


if __name__ == '__main__':
    main()
