"""Offline actual-gateway readiness audit. Synthetic providers, not quality evidence.
Run in existing dev image with RECURSANT_BIN and /src tests on PYTHONPATH.
Only the named positive-control case waits for advice; tool sleeps model work.
"""
import http.server
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/integration'))
import test_native_tools as native


class Sink(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.seen.append((self.path, dict(self.headers), body))
        interpreter = 'response_format' in body
        record = dict(kind='interpreter' if interpreter else 'chat', start=time.monotonic())
        self.server.records.append(record)
        if interpreter:
            data = json.loads(body['messages'][1]['content'])
            record.update(revision=data['input_revision'], segments=data['segments'])
            time.sleep(.15)
            state = dict(schema_version='trajectory.v1', input_revision=data['input_revision'],
                         phase='formatting', next_action='format_result', difficulty_band='simple',
                         progress_state='advancing', coverage='partial',
                         evidence_refs=[data['segments'][0]['id']])
            message = dict(role='assistant', content=json.dumps(state))
            finish = 'stop'
        elif self.server.tool_response:
            message = dict(role='assistant', content='format the result after checking',
                           tool_calls=[dict(id='call-1', type='function',
                                            function=dict(name='f', arguments='{}'))])
            finish = 'tool_calls'
        else:
            message = dict(role='assistant', content='answer')
            finish = 'stop'
        wire = json.dumps(dict(choices=[dict(index=0, finish_reason=finish, message=message)])).encode()
        if not interpreter:
            record['model'] = body['model']
            self.server.last_response_wire = wire
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(wire)))
        self.end_headers()
        self.wfile.write(wire)
        self.wfile.flush()
        record['end'] = time.monotonic()


def run(case, repeat):
    h = native.NativeToolsTests()
    def setup(c, s):
        h.setup(c, s)
        c['context']['ttl_ms'] = 10000
        s.RequestHandlerClass = Sink
        s.records = []
    with h.router(setup) as (p, sink):
        scope, history = h.start(p, sink)
        events = []
        start = time.monotonic()
        def ingest(payload):
            t = time.monotonic()
            # Deliberately optimistic delivery: accepted before dispatch. No readiness wait.
            code = h.ingest(p, payload)
            events.append(dict(revision=payload['revision'], status=code,
                               start_ms=(t-start)*1000, end_ms=(time.monotonic()-start)*1000))
            h.assertEqual(code, 202)
        ingest(h.event(scope, 1, 1))
        tool_seconds = .025 if case == 'fast_tool' else .5
        time.sleep(tool_seconds)  # synthetic TOOL execution, not a readiness gate
        done_tool = time.monotonic()
        ready_before_callback = any(r['kind'] == 'interpreter' and 'end' in r for r in sink.records)
        callback = h.event(scope, 1, 2)
        e = callback['event']
        e.update(kind='tool', tool_call_id='call-1', status='ok',
                 text={'tool_result': 'format checked result'}, text_truncated={'tool_result': False})
        e.pop('stream_association')
        if case in ('long_tool_callback', 'positive_wait_control', 'long_tool_metadata'):
            if case == 'long_tool_metadata':
                e.pop('text'); e.pop('text_truncated')
            ingest(callback)
        if case == 'positive_wait_control':
            time.sleep(.3)  # explicitly artificial diagnostic control, not native behaviour
        history.append(dict(role='tool', tool_call_id='call-1', content='format checked result'))
        sink.tool_response = False
        dispatch = time.monotonic()
        code, raw, _ = h.continuation(p, scope, history)
        end_dispatch = time.monotonic()
        h.assertEqual(code, 200, raw)
        model = [r for r in sink.records if r['kind'] == 'chat'][-1]['model']
        late_status = None
        if case == 'long_tool_export_late':
            late_status = h.request(p, path='/v1/context', body=callback, source=True)[0]
            h.assertEqual(late_status, 409)
        # Drain diagnostic work AFTER selection; cannot benefit the audited next dispatch.
        time.sleep(.4)
        history += [json.loads(raw)['choices'][0]['message'], dict(role='user', content='continue')]
        code, raw, _ = h.request(p, headers=h.headers(scope, 3), body=dict(
            model='auto', messages=history, max_tokens=128))
        h.assertEqual(code, 200, raw)
        chats = [r for r in sink.records if r['kind'] == 'chat']
        interpreters = [r for r in sink.records if r['kind'] == 'interpreter']
        expected = 'physical' if case in ('long_tool_no_callback', 'positive_wait_control', 'long_tool_export_late') else 'frontier'
        h.assertEqual(model, expected)
        h.assertEqual(chats[-1]['model'], 'frontier')
        return dict(case=case, repeat=repeat, tool_seconds=tool_seconds,
                    synthetic_interpreter_delay_ms=150, events=events,
                    old_interpreter_completed_before_tool_callback=ready_before_callback,
                    tool_completion_to_dispatch_ms=(dispatch-done_tool)*1000,
                    next_request_roundtrip_ms=(end_dispatch-dispatch)*1000,
                    source_to_dispatch_ms=(dispatch-start)*1000,
                    next_model=model, after_drain_model=chats[-1]['model'], late_callback_status=late_status,
                    chat_dispatches=len(chats), interpreter_dispatches=len(interpreters),
                    interpreter_records=[dict(revision=r['revision'], segments=r['segments'],
                        start_ms=(r['start']-start)*1000,
                        response_sent_ms=(r['end']-start)*1000,
                        elapsed_ms=(r['end']-r['start'])*1000) for r in interpreters],
                    usage='not supplied by synthetic provider; unknown, not zero')


if __name__ == '__main__':
    cases = ['fast_tool', 'long_tool_no_callback', 'long_tool_callback',
             'long_tool_metadata', 'long_tool_export_late', 'positive_wait_control']
    results = [run(case, repeat) for repeat in range(3) for case in cases]
    report = dict(kind='actual_C_gateway_synthetic_readiness_probe', cases=results,
                  trials=len(results), chat_dispatches=sum(r['chat_dispatches'] for r in results),
                  interpreter_dispatches=sum(r['interpreter_dispatches'] for r in results),
                  savings_claim=False, native_harness_executed=False)
    Path(os.environ['AUDIT_OUTPUT']).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}))
