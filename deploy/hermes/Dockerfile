FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
ARG HERMES_SHA=d0288be5b3330d2442e3907185b8e9d0958297bb
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates build-essential && rm -rf /var/lib/apt/lists/*
RUN git init /opt/hermes && cd /opt/hermes && git remote add origin https://github.com/NousResearch/hermes-agent.git && git fetch --depth 1 origin ${HERMES_SHA} && git checkout --detach FETCH_HEAD && test "$(git rev-parse HEAD)" = "${HERMES_SHA}"
RUN python -m pip install --no-cache-dir -e /opt/hermes && python -m pip check && git -C /opt/hermes clean -fdx
ENV HOME=/isolated/home HERMES_HOME=/isolated/hermes PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY observer /opt/observer
COPY run.py /opt/baseline/run.py
RUN chmod -R a+rX /opt/baseline /opt/observer
ENTRYPOINT ["python", "/opt/baseline/run.py"]
