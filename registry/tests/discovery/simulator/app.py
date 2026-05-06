"""
Discovery test simulator — a single configurable Flask app that can simulate
A2A agents, LangServe agents, CrewAI agents, MCP servers, custom HTTP services,
and plain nginx-like services.

Configured entirely via environment variables.
"""

import json
import os
import random
import time
import yaml
from flask import Flask, request, jsonify, Response


app = Flask(__name__)

# Configuration from environment
MODE = os.environ.get('SIMULATOR_MODE', 'a2a')
AGENT_CARD_PATH = os.environ.get('SIMULATOR_AGENT_CARD', '')
PORT = int(os.environ.get('SIMULATOR_PORT', '5000'))
TLS_ENABLED = os.environ.get('SIMULATOR_TLS', 'false').lower() == 'true'
FLAKY = os.environ.get('SIMULATOR_FLAKY', 'false').lower() == 'true'
FLAKY_RATE = float(os.environ.get('SIMULATOR_FLAKY_RATE', '0.5'))
MCP_TOOLS = os.environ.get('SIMULATOR_MCP_TOOLS', '').split(',') if os.environ.get('SIMULATOR_MCP_TOOLS') else []
RESPONSE_DELAY_MS = int(os.environ.get('SIMULATOR_RESPONSE_DELAY_MS', '0'))
AUTH_REQUIRED = os.environ.get('SIMULATOR_AUTH_REQUIRED', 'false').lower() == 'true'
AUTH_KEY = os.environ.get('SIMULATOR_AUTH_KEY', 'secret123')

# Load agent card if in a2a mode
_agent_card = None
if MODE == 'a2a' and AGENT_CARD_PATH:
    try:
        with open(AGENT_CARD_PATH) as f:
            _agent_card = yaml.safe_load(f)
    except Exception as e:
        print(f"Warning: could not load agent card from {AGENT_CARD_PATH}: {e}")
        _agent_card = {
            'name': os.environ.get('SIMULATOR_AGENT_NAME', 'test-agent'),
            'description': 'Default test agent',
            'version': '1.0.0',
            'skills': [{'id': 'default', 'name': 'default', 'description': 'Default skill'}],
        }

if MODE == 'a2a' and not _agent_card:
    _agent_card = {
        'name': os.environ.get('SIMULATOR_AGENT_NAME', 'test-agent'),
        'description': 'Default test agent',
        'version': '1.0.0',
        'skills': [{'id': 'default', 'name': 'default', 'description': 'Default skill'}],
    }


def _maybe_delay():
    """Apply configured response delay."""
    if RESPONSE_DELAY_MS > 0:
        time.sleep(RESPONSE_DELAY_MS / 1000.0)


def _maybe_flaky():
    """Return True if this request should fail (flaky mode)."""
    if FLAKY and random.random() < FLAKY_RATE:
        return True
    return False


def _check_auth():
    """Check authentication if required. Returns error response or None."""
    if not AUTH_REQUIRED:
        return None
    auth_header = request.headers.get('Authorization', '')
    if auth_header == f'Bearer {AUTH_KEY}':
        return None
    return jsonify({'error': 'Unauthorized'}), 401


# =========================================================================
# Health endpoint (all modes)
# =========================================================================

@app.route('/healthz')
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'mode': MODE})


# =========================================================================
# A2A mode endpoints
# =========================================================================

@app.route('/.well-known/agent.json')
def well_known_agent():
    if MODE != 'a2a':
        return '', 404
    _maybe_delay()
    if _maybe_flaky():
        return '', 503
    auth_err = _check_auth()
    if auth_err:
        return auth_err
    return jsonify(_agent_card)


@app.route('/a2a', methods=['POST'])
def a2a_endpoint():
    if MODE != 'a2a':
        return '', 404
    _maybe_delay()
    if _maybe_flaky():
        return '', 503
    auth_err = _check_auth()
    if auth_err:
        return auth_err

    body = request.json or {}
    method = body.get('method', '')

    if method == 'tasks/send' or method == 'message/send':
        return jsonify({
            'jsonrpc': '2.0',
            'id': body.get('id', 1),
            'result': {
                'id': 'task-001',
                'status': {'state': 'completed'},
                'artifacts': [{'parts': [{'type': 'text', 'text': 'Simulated response'}]}],
            }
        })

    return jsonify({
        'jsonrpc': '2.0',
        'id': body.get('id', 1),
        'error': {'code': -32601, 'message': f'Method not found: {method}'}
    })


# =========================================================================
# LangServe mode endpoints
# =========================================================================

@app.route('/openapi.json')
def openapi():
    if MODE != 'langserve':
        return '', 404
    _maybe_delay()
    return jsonify({
        'openapi': '3.0.0',
        'info': {'title': 'LangServe Agent', 'version': '0.1.0'},
        'paths': {
            '/invoke': {
                'post': {'summary': 'Invoke the agent', 'operationId': 'invoke'}
            },
            '/batch': {
                'post': {'summary': 'Batch invoke', 'operationId': 'batch'}
            },
            '/stream': {
                'post': {'summary': 'Stream invoke', 'operationId': 'stream'}
            },
        }
    })


