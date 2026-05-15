# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Recursant is an enterprise agentic mesh platform — "Istio for AI agents". It has two planes that must be understood together:

- **Control plane** (`registry/`) — Flask API + React (Vite/Tailwind) frontend backed by PostgreSQL, Redis, and Kafka. Single source of truth for agent metadata, policies, mTLS certs, and audit history. Run as a single Flask app via the `create_app()` factory in `registry/app/__init__.py`; blueprints under `app/api/` register at `/v1`.
- **Data plane** (`mesh/runtime/sidecar/`) — Python sidecar process injected next to every agent pod by the Kubernetes mutating admission webhook (`k8s/webhook/`). Each sidecar runs **two listeners**: a plain HTTP port for the local agent and an mTLS A2A (JSON-RPC 2.0) port for sidecar-to-sidecar traffic. The TLS listener runs in a daemon thread via `werkzeug.serving.make_server()` with a custom handler that injects `peercert` into the WSGI environ.

The agent governance pipeline is **DRAFT → SUBMITTED → TESTING → EVALUATING → PENDING_APPROVAL → APPROVED → ACTIVE**. `submit_agent()` must call both `trigger_scan()` AND `execute_scan()` — scans do not auto-execute. The security scan issues 11 LLM calls and takes ~60s; gunicorn timeout must stay ≥ 300s. Evaluation needs seeded suites (`make seed-all`).

## Deployment model — Kubernetes is the deployment target

Everything runs in a Kind cluster (production: any cluster). The repository ships a Docker Compose file but new features and tests should target Kubernetes. NodePort mappings (no firewall rules required — DOCKER-USER is open):

- Registry Frontend: `http://localhost:8030`
- Registry API: `http://localhost:8050`
- Mortgage demo frontend: `http://localhost:8031`

