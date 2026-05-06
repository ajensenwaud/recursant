"""A2A agent mode — serves a real agent card and JSON-RPC 2.0 endpoint."""

import json
import os
import random
import time

import yaml
from flask import Flask, request, jsonify


def create_app():
    app = Flask(__name__)

    card_path = os.environ.get('AGENT_CARD_PATH', '')
    flaky = os.environ.get('AGENT_FLAKY', 'false').lower() == 'true'
    flaky_rate = float(os.environ.get('AGENT_FLAKY_RATE', '0.5'))
    auth_required = os.environ.get('AGENT_AUTH_REQUIRED', 'false').lower() == 'true'
    auth_key = os.environ.get('AGENT_AUTH_KEY', 'secret123')
    delay_ms = int(os.environ.get('AGENT_RESPONSE_DELAY_MS', '0'))

    # Load agent card from YAML
    agent_card = None
    if card_path:
        try:
            with open(card_path) as f:
                agent_card = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: could not load agent card from {card_path}: {e}")

    if not agent_card:
        agent_card = {
            'name': os.environ.get('AGENT_NAME', 'test-agent'),
            'description': 'Default test agent',
            'version': '1.0.0',
            'skills': [{'id': 'default', 'name': 'default', 'description': 'Default skill'}],
        }

    def _maybe_delay():
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def _maybe_flaky():
        return flaky and random.random() < flaky_rate

    def _check_auth():
        if not auth_required:
            return None
        auth_header = request.headers.get('Authorization', '')
        if auth_header == f'Bearer {auth_key}':
            return None
        return jsonify({'error': 'Unauthorized'}), 401

    @app.route('/health')
    @app.route('/healthz')
    def health():
        return jsonify({'status': 'ok', 'mode': 'a2a', 'agent': agent_card.get('name', '')})

    @app.route('/.well-known/agent.json')
    def well_known_agent():
        _maybe_delay()
        if _maybe_flaky():
            return '', 503
        auth_err = _check_auth()
        if auth_err:
            return auth_err
        return jsonify(agent_card)

    @app.route('/a2a', methods=['POST'])
    def a2a_handler():
        _maybe_delay()
        if _maybe_flaky():
            return '', 503
        auth_err = _check_auth()
        if auth_err:
            return auth_err

        body = request.json or {}
        method = body.get('method', '')
        req_id = body.get('id', 1)
        params = body.get('params', {})

        if method in ('tasks/send', 'message/send'):
            # Extract text from message parts if present
            text = ''
            msg = params.get('message', {})
            parts = msg.get('parts', [])
            for part in parts:
                if isinstance(part, dict) and part.get('type') == 'text':
                    text = part.get('text', '')
                    break

            return jsonify({
                'jsonrpc': '2.0',
                'id': req_id,
                'result': {
                    'id': f'task-{req_id}',
                    'status': {'state': 'completed'},
                    'artifacts': [{
                        'parts': [{'type': 'text', 'text': f'Response from {agent_card["name"]}: {text}'}],
                    }],
                },
            })

        return jsonify({
            'jsonrpc': '2.0',
            'id': req_id,
            'error': {'code': -32601, 'message': f'Method not found: {method}'},
        })

    @app.route('/')
    def index():
        return jsonify({'service': agent_card.get('name', 'agent'), 'protocol': 'a2a'})

    return app
