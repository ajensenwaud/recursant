import json
import os
import subprocess
import unittest

BIN = os.environ['INTERPRETER_BIN']
STATE = dict(schema_version='trajectory.v1', input_revision='1', evidence_refs=['e1'],
             phase='planning', next_action='plan', difficulty_band='hard',
             progress_state='blocked', coverage='partial')
def response(state=None, finish='stop'):
    return json.dumps({'choices': [{'finish_reason': finish, 'message': {
        'role': 'assistant', 'content': json.dumps(STATE if state is None else state)}}]})

class Parser(unittest.TestCase):
    def check(self, text, valid):
        p = subprocess.run([BIN], input=text, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0 if valid else 1, p.stderr)
    def test_valid(self):
        self.check(response(), True)
    def test_schema_edges(self):
        for key in STATE:
            state = dict(STATE); del state[key]
            self.check(response(state), False)
        for refs in ([], ['e1']*17, [1], 'e1', None):
            self.check(response(dict(STATE, evidence_refs=refs)), False)
        state_text = json.dumps(STATE).replace('"phase":', '"phase":"unknown","phase":')
        outer = json.loads(response())
        outer['choices'][0]['message']['content'] = state_text
        self.check(json.dumps(outer), False)
        for field in ('tool_calls', 'function_call'):
            outer = json.loads(response()); outer['choices'][0]['message'][field] = []
            self.check(json.dumps(outer), False)
        self.check(response()[:-1], False)
        self.check(json.dumps({'choices': []}), False)
        self.check(json.dumps({'choices': json.loads(response())['choices']*2}), False)

    def test_rejections(self):
        for key, value in [('input_revision','2'), ('evidence_refs',['invented']),
                           ('evidence_refs',['e1','e1']), ('coverage','complete'),
                           ('policy', 'allow'), ('route','http://evil'), ('phase', True)]:
            with self.subTest(key=key, value=value):
                self.check(response(dict(STATE, **{key:value})), False)
        self.check(response(finish='length'), False)
        self.check(response().replace('"choices":', '"choices": [], "choices":'), False)
        self.check(response().replace('trajectory.v1', 'trajectory.v1\\u0000'), False)
        self.check('{} trailing', False)
        self.check('x'*65537, False)

import http.server
import threading
import time

class HTTP(unittest.TestCase):
    def run_case(self, body, status='0', delay=0.15, code=200):
        requests = []
        redirects = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                redirects.append(self.path)
                self.send_response(500); self.end_headers()
            def log_message(self, format, *args): pass
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                time.sleep(delay)
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                if code == 302: self.send_header('Location', '/must-not-follow')
                self.end_headers()
                try: self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError): pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = dict(os.environ, http_proxy='http://127.0.0.1:1', ALL_PROXY='http://127.0.0.1:1', NO_PROXY='')
            p = subprocess.run([BIN, f'http://127.0.0.1:{server.server_port}/v1/chat/completions', status],
                               capture_output=True, text=True, timeout=5, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(redirects, [])
            for request in requests:
                self.assertEqual(set(request), {'model','stream','max_tokens','messages'})
                self.assertEqual(request['max_tokens'], 4096)
                self.assertEqual(request['model'], 'fixture')
                data = json.loads(request['messages'][1]['content'])
                self.assertEqual(data['input_revision'], '1')
                self.assertEqual(data['segments'][0]['text'], 'test failed')
            if status not in ('cancel','shutdown'): self.assertTrue(requests)
        finally:
            server.shutdown(); server.server_close(); thread.join()
    def test_delayed_nonblocking_and_copied_input(self): self.run_case(response().encode())
    def test_http_revision_mismatch(self): self.run_case(response(dict(STATE,input_revision='2')).encode(), '1')
    def test_http_forbidden_fields(self): self.run_case(response(dict(STATE,policy='allow')).encode(), '1')
    def test_http_timeout(self): self.run_case(response().encode(), '2', delay=1.5)
    def test_http_overflow(self): self.run_case(b'x'*65537, '1')
    def test_http_no_redirect(self): self.run_case(b'', '1', code=302)
    def test_http_cancel(self): self.run_case(response().encode(), 'cancel', delay=1.5)
    def test_http_shutdown(self): self.run_case(response().encode(), 'shutdown', delay=1.5)

if __name__ == '__main__': unittest.main()