@app.route('/invoke', methods=['POST'])
def langserve_invoke():
    if MODE != 'langserve':
        return '', 404
    _maybe_delay()
    if _maybe_flaky():
        return '', 503
    auth_err = _check_auth()
    if auth_err:
        return auth_err
    return jsonify({'output': 'Simulated LangServe response'})


@app.route('/batch', methods=['POST'])
def langserve_batch():
    if MODE != 'langserve':
        return '', 404
    return jsonify({'output': []})


@app.route('/stream', methods=['POST'])
def langserve_stream():
    if MODE != 'langserve':
        return '', 404
    return jsonify({'output': 'Simulated stream response'})


# =========================================================================
# CrewAI mode endpoints
# =========================================================================

@app.route('/docs')
def crewai_docs():
    if MODE != 'crewai':
        return '', 404
    _maybe_delay()
    return '<html><body><h1>CrewAI Agent Docs</h1></body></html>'


@app.route('/run', methods=['POST', 'OPTIONS'])
def crewai_run():
    if MODE != 'crewai':
        return '', 404
    if request.method == 'OPTIONS':
        return '', 204
    _maybe_delay()
    if _maybe_flaky():
        return '', 503
    auth_err = _check_auth()
    if auth_err:
        return auth_err
    return jsonify({'result': 'Simulated CrewAI response'})


# =========================================================================
# MCP mode endpoints
# =========================================================================

def _build_mcp_tool_definitions():
    """Build tool definitions from configured tool names."""
    tools = []
    for name in MCP_TOOLS:
        name = name.strip()
        if not name:
            continue
        tools.append({
            'name': name,
            'description': f'Simulated {name} tool',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'input': {'type': 'string', 'description': f'Input for {name}'}
                },
                'required': ['input'],
            }
        })
    return tools


@app.route('/mcp', methods=['POST'])
@app.route('/', methods=['POST'])
def mcp_endpoint():
    if MODE != 'mcp':
        # For non-MCP modes, root POST returns 404
        if request.path == '/':
            return '', 404
        return '', 404
    _maybe_delay()
    if _maybe_flaky():
        return '', 503

    body = request.json or {}
    method = body.get('method', '')
    req_id = body.get('id', 1)

    if method == 'initialize':
        return jsonify({
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {
                    'name': 'simulator-mcp',
                    'version': '1.0.0',
                }
            }
        })

    if method == 'tools/list':
        return jsonify({
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'tools': _build_mcp_tool_definitions()
            }
        })

    if method == 'tools/call':
        tool_name = body.get('params', {}).get('name', '')
        return jsonify({
            'jsonrpc': '2.0',
            'id': req_id,
            'result': {
                'content': [{'type': 'text', 'text': f'Result from {tool_name}'}]
            }
        })

    return jsonify({
        'jsonrpc': '2.0',
        'id': req_id,
        'error': {'code': -32601, 'message': f'Unknown method: {method}'}
    })


# =========================================================================
# Custom HTTP mode endpoints
# =========================================================================

@app.route('/api/v1/process', methods=['POST'])
def custom_process():
    if MODE != 'custom':
        return '', 404
    _maybe_delay()
    return jsonify({'result': 'Processed'})


# =========================================================================
# Nginx mode (just serves static HTML)
# =========================================================================

@app.route('/')
def index():
    if MODE == 'nginx':
        return '<html><body><h1>Welcome to nginx</h1></body></html>'
    if MODE == 'mcp':
        return '', 404  # MCP mode root is handled by POST
    if MODE == 'custom':
        return jsonify({'service': 'custom-api', 'version': '1.0.0'})
    if MODE == 'a2a':
        return jsonify({'service': _agent_card.get('name', 'agent'), 'protocol': 'a2a'})
    if MODE == 'langserve':
        return jsonify({'service': 'langserve-agent'})
    if MODE == 'crewai':
        return jsonify({'service': 'crewai-agent'})
    return '', 200


# =========================================================================
# Entry point
# =========================================================================

if __name__ == '__main__':
    ssl_context = None
    if TLS_ENABLED:
        cert_path = os.environ.get('SIMULATOR_TLS_CERT', '/certs/server.pem')
        key_path = os.environ.get('SIMULATOR_TLS_KEY', '/certs/server-key.pem')
        ssl_context = (cert_path, key_path)

    print(f"Starting simulator in {MODE} mode on port {PORT}")
    print(f"  TLS: {TLS_ENABLED}, Flaky: {FLAKY} ({FLAKY_RATE}), Auth: {AUTH_REQUIRED}")
    if MODE == 'a2a':
        print(f"  Agent card: {_agent_card.get('name', 'unknown')}")
    if MODE == 'mcp':
        print(f"  MCP tools: {MCP_TOOLS}")

    app.run(host='0.0.0.0', port=PORT, ssl_context=ssl_context)
