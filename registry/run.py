#!/usr/bin/env python
"""Entry point for running the Flask application."""
import os
from app import create_app
from app.services.mesh_events import socketio

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
