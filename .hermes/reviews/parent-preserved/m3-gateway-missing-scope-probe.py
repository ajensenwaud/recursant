"""Adversarial loopback regression; synthetic provider and test credentials only."""
import json
import sys
import time
sys.path.insert(0, '/src/tests/integration')
from test_gateway_context import GatewayContextTests, ContextSink  # pyright: ignore[reportMissingImports]

t = GatewayContextTests()
def configure(config, sink):
    t.configure(config, sink)
    sink.RequestHandlerClass = ContextSink

with t.router(configure) as (port, sink):
    scope = t.open_scope(port)
    history = [{'role': 'user', 'content': 'start'}]
    t.turn(port, scope, 1, history)
    assert t.ingest(port, t.event(scope, 1, 1)) == 202
    # Fixture synchronization only; not a latency/readiness measurement.
    time.sleep(.25)
    history.append({'role': 'user', 'content': 'continue'})
    sink.tool_response = True
    t.turn(port, scope, 2, history)
    owner = sink.seen[-1][2]['model']
    assert owner == 'physical', owner
    sink.tool_response = False
    history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'fixture tool output'})
    headers = t.headers(scope, 3)
    del headers['X-Recursant-generation']
    del headers['X-Recursant-branch']
    code, _, _ = t.request(port, headers=headers, body={
        'model': 'auto', 'messages': history, 'max_tokens': 128})
    actual = sink.seen[-1][2]['model']
    print(json.dumps({'provider': 'synthetic loopback', 'owner': owner,
                      'next_status': code, 'next_model': actual}), flush=True)
    assert code in (400, 403, 409) or actual == owner, 'Lost scope bypassed mandatory model pin'
