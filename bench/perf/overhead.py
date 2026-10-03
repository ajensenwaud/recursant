"""Routing overhead: the same agent requests sent straight to a stub provider and through
Recursant to that stub, so the difference is what the router adds. No model calls.

The stub answers instantly from a thread pool. Bodies are synthetic agent conversations
(system prompt, tool schemas, alternating tool calls and tool results) at three sizes.
The router runs the starter config with sessions, signals, the prompt classifier,
compliance and cost selection switched on, in --test-mode (plain HTTP to the stub).
usage: python3 bench/perf/overhead.py ROUTER_BINARY CONFIG [--requests 2000] [--concurrency 16]"""
import argparse, http.client, http.server, json, os, socket, socketserver, statistics, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

ANSWER = json.dumps({'id': 'x', 'object': 'chat.completion', 'model': 'm', 'choices': [
    {'index': 0, 'message': {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call-next', 'type': 'function', 'function': {'name': 'terminal', 'arguments': '{"command":"ls"}'}}]},
     'finish_reason': 'tool_calls'}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}}).encode()


class Stub(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'; disable_nagle_algorithm = True   # one write per reply, no delayed-ACK stall
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(ANSWER))); self.end_headers(); self.wfile.write(ANSWER)
    def log_message(self, *a): pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True; request_queue_size = 256


TOOLS = [{'type': 'function', 'function': {'name': n, 'description': 'tool ' + n, 'parameters': {
    'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command'], 'additionalProperties': False}}}
    for n in ('terminal', 'read_file', 'write_file', 'patch', 'search_files')]


def conversation(target_bytes, salt):
    msgs = [{'role': 'system', 'content': 'You are a coding agent. ' * 40},
            {'role': 'user', 'content': 'Fix the failing tests in the repository (run %d).' % salt}]
    i = 0
    while len(json.dumps(msgs)) < target_bytes:
        i += 1
        msgs.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call-%d' % i, 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"command":"cat src/m%d.py"}' % i}}]})
        msgs.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': ('def f%d(x):\n    return x + %d\n' % (i, i)) * 40})
    return {'model': 'auto', 'messages': msgs, 'tools': TOOLS, 'tool_choice': 'auto', 'max_tokens': 1024}


def run(port, bodies, concurrency, headers):
    local = threading.local()
    def one(body):
        if not hasattr(local, 'c'):
            local.c = http.client.HTTPConnection('127.0.0.1', port, timeout=30); local.c.connect()
            local.c.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # no Nagle/delayed-ACK stall
        t = time.perf_counter()
        local.c.request('POST', '/v1/chat/completions', body, headers)
        r = local.c.getresponse(); r.read()
        if r.status != 200: raise SystemExit('status %d (router log: /tmp/perf-router.log)' % r.status)
        return (time.perf_counter() - t) * 1e3, r.getheader('X-Recursant-Routing-Us')
    start = time.perf_counter()
    with ThreadPoolExecutor(concurrency) as ex: out = list(ex.map(one, bodies))
    return out, len(bodies) / (time.perf_counter() - start)


def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('binary'); ap.add_argument('config')
    ap.add_argument('--requests', type=int, default=2000); ap.add_argument('--concurrency', type=int, default=16)
    a = ap.parse_args()
    stub = Server(('127.0.0.1', 9998), Stub); threading.Thread(target=stub.serve_forever, daemon=True).start()
    cfg = json.load(open(a.config))
    for p in cfg['providers']: p['url'] = 'http://127.0.0.1:9998/v1'
    cfg.setdefault('limits', {}).update(max_connections=256, max_body_bytes=8 << 20)
    cfg['context'].pop('budgets', None)
    path = '/tmp/perf-config.json'; json.dump(cfg, open(path, 'w')); os.chmod(path, 0o600)
    env = dict(os.environ, RECURSANT_API_KEY='client-key', OPENROUTER_API_KEY='public-key', RECURSANT_SOURCE_KEY='source-key')
    router = subprocess.Popen([a.binary, 'serve', path, '--test-mode'], env=env, stderr=open('/tmp/perf-router.log', 'w'))
    time.sleep(1)
    port = cfg['listen']['port']
    auth = {'Authorization': 'Bearer client-key', 'Content-Type': 'application/json'}
    print('requests %d, concurrency %d, %d CPUs' % (a.requests, a.concurrency, os.cpu_count()))
    print('%-8s %10s %10s %10s %10s %12s %10s' % ('body', 'direct p50', 'router p50', 'added p50', 'added p99', 'router req/s', 'decide p50'))
    try:
        for size in [int(x) << 10 for x in os.environ.get('PERF_SIZES', '4,64,512').split(',')]:
            # Each request is its own conversation (a fresh session), so the router does
            # session lookup, compliance scan, signals, cost and selection every time.
            bodies = [json.dumps(conversation(size, i)) for i in range(a.requests)]
            run(9998, bodies[:200], a.concurrency, auth); run(port, bodies[:200], a.concurrency, auth)   # warm-up
            direct, _ = run(9998, bodies, a.concurrency, auth)
            routed, rps = run(port, bodies, a.concurrency, auth)
            d = [x for x, _ in direct]; r = [x for x, _ in routed]; us = [int(h) for _, h in routed if h]
            print('%-8s %8.2fms %8.2fms %8.2fms %8.2fms %12.0f %8dus' % (
                '%dKiB' % (size >> 10), pct(d, .5), pct(r, .5), pct(r, .5) - pct(d, .5), pct(r, .99) - pct(d, .99), rps,
                statistics.median(us) if us else -1))
    finally:
        router.terminate(); router.wait()


if __name__ == '__main__':
    main()
