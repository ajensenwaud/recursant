"""Pinned real Hermes / real terminal, SYNTHETIC loopback provider, no inference.
Run only in the isolated read-only --network none image described in evidence.
Raw request/event content lives in memory or ephemeral container tmpfs only.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SHA = 'd0288be5b3330d2442e3907185b8e9d0958297bb'


def main():
    os.umask(0o077)
    git = ['git', '-c', 'safe.directory=/opt/hermes', '-C', '/opt/hermes']
    assert subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip() == SHA
    assert not subprocess.check_output(git + ['status', '--porcelain'], text=True)
    assert os.getuid() != 0
    for key in ('HOME', 'HERMES_HOME'):
        path = Path(os.environ[key])
        assert not path.exists()
        path.mkdir(parents=True)
    content_enabled = '--content' in sys.argv
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind('/tmp/context.sock'); receiver.setblocking(False)
    events = []; requests = []; checks = []; failures = []

    def drain():
        while True:
            try:
                events.append(json.loads(receiver.recv(32768)))
            except BlockingIOError:
                break

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/show':
                    # Hermes' model-capability discovery, not an inference request.
                    self.send_error(404, 'synthetic provider has no Ollama metadata')
                    return
                requests.append(dict(self.headers))
                assert self.path == '/v1/chat/completions'
                assert body['model'] == 'synthetic-fixture'
                first = len(requests) == 1
                if not first:
                    assert checks == [True], 'consumer proof absent before next wire request'
                    tool = [m for m in body['messages'] if m.get('role') == 'tool']
                    assert tool, 'no real terminal response'
                    terminal_result = json.loads(tool[-1]['content'])
                    assert terminal_result.get('exit_code') == 0
                    assert terminal_result.get('output') == 'M3_TERMINAL_OK'
                message = {'role': 'assistant', 'content': 'synthetic plan' if first else 'SYNTHETIC_DONE',
                           'reasoning_content': 'synthetic exposed reasoning'}
                if first:
                    message['tool_calls'] = [{'id': 'probe_call', 'type': 'function',
                        'function': {'name': 'terminal', 'arguments': json.dumps({'command': 'printf M3_TERMINAL_OK'})}}]
                finish = 'tool_calls' if first else 'stop'
                self.send_response(200)
                if body.get('stream'):
                    self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                    delta = dict(message)
                    if first:
                        delta['tool_calls'][0]['index'] = 0
                    chunks = [dict(id='synthetic', object='chat.completion.chunk', created=1,
                                   model='synthetic-fixture', choices=[dict(index=0, delta=delta, finish_reason=None)]),
                              dict(id='synthetic', object='chat.completion.chunk', created=1,
                                   model='synthetic-fixture', choices=[dict(index=0, delta={}, finish_reason=finish)],
                                   usage=dict(prompt_tokens=1, completion_tokens=1, total_tokens=2))]
                    for chunk in chunks:
                        self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                else:
                    self.send_header('Content-Type', 'application/json'); self.end_headers()
                    self.wfile.write(json.dumps(dict(id='synthetic', object='chat.completion', created=1,
                        model='synthetic-fixture', choices=[dict(index=0, message=message, finish_reason=finish)],
                        usage=dict(prompt_tokens=1, completion_tokens=1, total_tokens=2))).encode())
            except Exception as exc:
                print(json.dumps({'probe_failure': repr(exc), 'path': self.path,
                                  'prior_checks': checks, 'hook_failures': failures}), flush=True)
                os._exit(1)

    server = HTTPServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f'http://127.0.0.1:{server.server_port}/v1'
    sys.path[:0] = ['/opt/hermes', '/probe']
    from run_agent import AIAgent
    from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager
    from context_adapter import install
    manager = get_plugin_manager()
    manager.discover_and_load()
    ctx = PluginContext(PluginManifest(name='recursant-context-probe'), manager)
    adapter = install(ctx, enabled=True, endpoint=endpoint)
    adapter.configure_sink('/tmp/context.sock')
    adapter.content_enabled = content_enabled

    def before_request(**kwargs):
        drain()
        if requests:
            try:
                response = next(e for e in events if e['kind'] == 'response')
                tool = next(e for e in events if e['kind'] == 'tool')
                assert response['routing_eligible'] and tool['routing_eligible']
                assert response['attempt'] == tool['attempt']
                assert tool['status'] == 'ok'
                if content_enabled:
                    assert response['text']['assistant_plan'] == 'synthetic plan'
                    assert response['text']['reasoning'] == 'synthetic exposed reasoning'
                    assert 'M3_TERMINAL_OK' in tool['text']['tool_result']
                else:
                    assert all('text' not in e for e in events)
                checks.append(True)
            except Exception as exc:
                failures.append('before request: ' + repr(exc) + ' metadata=' + repr([
                    {k: v for k, v in e.items() if k != 'text'} for e in events]))
    ctx.register_hook('pre_api_request', before_request)
    agent = AIAgent(model='synthetic-fixture', base_url=endpoint, api_key='synthetic-not-a-secret',
                    provider='custom', api_mode='chat_completions', enabled_toolsets=['terminal'],
                    max_iterations=3, max_tokens=256, run_budget_seconds=60, quiet_mode=True,
                    session_id='m3-synthetic-session', skip_context_files=True, skip_memory=True,
                    skip_background_review=True, cwd='/tmp', save_trajectories=False)
    try:
        result = agent.run_conversation('Execute the synthetic terminal fixture.', task_id='m3-synthetic-task')
        drain()
        assert not failures, failures
        assert len(requests) == 2, len(requests)
        assert checks == [True], checks
        responses = [e for e in events if e['kind'] == 'response']
        assert len(responses) == 2
        for headers, event in zip(requests, responses):
            headers = {k.lower(): v for k, v in headers.items()}
            for field in ('task_id', 'session_id', 'turn_id', 'api_request_id', 'attempt'):
                assert headers['x-recursant-' + field.replace('_', '-')] == event[field]
        assert responses[0]['attempt'] != responses[1]['attempt']
        assert result.get('completed') is True
        assert result.get('final_response') == 'SYNTHETIC_DONE'
        assert not any(result.get(k) for k in ('failed', 'partial', 'interrupted'))
        assert adapter.dropped == 0
        print(json.dumps(dict(provider='SYNTHETIC scripted loopback; no semantic inference',
            hermes_sha=SHA, requests=len(requests), responses=len(responses),
            tool_events=sum(e['kind'] == 'tool' for e in events), content_enabled=content_enabled,
            headers_exact=True, terminal_executed=True, consumer_ready_before_next_dispatch=True,
            adapter_dropped=adapter.dropped, physical_attempt_uniqueness='unproven',
            stream_association='unsupported', upstream_gaps='unknown'), sort_keys=True))
    finally:
        agent.close(); adapter.close(); receiver.close(); server.shutdown()


if __name__ == '__main__':
    main()
