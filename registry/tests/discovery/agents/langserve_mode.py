"""LangServe agent mode — FastAPI serving /openapi.json with /invoke paths."""

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def create_app():
    app = FastAPI(title='LangServe Agent', version='0.1.0')

    agent_name = os.environ.get('AGENT_NAME', 'langserve-agent')

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'mode': 'langserve', 'agent': agent_name}

    @app.get('/openapi.json')
    async def openapi_spec():
        return {
            'openapi': '3.0.0',
            'info': {'title': agent_name, 'version': '0.1.0'},
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
            },
        }

    @app.post('/invoke')
    async def invoke(body: dict = None):
        return JSONResponse({'output': f'Response from {agent_name}'})

    @app.post('/batch')
    async def batch(body: dict = None):
        return JSONResponse({'output': []})

    @app.post('/stream')
    async def stream(body: dict = None):
        return JSONResponse({'output': f'Stream response from {agent_name}'})

    @app.get('/')
    async def index():
        return {'service': agent_name, 'type': 'langserve'}

    return app
