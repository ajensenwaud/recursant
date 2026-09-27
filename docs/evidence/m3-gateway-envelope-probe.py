"""Synthetic HTTP regression using metadata shape from saved GLM response.
Not replay of real inference: provider/interpreter answers remain fixtures.
"""
import json
import sys
import time
sys.path.insert(0, '/src/tests/integration')
from test_gateway_context import GatewayContextTests, ContextSink  # pyright: ignore[reportMissingImports]

saved = json.load(open('/saved.json'))['records'][0]['response']
root_extra = {k: v for k, v in saved.items() if k not in ('choices','id','created','model','object','usage')}
choice_extra = {k: v for k, v in saved['choices'][0].items() if k not in ('message','index','finish_reason')}
message_extra = {k: v for k, v in saved['choices'][0]['message'].items() if k not in ('role','content')}
class EnvelopeSink(ContextSink):
    def do_POST(self):
        real = self.wfile
        class Writer:
            def write(self, data):
                try:
                    value = json.loads(data)
                    if isinstance(value, dict) and 'choices' in value:
                        value.update(root_extra)
                        for choice in value['choices']:
                            choice.update(choice_extra)
                            choice['message'].update(message_extra)
                        data = json.dumps(value).encode()
                except (ValueError, UnicodeError):
                    pass
                return real.write(data)
            def __getattr__(self, key):
                return getattr(real, key)
        self.wfile = Writer()
        try:
            super().do_POST()
        finally:
            self.wfile = real

t = GatewayContextTests()
def configure(config, sink):
    t.configure(config, sink)
    sink.RequestHandlerClass = EnvelopeSink
with t.router(configure) as (port, sink):
    scope = t.open_scope(port)
    history = [{'role': 'user', 'content': 'start'}]
    t.turn(port, scope, 1, history)
    # Hermes normalizes absent optional fields out of replayable messages.
    history[-1] = {k: history[-1][k] for k in ('role','content')}
    assert t.ingest(port, t.event(scope, 1, 1)) == 202
    time.sleep(.25)  # fixture synchronization, not measured asynchronous readiness
    history.append({'role': 'user', 'content': 'continue'})
    t.turn(port, scope, 2, history)
    actual = sink.seen[-1][2]['model']
    print(json.dumps({'provider': 'synthetic; stored GLM metadata shape only',
                      'expected': 'physical', 'actual': actual}), flush=True)
    assert actual == 'physical', 'Known inert provider metadata permanently disabled safe selection'
