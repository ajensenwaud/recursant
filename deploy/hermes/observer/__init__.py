"""Read-only, bounded local JSONL observer; never modifies hook payloads."""
import json
import os
from pathlib import Path
import threading
import time

HOOKS = (
    'pre_api_request', 'post_api_request', 'api_request_error',
    'pre_auxiliary_call', 'post_auxiliary_call', 'post_tool_call',
    'on_stream_start', 'on_stream_delta', 'on_stream_end',
    'on_session_start', 'on_session_end', 'agent_loop_stopped',
)


def register(ctx):
    path = Path(os.environ['HERMES_OBSERVER_PATH'])
    path.parent.mkdir(parents=True, exist_ok=True)
    limit = max(1024, min(int(os.environ.get('HERMES_OBSERVER_MAX_BYTES', '8388608')), 8388608))
    lock = threading.Lock()
    used = path.stat().st_size if path.exists() else 0
    sequence = 0
    exhausted = False

    def callback(event, **payload):
        nonlocal used, sequence, exhausted
        # Exclude legacy object fields: canonical sanitized request/response remain.
        payload = {k: v for k, v in payload.items()
                   if k not in {'assistant_message', 'request_messages', 'conversation_history'}}
        with lock:
            if exhausted:
                return
            sequence += 1
            record = {'observer_sequence': sequence, 'received_ns': time.time_ns(),
                      'event': event, 'payload': payload}
            data = (json.dumps(record, default=lambda o: {'unserialized_type': type(o).__name__},
                               ensure_ascii=True) + '\n').encode()
            if used + len(data) > limit - 256:
                data = (json.dumps({'event': 'observer_storage_limit',
                                    'observer_sequence': sequence,
                                    'completeness': 'truncated'}) + '\n').encode()
                exhausted = True
            with path.open('ab') as output:
                output.write(data)
            used += len(data)

    for name in HOOKS:
        def observe(_name=name, **kwargs):
            callback(_name, **kwargs)
        ctx.register_hook(name, observe)
