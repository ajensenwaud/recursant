"""Entry point for the discovery test agent — dispatches on AGENT_MODE env var.

Supported modes:
  a2a       — A2A agent card + JSON-RPC 2.0 endpoint (Flask)
  mcp       — FastMCP SSE server with @mcp.tool() definitions
  langserve — LangServe-shaped FastAPI (openapi + /invoke)
  crewai    — CrewAI-shaped FastAPI (/docs + /health + /run)
  custom    — Bare HTTP API (Flask)
  nginx     — Static HTML (Flask)
"""

import os
import sys


def main():
    mode = os.environ.get('AGENT_MODE', 'a2a')
    port = int(os.environ.get('AGENT_PORT', '5000'))

    print(f"Starting discovery agent in {mode} mode on port {port}", flush=True)

    if mode == 'mcp':
        from mcp_mode import run
        run()

    elif mode == 'langserve':
        from langserve_mode import create_app
        import uvicorn
        app = create_app()
        uvicorn.run(app, host='0.0.0.0', port=port, log_level='info')

    elif mode == 'crewai':
        from crewai_mode import create_app
        import uvicorn
        app = create_app()
        uvicorn.run(app, host='0.0.0.0', port=port, log_level='info')

    elif mode in ('a2a', 'custom', 'nginx'):
        from a2a_mode import create_app as create_a2a_app
        from flask import Flask, jsonify

        if mode == 'a2a':
            app = create_a2a_app()
        elif mode == 'custom':
            app = Flask(__name__)

            @app.route('/health')
            def health():
                return jsonify({'status': 'ok', 'mode': 'custom'})

            @app.route('/')
            def index():
                return jsonify({'service': os.environ.get('AGENT_NAME', 'custom-api'), 'version': '1.0.0'})

            @app.route('/api/v1/process', methods=['POST'])
            def process():
                return jsonify({'result': 'Processed'})

        elif mode == 'nginx':
            app = Flask(__name__)

            @app.route('/health')
            def health():
                return jsonify({'status': 'ok', 'mode': 'nginx'})

            @app.route('/')
            def index():
                return '<html><body><h1>Welcome to nginx</h1></body></html>'

        app.run(host='0.0.0.0', port=port)

    else:
        print(f"Unknown agent mode: {mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
