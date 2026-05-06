FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask pyyaml

COPY app.py /app/
COPY cards/ /app/cards/

HEALTHCHECK --interval=5s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${SIMULATOR_PORT:-5000}/healthz')"

ENTRYPOINT ["python", "app.py"]
