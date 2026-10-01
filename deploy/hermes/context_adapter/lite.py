"""Optional telemetry for request-stream sessions; no source-patched Hermes.

The router (`context.sessions: "request"`) routes without any of this. When
installed, this plugin adds two advisory facts through supported hooks only:

- every model request to the router carries `X-Recursant-session-id` (the
  harness session), so two conversations with the same opening never share
  router state;
- when Hermes starts a subagent, the router is told the child session's role
  before the child's first request (`POST /v1/context/hint`);
- optionally, before a tool call touches a path matching `restricted_paths`
  (shell-style patterns set by the operator), the session is labelled
  restricted, which keeps it on private inference from then on.

Session ids and roles are advisory: compliance scans every request regardless,
and a missing or late role hint only means the router falls back to what it
derives from the request stream. The restricted label is different: it must
reach the router BEFORE the tool reads the data, so the hook runs in Hermes'
pre_tool_call (which can veto) and blocks the call if the router did not
confirm the label.
"""
import fnmatch
import shlex
import http.client
import ipaddress
import json
import os
import re
import threading
from urllib.parse import urlsplit

TOKEN = re.compile(r'[!-~]{1,128}')


class LiteBridge:
    def __init__(self, *, endpoint, source_key_env, timeout=0.5, restricted_paths=()):
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
        if (not isinstance(restricted_paths, (list, tuple)) or
                not all(isinstance(p, str) and p and len(p) <= 512 for p in restricted_paths)):
            raise ValueError('restricted_paths must be a list of nonempty patterns')
        self.restricted_paths = tuple(restricted_paths)
        self._lock = threading.Lock()
        self.annotated = 0
        self.hints = []       # (child_session_id, role, http status or None)
        self.labelled = set() # sessions the router confirmed as restricted
        self.blocked = 0

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

    def _post_hint(self, payload):
        cls = http.client.HTTPSConnection if self._url.scheme == 'https' else http.client.HTTPConnection
        conn = cls(self._host, self._url.port, timeout=self.timeout)
        try:
            conn.request('POST', '/v1/context/hint', json.dumps(payload).encode(),
                         {'Authorization': 'Bearer ' + self._credential, 'Content-Type': 'application/json'})
            response = conn.getresponse()
            response.read(4096)
            return response.status
        except (OSError, http.client.HTTPException):
            return None
        finally:
            conn.close()

    def _touches_restricted(self, value, depth=0):
        if depth > 6: return False
        if isinstance(value, str):
            try: words = shlex.split(value)
            except ValueError: words = value.split()
            candidates = [value] + words
            return any(fnmatch.fnmatch(c, p) or fnmatch.fnmatch(c.lstrip('./'), p)
                       for c in candidates for p in self.restricted_paths)
        if isinstance(value, dict): return any(self._touches_restricted(v, depth + 1) for v in value.values())
        if isinstance(value, list): return any(self._touches_restricted(v, depth + 1) for v in value)
        return False

    def pre_tool_call(self, **context):
        """Policy hook: label the session restricted before it reads restricted data."""
        session = context.get('session_id')
        if not self.restricted_paths or not self._touches_restricted(context.get('args')):
            return None
        if isinstance(session, str) and session in self.labelled:
            return None
        status = self._post_hint({'session_id': session, 'data': 'restricted'}) \
            if isinstance(session, str) and TOKEN.fullmatch(session) else None
        with self._lock:
            if status == 202:
                self.labelled.add(session)
                return None
            self.blocked += 1
        return {'action': 'block',
                'message': 'Blocked: this call touches restricted data and the router did not confirm '
                           'that this session is restricted to private inference.'}

    def subagent_start(self, **context):
        """Observer hook, invoked by Hermes before the child's first request."""
        child, parent = context.get('child_session_id'), context.get('parent_session_id')
        if not isinstance(child, str) or not TOKEN.fullmatch(child):
            return
        role = 'leaf' if context.get('child_role') == 'leaf' else 'orchestrator'
        payload = {'session_id': child, 'role': role}
        if isinstance(parent, str) and TOKEN.fullmatch(parent):
            payload['parent_session_id'] = parent
        status = self._post_hint(payload)   # advisory: a lost role hint is not an error
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
    if bridge.restricted_paths:
        ctx.register_hook('pre_tool_call', bridge.pre_tool_call)
    return bridge
