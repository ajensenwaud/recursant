"""Optional telemetry for request-stream sessions; no source-patched Hermes.

The router (`context.sessions: "request"`) routes without any of this. When
installed, this plugin adds two advisory facts through supported hooks only:

- every model request to the router carries `X-Recursant-session-id` (the
  harness session), so two conversations with the same opening never share
  router state;
- when Hermes starts a subagent, the router is told the child session's role
  before the child's first request (`POST /v1/context/hint`).

Neither is authentication or placement authority: compliance scans every
request regardless, and a missing or late hint only means the router falls
back to what it derives from the request stream.
"""
import http.client
import ipaddress
import json
import os
import re
import threading
from urllib.parse import urlsplit

TOKEN = re.compile(r'[!-~]{1,128}')


class LiteBridge:
    def __init__(self, *, endpoint, source_key_env, timeout=0.5):
        url = urlsplit(endpoint) if isinstance(endpoint, str) else None
        try:
            host = url.hostname if url else None
            if not isinstance(host, str):
                raise ValueError
            address = ipaddress.ip_address(host)
            if (url.scheme not in ('http', 'https') or (url.scheme == 'http' and not address.is_loopback) or
                    url.path != '/v1' or url.query or url.fragment or url.username is not None):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError('invalid context endpoint') from None
        if type(timeout) not in (int, float) or not 0 < timeout <= 5:
            raise ValueError('invalid hint timeout')
        self.endpoint, self._url, self._host, self.timeout = endpoint, url, host, timeout
        self._credential = os.environ.get(source_key_env, '') if isinstance(source_key_env, str) else ''
        if not re.fullmatch(r'[!-~]{1,4096}', self._credential):
            raise ValueError('missing or invalid source credential')
        self._lock = threading.Lock()
        self.annotated = 0
        self.hints = []       # (child_session_id, role, http status or None)

    def request(self, request, **context):
        """llm_request middleware: annotate, never alter the body."""
        session = context.get('session_id')
        if context.get('base_url') != self.endpoint or not isinstance(session, str) or not TOKEN.fullmatch(session):
            return None
        try:
            headers = dict(request.get('extra_headers') or {})
        except (TypeError, ValueError, AttributeError):
            return None
        if any(str(k).lower().startswith('x-recursant-') for k in headers):
            return None
        headers['X-Recursant-session-id'] = session
        with self._lock:
            self.annotated += 1
        return {'request': dict(request, extra_headers=headers),
                'source': 'recursant.session.v1', 'reason': 'session identity only; not authentication'}

    def subagent_start(self, **context):
        """Observer hook, invoked by Hermes before the child's first request."""
        child, parent = context.get('child_session_id'), context.get('parent_session_id')
        if not isinstance(child, str) or not TOKEN.fullmatch(child):
            return
        role = 'leaf' if context.get('child_role') == 'leaf' else 'orchestrator'
        payload = {'session_id': child, 'role': role}
        if isinstance(parent, str) and TOKEN.fullmatch(parent):
            payload['parent_session_id'] = parent
        status = None
        cls = http.client.HTTPSConnection if self._url.scheme == 'https' else http.client.HTTPConnection
        conn = cls(self._host, self._url.port, timeout=self.timeout)
        try:
            conn.request('POST', '/v1/context/hint', json.dumps(payload).encode(),
                         {'Authorization': 'Bearer ' + self._credential, 'Content-Type': 'application/json'})
            response = conn.getresponse()
            response.read(4096)
            status = response.status
        except (OSError, http.client.HTTPException):
            pass   # advisory: a lost hint is not an error for the harness
        finally:
            conn.close()
        with self._lock:
            self.hints.append((child, role, status))


def install_lite(ctx, *, enabled=False, **options):
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    if not enabled:
        return None
    bridge = LiteBridge(**options)
    ctx.register_middleware('llm_request', bridge.request)
    ctx.register_hook('subagent_start', bridge.subagent_start)
    return bridge