Calico CNI is required (Kind's default `kindnet` does not enforce NetworkPolicy). The Helm chart lives at `k8s/charts/recursant/` and overlays mortgage-specific values from `values-mortgage.yaml`.

## Common commands

### Bring up / tear down
```bash
make k8s-all              # Full deploy: cluster + build all 14 images + Helm install + smoke test
make k8s-up               # Just create the kind cluster
make k8s-build            # Rebuild all Docker images (registry, frontend, sidecar, mortgage agents, webhook, etc.)
make k8s-load             # kind load — depends on k8s-build so it always ships fresh images
make k8s-install          # helm upgrade --install with .env-sourced secrets
make k8s-down             # Delete the kind cluster
make k8s-status / k8s-logs / k8s-port-forward
```

### Mortgage demo
```bash
make mortgage-up          # Full clean bring-up of the mortgage demo
./demo/mortgage/scripts/test_e2e.sh  # End-to-end mortgage application journey
python3 demo/mortgage/scripts/generate_demo_traffic.py --interval 8  # Continuous traffic
```

### Tests — run inside Kubernetes, not via Docker Compose
```bash
make test                          # All unit + integration
make test-unit-registry            # kubectl exec into recursant-registry pod, run pytest tests/
make test-integration-registry     # kubectl exec, run pytest tests/integration/ -m integration
make k8s-test                      # Full k8s integration suite
make k8s-test-registry             # Registry E2E (evaluation + security scan)
make k8s-test-governance / -compliance / -a2a / -isolation / -banking / -lifecycle / -llm
```

Run a single registry test inside the pod:
```bash
POD=$(kubectl get pod -n recursant -l app=recursant-registry -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n recursant $POD -c registry -- \
  env TEST_DATABASE_URL=postgresql://registry:registry@recursant-db:5432/registry_test \
  python -m pytest tests/test_agents.py::TestAgentCreation::test_create_agent_with_valid_payload -v
```

pytest markers (in `registry/pytest.ini`): `integration`, `requires_anthropic`, `requires_openai`, `requires_google`. Tests use a separate `registry_test` database derived from `DATABASE_URL`.

### Mesh tests (run locally in a venv)
```bash
cd mesh && .venv/bin/pytest tests/unit/ -v
cd mesh && .venv/bin/pytest tests/integration/ -v
cd mesh && .venv/bin/pytest tests/smoke/ -v       # Requires docker compose stack
make install                                      # Creates mesh/.venv with [dev] extras
```

### Rebuild one component without recycling the cluster
```bash
docker build -t recursant-registry registry/
kind load docker-image recursant-registry --name recursant
kubectl rollout restart deployment/recursant-registry -n recursant
```

### Database migrations (registry)
```bash
make db-migrate msg="add foo column"   # Generate Alembic migration
make db-upgrade                         # Apply migrations
# For new tables: run db.create_all() first — flask db upgrade head alone may not create them.
```

### Seeding
```bash
make seed-all     # Admin user + security tests + evaluation suites
```

### Lint
```bash
make lint         # Light: py_compile across critical mesh files
```

## Architecture details that span multiple files

### Sidecar interceptor pipeline
Every request through a sidecar passes through this ordered chain (`mesh/runtime/sidecar/interceptors/`):

```
Request → Authentication → Authorisation → Compliance → PII Redaction
       → Audit → Rate Limiting → Resilience → Target Sidecar
```

Each interceptor is independently configurable via the sidecar's YAML config. Sidecars poll the registry every 30s for policy/tool/agent-discovery updates (`registry_client.py`). When TLS is configured, advertise defaults auto-detect to `https` and `a2a_port` unless `SIDECAR_ADVERTISE_HOST`/`PORT`/`SCHEME` env vars override.

### Sidecar injection webhook
Annotations on pods drive injection (`recursant.io/inject-sidecar`, `inject-sidecars`, `agent-name`, `agent-port`, `sidecar-config`, `cert-secret`). The webhook mounts the configmap'd sidecar YAML and the cert secret into the injected container. `agent_card_path` in the sidecar YAML must match the mounted path (typically `./agent_card.yaml`).

### Networking
- Agent ↔ own sidecar: plain HTTP on localhost
- Sidecar ↔ sidecar: mTLS on A2A ports (8443–8455), JSON-RPC 2.0
- NetworkPolicy blocks direct agent-to-agent traffic — everything goes through sidecars
- Mortgage demo enforces hub-and-spoke: spokes (Auth/KYC/Credit/Core Banking/Compliance) **cannot** talk to each other; only through the Customer hub

### Multi-cluster
`mesh/tests/integration/test_multi_cluster_ha.py` covers active-active HA across two kind clusters. `make multi-cluster-up/-test/-down/-status`. App reads `CLUSTER_ID` and `REMOTE_REGISTRY_URL` to start an `EventBridge`.

## Important conventions and gotchas

### Branching and commits
- **Always work on a feature branch** — never edit files directly on `main`. Branch first, edit, commit, then merge after tests pass. This applies to every change, no matter how small.
- Conventional imperative commit subject lines ("Add openrouter LLM provider", not "Added…"). Body explains *why*.
- User pushes manually and writes commit messages in vim. Do not add `Co-Authored-By` lines.

### Testing
- **No mocking in integration tests.** No `unittest.mock`, no `@patch`, and never use Flask's `app.test_client()` in integration tests. Tests must make real HTTP calls (httpx/requests) to a real running service, hitting real PostgreSQL/Redis/Weaviate/Kafka/LLM APIs. If a component isn't deployed, deploy it. If you absolutely need to mock something, ask first.
- Run tests via `kubectl exec` against the Kind cluster — not via `docker compose exec`. Inside the pod, hit `http://localhost:5000`.
- LLM keys live in `.env` (real keys are present locally). Don't skip LLM tests as "expected failures".
- `curl` is **not** installed in the registry pod — use `python -c 'import httpx; ...'` for in-pod HTTP calls.

### Security model
- **No governance-bypass API endpoints.** Don't add endpoints like `force-activate` or `force-approve` that skip the pipeline. For demo/test data that needs to skip, do it via direct DB access in a seed/pipeline script, never via an API.
- Admin password is seeded from `.env` into the DB. Other services should never know it — use purpose-specific auth (mesh API key for sidecars, JWT for users).
- `.env.sample` is safe; `.env` contains real API keys and must not be committed. `.dockerignore` excludes `.env`, `.git`, `frontend/`, `node_modules` — keep it that way (without `.dockerignore`, Docker context transfer stalls 600s+).

### Auth and API shape
- Login returns `{"token": "..."}` — **not** `{"access_token": "..."}`. Always use `resp.json()["token"]`.
- Frontend sends `X-Tenant-ID: default` — seed scripts must match.
- Agents use **soft delete** via `deleted_at` timestamp. Filter with `Agent.deleted_at.is_(None)`, not `is_deleted`.
- API blueprints are registered in `registry/app/api/__init__.py` and exposed under `/v1`.
- List endpoints use lightweight schemas (e.g. `AgentListSchema`).

### Security scan / evaluation behavior
- Regex-based security evaluation must check success indicators **before** failure indicators — otherwise agents that quote attack vectors in refusals produce false positives.
- The test agent (`registry/test_agent/`) runs on port 5001 and reads provider-specific keys via `Config.get_api_key()` (`ANTHROPIC_API_KEY`, etc.). `LLM_API_KEY` in docker-compose is **not** consumed by the code.

### Frontend
- Brand colors are teal-based, not blue: dark `#0A0F1C`, teal `#14B8A6`, green `#06D6A0`, deep teal `#0F9690`, light `#E8F4F2`. Sidebar active states and spinners use teal.
- React 18 + Vite + Tailwind, functional components + hooks (no class components).

### Docker Compose vs Kubernetes
There's still a `docker-compose.yaml` and `docker-compose.mortgage.yaml` at the repo root, but **new features and tests should target Kubernetes**. The Kind cluster is the deployment target.

## Where to look for things

- `registry/app/api/` — 20+ Flask blueprints (agents, approval, audit, auth, certificates, consent, dashboard, evaluation, guardrails, mesh, security, users, observability, adversarial, discovery, governance, webhooks, euai_compliance)
- `registry/app/services/` — business logic (one service per domain; `mesh_events.py` hosts the Socket.IO `/mesh` namespace)
- `registry/app/models/` — SQLAlchemy
- `registry/app/schemas/` — Marshmallow
- `registry/app/llm/` — provider abstraction (Anthropic, OpenAI, Google, OpenRouter, Moonshot)
- `registry/migrations/` — Alembic
- `registry/test_agent/` — LangGraph LLM-backed test agent used by evaluation
- `mesh/runtime/sidecar/` — sidecar runtime, interceptor pipeline, dual-listener server, registry client
- `mesh/runtime/gateway/` — external A2A ingress gateway
- `mesh/examples/` — Agent A & B example deployments
- `demo/mortgage/` — full mortgage origination demo (hub-and-spoke agents, MCP servers, CrewAI compliance, stub banking APIs, separate frontend)
- `k8s/charts/recursant/` — Helm chart with mortgage overlay; `k8s/webhook/` — sidecar injection webhook; `k8s/scripts/` — kind, smoke test, integration test runners
- `scripts/install.sh` — top-level "single command" bring-up
- `ARCHITECTURE.md` / `FEATURES.md` / `INSTALL.md` — long-form docs to read before large changes

## Tech stack

Python 3.11+, Flask, SQLAlchemy, Alembic, Marshmallow, Socket.IO; React 18 + Vite + Tailwind + D3; PostgreSQL (with pgvector), Redis, Weaviate; Kafka (KRaft); A2A protocol (`a2a-sdk` 1.0+) over mTLS with JSON-RPC 2.0; OpenTelemetry; Helm 3, Kubernetes 1.27+, Calico CNI.
