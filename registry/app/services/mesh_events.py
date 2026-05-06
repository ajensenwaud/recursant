"""Socket.IO instance for real-time mesh visualiser events.

Provides a singleton SocketIO object that is initialised in create_app()
and used by mesh REST handlers to broadcast registration and audit events
to connected visualiser clients.

When a Redis URL is configured (via REDIS_URL env var), Socket.IO uses
Redis as a message queue so that events broadcast from any registry replica
are delivered to clients connected to every replica (required for HA).
"""

import os

from flask_socketio import Namespace, SocketIO, disconnect

_redis_url = os.environ.get("REDIS_URL")

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="gevent",
    message_queue=_redis_url,
)


class MeshNamespace(Namespace):
    """WebSocket namespace ``/mesh`` for the mesh visualiser.

    Authenticates clients via JWT token passed in the handshake query
    string (``?token=<jwt>``).  Emits ``registration`` and ``audit``
    events to all connected clients when mesh state changes.
    """

    def on_connect(self, auth):
        from flask import current_app, request

        token = None
        if auth and isinstance(auth, dict):
            token = auth.get("token")
        if not token:
            token = request.args.get("token")
        if not token:
            disconnect()
            return False

        import jwt as pyjwt

        try:
            pyjwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"],
            )
        except Exception:
            disconnect()
            return False

    def on_disconnect(self):
        pass
