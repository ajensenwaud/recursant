"""Executable contract: real pinned Hermes, scripted local HTTP only (NOT inference).
Run via run_hermes_physical_probe.sh; no raw payloads leave container tmpfs.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import socket
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

SHA = 'd0288be5b3330d2442e3907185b8e9d0958297bb'


class IngressContract(unittest.TestCase):
    def test_real_retry_invalidates_repeated_invocation(self):
        os.umask(0o077)
        self.assertNotEqual(os.getuid(), 0)
        self.assertNotIn('HERMES_YOLO_MODE', os.environ)
        git = ['git', '-c', 'safe.directory=/opt/hermes', '-C', '/opt/hermes']
        self.assertEqual(subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip(), SHA)
        self.assertFalse(subprocess.check_output(git + ['status', '--porcelain'], text=True))
        for key in ('HOME', 'HERMES_HOME'):
            p = Path(os.environ[key]); self.assertFalse(p.exists()); p.mkdir(parents=True)
        sys.path[:0] = ['/opt/hermes', '/probe']
        from run_agent import AIAgent
        from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager
        from context_adapter import install
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('physical_observer'), 'physical observer not implemented')
        from physical_observer import PhysicalObserver
        self.assertIsNotNone(importlib.util.find_spec('attempt_boundary'), 'C ingress boundary not implemented')
        from attempt_boundary import Boundary
        boundary = Boundary()
        sink = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sink.bind('/tmp/source-events.sock'); sink.setblocking(False)
        wire, errors, completed, tools = [], [], [], []
        probe = self

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    if self.path == '/api/show':
                        self.send_error(404); return
                    probe.assertEqual(self.path, '/v1/chat/completions')
                    probe.assertEqual(body['model'], 'synthetic-fixture')
                    probe.assertLess(len(wire), 4, 'bounded fixture request cap')
                    attempt = boundary.begin(self.headers)  # Exactly once per accepted physical HTTP request.
                    headers = {k.lower(): v for k, v in self.headers.items()}
                    # Explicit allowlist: never persist authorization, body or tool text.
                    wire.append({k: v for k, v in headers.items()
                                 if k.startswith('x-recursant-') or k == 'traceparent'})
                    if len(wire) == 1:
                        self.send_response(int(os.environ.get('PROBE_FAILURE_STATUS', '503')))
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Retry-After', '0'); self.end_headers()
                        self.wfile.write(b'{"error":{"message":"synthetic retry fixture","type":"server_error"}}')
                        boundary.finish(attempt, False)
                        return
                    first = len(wire) == 2
                    if not first:
                        tool_messages = [m for m in body['messages'] if m.get('role') == 'tool']
                        probe.assertTrue(tool_messages)
                        result = json.loads(tool_messages[-1]['content'])
                        probe.assertEqual(result['exit_code'], 0)
                        probe.assertEqual(result['output'], 'M3_PHYSICAL_OK')
                    message = dict(role='assistant', content='fixture plan' if first else 'FIXTURE_DONE')
                    if first:
                        message['tool_calls'] = [dict(id='physical_fixture_tool', type='function',
                            function=dict(name='terminal', arguments=json.dumps(dict(command='printf M3_PHYSICAL_OK'))))]
                    finish = 'tool_calls' if first else 'stop'
                    self.send_response(200)
                    if body.get('stream'):
                        self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                        if first:
                            message['tool_calls'][0]['index'] = 0
                        chunks = [dict(id='fixture', object='chat.completion.chunk', created=1,
                            model='synthetic-fixture', choices=[dict(index=0, delta=message, finish_reason=None)]),
                            dict(id='fixture', object='chat.completion.chunk', created=1, model='synthetic-fixture',
                            choices=[dict(index=0, delta={}, finish_reason=finish)],
                            usage=dict(prompt_tokens=1, completion_tokens=1, total_tokens=2))]
                        for chunk in chunks:
                            self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                        self.wfile.write(b'data: [DONE]\n\n')
                    else:
                        self.send_header('Content-Type', 'application/json'); self.end_headers()
                        self.wfile.write(json.dumps(dict(id='fixture', object='chat.completion', created=1,
                            model='synthetic-fixture', choices=[dict(index=0, message=message, finish_reason=finish)],
                            usage=dict(prompt_tokens=1, completion_tokens=1, total_tokens=2))).encode())
                    self.wfile.flush()
                    boundary.finish(attempt, True)
                except Exception as exc:
                    print(json.dumps({'fixture_failure': repr(exc)}), flush=True)
                    os._exit(1)

        server = HTTPServer(('127.0.0.1', 0), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoint = f'http://127.0.0.1:{server.server_port}/v1'
        manager = get_plugin_manager(); manager.discover_and_load()
        ctx = PluginContext(PluginManifest(name='recursant-physical-proof'), manager)
        adapter = install(ctx, enabled=True, endpoint=endpoint)
        adapter.configure_sink('/tmp/source-events.sock')
        fields = ('task_id', 'session_id', 'turn_id', 'api_request_id')
        ctx.register_hook('post_api_request', lambda **kw: completed.append({k: kw.get(k) for k in fields}))
        ctx.register_hook('post_tool_call', lambda **kw: tools.append({k: kw.get(k) for k in fields}))
        observer = PhysicalObserver()
        agent = AIAgent(model='synthetic-fixture', base_url=endpoint, api_key='synthetic-not-a-secret',
            provider='custom', api_mode='chat_completions', enabled_toolsets=['terminal'],
            max_iterations=3, max_tokens=256, run_budget_seconds=45, quiet_mode=True,
            session_id='physical:session', skip_context_files=True, skip_memory=True,
            skip_background_review=True, cwd='/tmp', save_trajectories=False)
        try:
            result = agent.run_conversation('Execute the scripted terminal fixture.', task_id='physical:task')
            observer.flush()  # Test/shutdown only; not an inference-lane barrier.
            self.assertTrue(result.get('completed'))
            self.assertEqual(result.get('final_response'), 'FIXTURE_DONE')
            self.assertEqual(len(wire), 3)
            self.assertEqual(len(completed), 2)
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0], completed[0])
            print(json.dumps({'wire': wire, 'relay_events': observer.events,
                              'intercepts': observer.intercepts}, sort_keys=True), flush=True)
            starts = [e for e in observer.events if e['name'] == 'openai.chat_completions'
                      and e['scope_category'] == 'start']
            roots = {i['root_uuid'] for i in observer.intercepts}
            self.assertEqual(len(roots), 1, 'this fixture has one session, not a general branch assumption')
            root = next(iter(roots))
            joins = {observer.relay.PropagationContext(e['uuid'], root).to_traceparent(): e for e in starts}
            self.assertEqual(len(joins), len(starts))
            for w in wire:
                if 'traceparent' not in w:
                    continue
                self.assertIn(w['traceparent'], joins)
                physical = [e for e in observer.events if e['uuid'] == joins[w['traceparent']]['uuid']]
                self.assertEqual(len(physical), 2, 'physical start and end required')
                self.assertEqual({e['scope_category'] for e in physical}, {'start', 'end'})
                for e in physical:
                    self.assertEqual(e['metadata']['api_request_id'], w['x-recursant-api-request-id'])
            # Keep the original Relay undercount as evidence; never manufacture its missing span.
            self.assertEqual(len(starts), 2)
            self.assertEqual(len(observer.intercepts), 2)
            self.assertNotIn('traceparent', wire[1])
            self.assertEqual(wire[0]['x-recursant-attempt'], wire[1]['x-recursant-attempt'])
            events = []
            while True:
                try:
                    events.append(json.loads(sink.recv(24577)))
                    self.assertLessEqual(len(events), 16)
                except BlockingIOError:
                    break
            responses = [e for e in events if e['kind']=='response']
            self.assertEqual(len(responses), 2)
            for event in responses:
                self.assertEqual(event['dropped'], 0)
                self.assertEqual(event['association'], 'exact')  # Invocation only in old adapter.
                self.assertFalse(event['physical_routing_eligible'])
                boundary.source(event)  # Real adapter datagram, not simulated callbacks.
            views = boundary.views()
            self.assertEqual(len(views), 3)
            self.assertEqual(len({v['id'] for v in views}), 3)
            self.assertEqual([v['physical_count'] for v in views], [2, 2, 1])
            self.assertTrue(all(v['count_known'] for v in views))
            self.assertEqual([v['ambiguous'] for v in views], [True, True, False])
            self.assertEqual([v['exact'] for v in views], [False, False, True])
            print(json.dumps(dict(result='INGRESS_CONTRACT_PASS', provider='SYNTHETIC; no semantic inference',
                hermes_sha=SHA, ingress_attempts=views, relay_physical_attempts=len(starts),
                real_source_datagrams=len(responses), source_before_next_dispatch='NOT PROVED',
                production_gateway_integration='NOT ENABLED', full_M3=False)), flush=True)
        finally:
            agent.close(); observer.close(); adapter.close(); server.shutdown(); server.server_close(); sink.close(); boundary.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
