"""Bounded fixture-only HTTP provider; never calls an inference endpoint."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import threading
import time
import uuid
from .tasks import FIXTURE_SOLUTIONS


def completion_response(dispatch_id, message, finish, *, stream, model='fixture', usage=None,
                        include_usage=False):
    """(raw bytes, MIME) of one scripted assistant step, OpenAI-shaped: an SSE chunk stream
    when the request streamed, else a chat.completion object. usage (optional) is attached
    to the JSON object always and to the stream only when include_usage was requested."""
    head = dict(id=dispatch_id, object='chat.completion.chunk' if stream else 'chat.completion',
                created=1, model=model)
    if stream:
        chunks = [dict(head, choices=[dict(index=0, delta=message, finish_reason=None)]),
                  dict(head, choices=[dict(index=0, delta={}, finish_reason=finish)])]
        if usage is not None and include_usage: chunks.append(dict(head, choices=[], usage=usage))
        return (''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n').encode(), 'text/event-stream'
    body = dict(head, choices=[dict(index=0, message=message, finish_reason=finish)])
    if usage is not None: body['usage'] = usage
    return json.dumps(body).encode(), 'application/json'


def tool_call_message(call_id, name, arguments, *, content):
    """Assistant message carrying one function tool call (the scripted agents' only shape)."""
    return {'role': 'assistant', 'content': content,
            'tool_calls': [dict(index=0, id=call_id, type='function',
                                function=dict(name=name, arguments=json.dumps(arguments)))]}


class Meter:
    def __init__(self, *, mode, request_cap):
        if mode != 'fixture':
            raise ValueError('live mode requires the reviewed live runner')
        self.mode, self.request_cap = mode, request_cap
        self.calls = []
        self.lock = threading.Lock()
        self.traces = []
        self.context_events = []

    def handle(self, path, body, headers):
        if path=='/v1/context/open':
            return 201,json.dumps(dict(body,generation=uuid.uuid4().hex)).encode(),'application/json'
        if path.startswith('/v1/context'):
            self.context_events.append(body)
            return 202,b'{}','application/json'
        return 404,b'{}','application/json'

    def dispatch(self, body, task_id, arm):
        with self.lock:
            if len(self.calls) >= self.request_cap:
                return 429, b'{"error":"request_cap"}', 'application/json'
            index = len(self.calls)
            call = dict(dispatch_id=uuid.uuid4().hex, task_id=task_id, arm=arm,
                        attempt=index+1, role='main', evidence_kind='fixture',
                        input_tokens=None, output_tokens=None, reasoning_tokens=None,
                        cached_input_tokens=None, reasoning_semantics='unknown',
                        cost_usd=None, tokenizer=None, started_at=time.time())
            self.calls.append(call)
            self.traces.append({'dispatch_id':call['dispatch_id'], 'request':body})
        source = base64.b64encode(FIXTURE_SOLUTIONS[task_id].encode()).decode()
        commands = [
            'pwd; python -c "from pathlib import Path; print(Path(\'TASK.md\').read_text())"',
            "python -c \"import base64; from pathlib import Path; Path('solution.py').write_bytes(base64.b64decode('"+source+"'))\"",
            "printf '%s\\n' '{}' | python solution.py" if task_id=='dag-v1' else
            "printf '%s\\n' '[]' | python solution.py" if task_id=='ledger-v1' else
            "printf '%s\\n' '{\"busy\":[],\"window\":[0,9]}' | python solution.py"
        ]
        message = {'role':'assistant','content':'Scripted fixture step; no inference.'}
        finish = 'stop'
        if index < len(commands):
            message = tool_call_message('fixture_'+str(index),'terminal',{'command':commands[index]},
                                        content=message['content'])
            finish='tool_calls'
        else:
            message['content']='Fixture artifact written and local test executed.'
        raw,mime=completion_response(call['dispatch_id'],message,finish,stream=bool(body.get('stream')))
        call['finished_at']=time.time()
        call['status']=200
        self.traces[-1]['response']=raw.decode()
        return 200,raw,mime


def handler(meter, task_id, arm):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4*1024*1024:
                self.send_error(413); return
            body=json.loads(self.rfile.read(length))
            if self.path=='/v1/chat/completions' and hasattr(meter,'dispatch'):
                status,raw,mime=meter.dispatch(body,task_id,arm)
            else:
                status,raw,mime=meter.handle(self.path,body,dict(self.headers))
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    return Handler


@contextmanager
def serve(meter, *, task_id, arm):
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(meter,task_id,arm))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1'
    finally:
        server.shutdown(); server.server_close(); thread.join()
