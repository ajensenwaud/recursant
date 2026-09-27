#!/bin/sh
# Disposable local fixture; no provider inference or host profile mounts.
set -eu
cd "$(dirname "$0")/.."
test -f build-attempts/libattempt_probe.so || {
  printf '%s\n' 'Build first: cmake -S . -B build-attempts && cmake --build build-attempts' >&2
  exit 2
}
name=recursant-ingress-proof-$$
# A host timeout must not leave a surviving diagnostic container.
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
timeout 80s docker run --rm --name "$name" --pull never --network none --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 --workdir /tmp \
  -e HOME=/tmp/probe-home -e HERMES_HOME=/tmp/probe-hermes \
  -e PYTHONDONTWRITEBYTECODE=1 -e TERMINAL_ENV=local \
  -v "$PWD/deploy/hermes/context_adapter:/probe/context_adapter:ro" \
  -v "$PWD/bench/physical_observer.py:/probe/physical_observer.py:ro" \
  -v "$PWD/bench/hermes_ingress_probe.py:/probe/run.py:ro" \
  -v "$PWD/bench/attempt_boundary.py:/probe/attempt_boundary.py:ro" \
  -v "$PWD/build-attempts/libattempt_probe.so:/probe/libattempt_probe.so:ro" \
  --entrypoint python \
  sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b /probe/run.py
