# Recursant v4

C inference gateway for explicit hybrid routing and deterministic request-egress controls. Requirements: [AGENTS.md](AGENTS.md).

**Current checkpoint:** M1 transport is implemented and container-tested; live endpoint validation is in progress. M2 integration follows M1. M3 is not implemented and remains subject to architecture review.

## Production binary

`recursant serve CONFIG` and `recursant validate CONFIG` use one JSON configuration.

- Authenticated OpenAI-compatible `POST /v1/chat/completions` and `GET /v1/models`.
- Metadata-only unauthenticated `GET /healthz`.
- Explicit aliases or configured physical model identifiers select private inference or OpenRouter.
- JSON and SSE pass-through, including tool calls/results, reasoning fields and usage chunks.
- TLS verification, no redirects, no automatic retries or fallback, static upstream errors.
- Bounded body size, concurrency, upload/upstream deadlines and a 64 KiB streaming queue.
- libmicrohttpd parses HTTP, libcurl handles upstream transport, and Jansson parses JSON with duplicate-key rejection. This is a bounded threaded implementation, not a demonstrated latency/throughput advantage.

The old `recursant-tracer` and `recursant-validate` executables are development spikes. Use the **single `recursant` binary** for deployment and configuration validation.

## Build and test in Docker

No host package installation is needed beyond an existing Docker installation.

```sh
docker build -f deploy/Dockerfile.dev -t recursant-v4-dev:local deploy
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  recursant-v4-dev:local bash -lc \
  'cmake -S . -B build/container -DCMAKE_BUILD_TYPE=Debug &&
   cmake --build build/container -j2 &&
   ctest --test-dir build/container --output-on-failure'
```

Repeat with `-B build/container-asan -DRECURSANT_SANITIZERS=ON` for address/undefined-behaviour checks. CTest passes the exact built executable to integration tests, not an unrelated binary from another build directory. Tests use local synthetic sinks, including a local untrusted TLS server; ordinary test runs make no model calls.

```sh
docker build -f deploy/Dockerfile -t recursant-v4:local .
```

The Docker context is allowlisted. `.env`, Git history, runtime files and raw traces never enter the image. The runtime image has no compiler and defaults to an unprivileged UID.

## Configuration and deployment

[config/recursant.example.json](config/recursant.example.json) is the intended M2 configuration; compliance-enabled startup fails closed until the M2 engine is connected.

Credentials are **environment references**, never JSON values. Supply `RECURSANT_API_KEY` and `OPENROUTER_API_KEY` through your secret manager/environment. Never commit `.env` or pass secret values on a command line.

When using a mode-0600 host configuration, run the container as its owning unprivileged UID/GID. Do not broaden file permissions simply to fit the image's default UID.

```sh
docker run --rm --name recursant-v4 \
  --user "$(id -u):$(id -g)" --read-only --cap-drop ALL \
  --security-opt no-new-privileges \
  -p 127.0.0.1:8080:8080 \
  -v "$PWD/config/recursant.example.json:/etc/recursant/config.json:ro" \
  -e RECURSANT_API_KEY -e OPENROUTER_API_KEY \
  recursant-v4:local
```

The container must resolve/reach the configured private hostname; add a project-container `--add-host` entry when host-specific DNS requires it. Do not expose the plaintext listener publicly; keep the loopback binding or put authenticated TLS ingress in front of it.

`--test-mode` permits public HTTP **only on loopback** for tests. Never use it in deployment. Public HTTPS remains mandatory otherwise.

## Scope and remaining work

- Explicit routing is not intelligent cost selection. No token-efficiency or speed advantage has been demonstrated.
- No model retries are attempted after uncertain dispatch. Private failures never trigger public fallback.
- Regex-based M2 is a configured-pattern request-egress boundary, not universal PII detection, output DLP, verified residency or APRA certification.
- Tenant federation, persistent session policy, Postgres audit, Next.js management, pooling and hard admission budgets from the broader architecture plan remain separate work. Do not interpret the functional M1/M2 requirements as completion of every production-hardening item in that plan.
- M3 direct-harness/OTel context engine and matched quality/token evaluation remain unimplemented.
- Accounting evaluator: `python3 -m bench.accounting RECORDS.json`. It reports descriptive arithmetic, not a statistical release pass. Missing usage remains unknown; failed attempts and auxiliary calls must be retained.

## Evidence

- [Production router tests and RED/GREEN history](docs/evidence/router-tdd.md)
- [Initial policy predicate](docs/evidence/egress-tdd.md)
- [Accounting tests](docs/evidence/accounting-tdd.md)
- [Baseline source discovery](docs/hermes-baseline-discovery.md)
- [Benchmark acceptance contract](docs/benchmark-contract.md)

Live smoke reports are deliberately labelled as smoke tests, not token-efficiency evidence. Raw traces and runtime configuration stay under ignored `.hermes/runtime/`.
