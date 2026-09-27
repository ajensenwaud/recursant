"""Optional production context API companion; no source-patched Hermes.

One explicitly registered task/session/branch per instance. Installation is a
startup barrier, never a lazy network operation in request middleware.
"""
import http.client
import ipaddress
import json
import math
import os
import queue
import re
import socket
import threading
from typing import Any
from urllib.parse import urlsplit

from . import Adapter, FIELDS, identity, serialized


class GatewayBridge(Adapter):
    def __init__(self, *, endpoint, task_id, session_id, branch, source_key_env,
                 content_enabled=False, queue_capacity=32, timeout=1.0):
        super().__init__(endpoint)
        self.scope = dict(task_id=task_id, session_id=session_id, branch=branch)
        if not all(isinstance(v, str) and re.fullmatch(r'[!-~]{1,63}', v)
                   for v in self.scope.values()):
            raise ValueError('invalid context scope')
        if (type(queue_capacity) is not int or not 1 <= queue_capacity <= 256 or
                type(timeout) not in (int, float) or not math.isfinite(timeout) or
                not 0 < timeout <= 30 or type(content_enabled) is not bool):
            raise ValueError('invalid context export bounds')
        # Numeric hosts avoid an unbounded libc DNS lookup in the startup barrier.
        # HTTP is loopback only; HTTPS uses stdlib certificate verification.
        try:
            if not isinstance(endpoint, str) or not re.fullmatch(r'[!-~]{1,2048}', endpoint):
                raise ValueError
            self._url = urlsplit(endpoint)
            host = self._url.hostname
            if not isinstance(host, str):
                raise ValueError
            self._host = host
            address = ipaddress.ip_address(self._host)
            port = self._url.port
            if (self._url.scheme not in ('http', 'https') or
                    (self._url.scheme == 'http' and not address.is_loopback) or
                    self._url.path != '/v1' or self._url.query or self._url.fragment or
                    self._url.username is not None or self._url.password is not None or
                    (port is not None and not 1 <= port <= 65535)):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError('invalid context endpoint') from None
        if not isinstance(source_key_env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', source_key_env):
            raise ValueError('invalid source credential reference')
        self._credential = os.environ.get(source_key_env, '')
        if not re.fullmatch(r'[!-~]{1,4096}', self._credential):
            raise ValueError('missing or invalid source credential')
        self.timeout = timeout
        self.content_enabled = content_enabled
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_capacity)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._pending_loss: dict[str, Any] | None = None
        self.last_status = None
        self._closed = False
        try:
            status, body = self._post('/context/open', self.scope)
            if (status != 201 or not isinstance(body, dict) or
                    set(body) != set(self.scope) | {'generation'} or
                    any(body.get(k) != v for k, v in self.scope.items()) or
                    not isinstance(body.get('generation'), str) or
                    not re.fullmatch(r'[0-9a-f]{32}', body['generation'])):
                raise ValueError
        except (OSError, ValueError, http.client.HTTPException):
            raise ValueError('context scope open failed') from None
        self.generation = body['generation']
        self.worker = threading.Thread(target=self._run, name='recursant-context-export', daemon=True)
        self.worker.start()

    def _post(self, suffix, payload) -> tuple[int, Any]:
        cls = http.client.HTTPSConnection if self._url.scheme == 'https' else http.client.HTTPConnection
        conn = cls(self._host, self._url.port, timeout=self.timeout)
        timer = None
        try:
            conn.connect()
            wire_socket = conn.sock
            assert wire_socket is not None
            def interrupt():
                try:
                    wire_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            # A socket timeout alone permits an arbitrarily slow header/body drip.
            # This transaction watchdog never shares the middleware state lock.
            timer = threading.Timer(self.timeout, interrupt)
            timer.daemon = True
            timer.start()
            conn.request('POST', self._url.path + suffix,
                         json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode(),
                         headers={'Authorization': 'Bearer ' + self._credential,
                                  'Content-Type': 'application/json'})
            response = conn.getresponse()
            raw = response.read(4097)
            if len(raw) > 4096:
                raise ValueError('context response exceeds bound')
            return response.status, json.loads(raw)
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()

    @serialized
    def request(self, request, **context):
        # Scope is mandatory authority, not optional API-correlation metadata.
        # Never infer an identity for a different task/session or destination.
        if (context.get('base_url') != self.endpoint or
                context.get('task_id') != self.scope['task_id'] or
                context.get('session_id') != self.scope['session_id']):
            return super().request(request, **context) if context.get('base_url') != self.endpoint else None
        result: Any = super().request(request, **context)
        if result is None:
            # A malformed call count/turn/API ID must not turn a registered
            # workflow into an unscoped baseline request. No attempt is invented.
            try:
                headers = dict(request.get('extra_headers') or {})
            except (TypeError, ValueError, AttributeError):
                raise ValueError('cannot annotate malformed request headers') from None
            result = {'request': dict(request, extra_headers=headers),
                      'source': 'recursant.context.v1',
                      'reason': 'registered scope; incomplete correlation'}
            self.dropped += 1
        headers = result['request']['extra_headers']
        known_scope = {'X-Recursant-generation': self.generation,
                       'X-Recursant-branch': self.scope['branch'],
                       'X-Recursant-task-id': self.scope['task_id'],
                       'X-Recursant-session-id': self.scope['session_id']}
        # Preserve every original occurrence. Conflicting/duplicate caller tags
        # remain invalid for the gateway; never normalize/repair them silently.
        present = {str(k).lower() for k in headers}
        for name, value in known_scope.items():
            if name.lower() not in present:
                headers[name] = value
        return result

    @serialized
    def emit(self, event):
        key = identity(event)
        if key is not None and key[:2] != (self.scope['task_id'], self.scope['session_id']):
            return
        self.sequence += 1
        attempt = event.get('attempt')
        if key is None or not isinstance(attempt, str) or not re.fullmatch(r'[!-~]{1,128}', attempt):
            self._record_loss(event)
            return
        # The C worker accepts only whole exposed model segments. Preserve the
        # adapter's raw provenance/truncation flags; never trim to make it fit.
        text = event.get('text')
        valid_text = True
        if text is not None:
            truncated = event.get('text_truncated', {})
            try:
                valid_text = (bool(text) and set(text) <= {'assistant_plan', 'reasoning'} and
                    set(truncated) == set(text) and all(
                        isinstance(value, str) and 0 < len(value.encode('utf-8')) <= 1024 and
                        '\x00' not in value and truncated[name] is False
                        for name, value in text.items()))
            except (UnicodeError, TypeError, AttributeError):
                valid_text = False
        if event.get('kind') not in ('response', 'invalidation') or not valid_text:
            self._record_loss(event)
            return
        event = dict(event, sequence=self.sequence, dropped=self.dropped,
                     upstream_gaps='unknown', schema='recursant.context.v1')
        payload = dict(generation=self.generation, branch=self.scope['branch'],
                       revision=self.sequence, event=event)
        if self._closed:
            self._record_loss(event)
            return
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self._record_loss(event)
        self._wake.set()

    def _record_loss(self, event):
        # Called under the state lock; keep only real source identities, never text.
        self.dropped += 1
        key = identity(event)
        attempt = event.get('attempt')
        if key and isinstance(attempt, str) and re.fullmatch(r'[!-~]{1,128}', attempt):
            self._pending_loss = dict(zip(FIELDS, key))
            self._pending_loss.update(kind='invalidation', attempt=attempt,
                association='ambiguous', routing_eligible=False,
                association_scope='middleware_invocation', physical_routing_eligible=False,
                physical_attempt_uniqueness='unproven')
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            queued = False
            with self._lock:
                if self._stop.is_set():
                    break
                try:
                    payload = self._queue.get_nowait()
                    queued = True
                except queue.Empty:
                    if self._pending_loss is not None:
                        self.sequence += 1
                        event = dict(self._pending_loss, sequence=self.sequence,
                            dropped=self.dropped, upstream_gaps='unknown', schema='recursant.context.v1')
                        self._pending_loss = None
                        payload = dict(generation=self.generation, branch=self.scope['branch'],
                                       revision=self.sequence, event=event)
                    else:
                        payload = None
                        self._wake.clear()
                if payload:
                    # Loss after enqueue must be visible on already queued evidence too.
                    payload['event']['dropped'] = self.dropped
            if payload is None:
                self._wake.wait()
                continue
            status = None
            try:
                status, _ = self._post('/context', payload)
            except (OSError, ValueError, http.client.HTTPException):
                pass
            finally:
                with self._lock:
                    self.last_status = status
                    # A loss marker is attempted once, not an infinite retry loop.
                    if status != 202 and payload['event']['kind'] != 'invalidation':
                        self._record_loss(payload['event'])
                if queued:
                    self._queue.task_done()

    def close(self, timeout=0.2):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 30:
            raise ValueError('invalid shutdown bound')
        with self._lock:
            self._closed = True
            self._stop.set()
            self._wake.set()
            while True:
                try:
                    payload = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._record_loss(payload['event'])
                self._queue.task_done()
        self.worker.join(timeout)


def install_gateway(ctx, *, enabled=False, **options):
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    if not enabled:
        return None
    adapter = GatewayBridge(**options)
    ctx.register_middleware('llm_request', adapter.request)
    ctx.register_hook('post_api_request', adapter.response)
    ctx.register_hook('post_tool_call', adapter.tool)
    ctx.register_hook('api_request_error', adapter.error)
    return adapter
