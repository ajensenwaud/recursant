FROM python:3.11-slim

RUN pip install --no-cache-dir \
    flask \
    pyyaml \
    mcp \
    httpx \
    fastapi \
    uvicorn

COPY . /app
WORKDIR /app

# Copy agent cards from simulator
COPY cards/ /app/cards/

# Health check uses TCP connect for MCP mode (no HTTP health endpoint),
# HTTP /health for all other modes.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('localhost',int(__import__('os').environ.get('AGENT_PORT','5000')))); s.close()"

ENTRYPOINT ["python", "app.py"]
