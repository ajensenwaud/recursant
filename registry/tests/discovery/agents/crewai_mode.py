"""CrewAI agent mode — FastAPI serving /docs, /health, /run endpoints."""

import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse


def create_app():
    app = FastAPI(title='CrewAI Agent', version='0.1.0')

    agent_name = os.environ.get('AGENT_NAME', 'crewai-agent')

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'mode': 'crewai', 'agent': agent_name}

    @app.get('/docs', response_class=HTMLResponse)
    async def docs():
        return f'<html><body><h1>{agent_name} Docs</h1></body></html>'

    @app.post('/run')
    async def run(body: dict = None):
        return JSONResponse({'result': f'CrewAI result from {agent_name}'})

    @app.api_route('/run', methods=['OPTIONS'])
    async def run_options():
        return JSONResponse(content={}, status_code=204)

    @app.get('/')
    async def index():
        return {'service': agent_name, 'type': 'crewai'}

    return app
