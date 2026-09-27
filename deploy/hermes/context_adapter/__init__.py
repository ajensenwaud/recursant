"""Opt-in request correlation; headers are not authentication."""
import json
import re
import socket
import uuid

FIELDS = ('task_id', 'session_id', 'turn_id', 'api_request_id')


def identity(payload):
    values = tuple(payload.get(k) for k in FIELDS)
    if all(isinstance(v, str) and re.fullmatch(r'[!-~]{1,128}', v) for v in values):
        return values
    return None


class Adapter:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.attempts = {}
        self.tools = {}
        self.content_enabled = False
        self.socket = None
        self.sequence = 0
        self.dropped = 0

    def configure_sink(self, path):
        self.close()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.sink_path = path

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def emit(self, event):
        self.sequence += 1
        event.update(sequence=self.sequence, dropped=self.dropped, upstream_gaps='unknown',
                     schema='recursant.context.v1')
        payload = json.dumps(event, ensure_ascii=False, separators=(',', ':')).encode()
        try:
            if self.socket is None or len(payload) > 24576:
                self.dropped += 1
                return
            self.socket.sendto(payload, self.sink_path)
        except OSError:
            self.dropped += 1

    def response(self, **context):
        key = identity(context)
        if context.get('base_url') != self.endpoint:
            return
        if key in self.tools or context.get('finish_reason') not in ('stop', 'tool_calls'):
            self.error(**context)
        attempts = self.attempts.get(key)
        association = 'exact' if attempts and attempts[1] == 1 else ('ambiguous' if attempts else 'missing')
        event = dict(kind='response', association=association, routing_eligible=association == 'exact',
                     association_scope='middleware_invocation', physical_routing_eligible=False,
                     physical_attempt_uniqueness='unproven', stream_association='unsupported')
        if key:
            event.update(zip(FIELDS, key))
        if association == 'exact':
            message = context.get('assistant_message')
            self.tools[key] = {getattr(t, 'id', None) for t in (getattr(message, 'tool_calls', None) or [])[:32]
                               if isinstance(getattr(t, 'id', None), str) and len(t.id) <= 128}
            event['attempt'] = attempts[0]
            if self.content_enabled:
                message = context.get('assistant_message')
                event['text'] = {k: v[:2048] for k, v in (
                    ('assistant_plan', getattr(message, 'content', None)),
                    ('reasoning', getattr(message, 'reasoning_content', None))) if isinstance(v, str)}
        self.emit(event)

    def tool(self, **context):
        key = identity(context)
        attempts = self.attempts.get(key)
        call = context.get('tool_call_id')
        exact = bool(attempts and attempts[1] == 1 and isinstance(call, str) and call in self.tools.get(key, set()))
        event = dict(kind='tool', routing_eligible=exact,
                     association='exact' if exact else 'missing_or_ambiguous',
                     association_scope='middleware_invocation', physical_routing_eligible=False,
                     physical_attempt_uniqueness='unproven')
        if key:
            event.update(zip(FIELDS, key))
        if exact:
            event.update(attempt=attempts[0], tool_call_id=call)
            status = context.get('status')
            event['status'] = status if status in ('ok', 'success', 'error', 'blocked', 'cancelled') else 'unknown'
            if self.content_enabled and isinstance(context.get('result'), str):
                event['text'] = {'tool_result': context['result'][:2048]}
        self.emit(event)

    def error(self, **context):
        key = identity(context)
        if context.get('base_url') == self.endpoint and key in self.attempts:
            self.attempts[key] = (self.attempts[key][0], 2)
            self.tools.pop(key, None)

    def request(self, request, **context):
        key = identity(context)
        count = context.get('api_call_count')
        if (context.get('base_url') != self.endpoint or key is None or
                type(count) is not int or not 0 <= count <= 999999999):
            return None
        headers = dict(request.get('extra_headers') or {})
        if any(str(k).lower().startswith('x-recursant-') for k in headers):
            self.error(**context)
            return None
        headers['X-Recursant-api-call-count'] = str(count)
        headers.update({'X-Recursant-' + k.replace('_', '-'): v for k, v in zip(FIELDS, key)})
        headers['X-Recursant-attempt'] = uuid.uuid4().hex
        previous = self.attempts.get(key)
        if previous or len(self.attempts) < 256:
            self.attempts[key] = (headers['X-Recursant-attempt'], 2 if previous else 1)
        return {'request': dict(request, extra_headers=headers),
                'source': 'recursant.context.v1', 'reason': 'correlation only; not authentication'}


def install(ctx, *, enabled=False, endpoint):
    if not enabled:
        return None
    adapter = Adapter(endpoint)
    ctx.register_middleware('llm_request', adapter.request)
    ctx.register_hook('post_api_request', adapter.response)
    ctx.register_hook('post_tool_call', adapter.tool)
    ctx.register_hook('api_request_error', adapter.error)
    return adapter
