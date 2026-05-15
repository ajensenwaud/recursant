# Recursant

Scaling AI agents creates a control problem most enterprises are not equipped for. Agents make decisions, talk to systems, and move data across stacks and clouds, yet most of today’s observability and compliance tools stop at the boundary of a single stack or a single cloud. This creates potential control gaps. 

I created an open source platform to help close that gap.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## What is Recursant?

Recursant is an enterprise-grade agentic mesh platform — Istio for AI agents.
It provides governance, security, compliance, and observability for AI agent
deployments where agents talk to each other (A2A protocol) and to tools (MCP).

The architecture has two planes:

- **Control plane** (`registry/`) — Flask + React web app backed by PostgreSQL,
  Redis, and Kafka. The single source of truth for agent metadata, policies,
  certificates, and audit history. Includes a full web UI for governance
  workflows.
- **Data plane** (`mesh/`) — A Python sidecar process injected next to every
  agent pod, mediating all inter-agent traffic over mTLS via the
  [A2A protocol](https://github.com/a2aproject/A2A).

Recursant is a **runtime governance layer for any AI agent** — LangChain,
LangGraph, CrewAI, OpenClaw, ServiceNow (in-flight), custom HTTP — not a
framework for writing agents. Bring your own agent code; Recursant gives it
identity, policy enforcement, observability, and compliance guarantees.

## Why use it?

If you're running AI agents at any meaningful scale, you eventually hit the
same questions:

- **Who's allowed to call whom?** Hub-and-spoke topologies, sovereignty zones, data classification.
- **What's leaking?** PII redaction, prompt-injection guardrails, chain-of-thought audit.
- **How did this decision get made?** Hash-chained audit trail per request, end-to-end traces.
- **Is the agent safe to deploy?** Automated security scans + LLM-as-judge eval suites + human approval gates.
- **What is it costing me?** Per-agent token consumption, model breakdown, budget thresholds.
- **Did the guardrail catch the attack?** Real-time effectiveness matrix, adversarial test runs, false-positive tracking.

Recursant answers all of these without requiring you to rewrite your agents.

## How it works

```
┌────────────────────────────────────────────────────────────────────┐
│                      Control Plane (Registry)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────────┐   │
│  │ Agent    │ │ Policy   │ │ Cert         │ │ Observability   │   │
│  │ Registry │ │ Engine   │ │ Authority    │ │ (Kafka + UI)    │   │
│  └──────────┘ └──────────┘ └──────────────┘ └─────────────────┘   │
└──────────────────────────────────────────────────┬─────────────────┘
                                  │ policy + identity (gRPC / REST)
        ┌─────────────────────────┴─────────────────────────┐
        ▼                                                   ▼
┌──────────────────┐                                ┌──────────────────┐
│  Pod: Agent A    │                                │  Pod: Agent B    │
│  ┌────┐ ┌─────┐  │     mTLS, JSON-RPC 2.0         │  ┌────┐ ┌─────┐  │
│  │App │◀┤Side-│◀─┼────────── A2A protocol ────────┼─▶│App │◀┤Side-│  │
│  │    │ │car  │  │                                │  │    │ │car  │  │
│  └────┘ └─────┘  │                                │  └────┘ └─────┘  │
└──────────────────┘                                └──────────────────┘
```

Every agent pod gets a sidecar injected by a Kubernetes mutating admission
webhook. The sidecar runs an interceptor pipeline — authentication,
authorisation, compliance, PII redaction, guardrails, audit, rate limiting,
resilience — for every inbound and outbound message. Agent code is unchanged.

For the full architecture, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).
For the catalog of capabilities, see [`FEATURES.md`](./FEATURES.md).

---

## Quick start

Recursant runs in Kubernetes (Kind for local dev, any cluster in production).
The fastest path to a working demo:

```bash
# 1. Configure secrets (at minimum: an LLM API key)
cp .env.sample .env
$EDITOR .env       # set OPENROUTER_API_KEY (or ANTHROPIC_/OPENAI_/GOOGLE_API_KEY)

# 2. One command to bring everything up — Kind cluster, build all images,
#    deploy via Helm, smoke test
./scripts/install.sh

# 3. Open the registry UI (login: admin / value of ADMIN_PASSWORD)
open http://localhost:8030
```

Full install + deployment guide: [`INSTALL.md`](./INSTALL.md).

---

## Try the mortgage demo

Recursant ships with a complete mortgage origination demo — a Customer Agent
hub coordinating Auth, KYC (n8n workflow), Credit, Core Banking, and
Compliance (CrewAI) spokes, with hub-and-spoke NetworkPolicy enforcement and
a full audit trail.

```bash
# Mortgage demo UI
open http://localhost:8031

# End-to-end test — walks the full mortgage application journey
python3 demo/mortgage/scripts/test_e2e.py

# Continuous traffic generator (great for live demos / recordings)
python3 demo/mortgage/scripts/generate_demo_traffic.py --interval 8
```

Watch traffic animate live in the **Mesh Visualiser** and **Observability**
tabs of the registry UI.

---

## OpenClaw integration

Recursant ships a governance plugin for [OpenClaw](https://www.openclaw.ai)
in `integrations/openclaw/`. The plugin enrols an OpenClaw instance with the
registry and intercepts its tool calls, LLM calls, and chat messages
in-process — authorisation, PII redaction, rate limiting, and hash-chained
audit. v0 is cooperative governance only (provider replacement and host-level
enforcement land in v1).

```bash
# Start the OpenClaw gateway and run the end-to-end smoke test
integrations/openclaw/scripts/start-gateway.sh
integrations/openclaw/scripts/smoke-test.sh
```

The smoke test sends a message through the gateway, waits for the plugin's
audit queue to flush, and verifies a new `openclaw.llm_call` row landed in
the registry. See [`integrations/openclaw/README.md`](./integrations/openclaw/README.md)
for plugin config and the registry endpoints it talks to.

---

## Repository layout

```
recursant/
├── registry/              # Control plane — Flask API + React frontend
│   ├── app/
│   │   ├── api/           # REST blueprints (agents, mesh, guardrails, ...)
│   │   ├── consumers/     # Kafka consumer services (pg-writer, ws-broadcaster, ...)
│   │   ├── models/        # SQLAlchemy models
│   │   ├── services/      # Business logic
│   │   ├── llm/           # LLM provider abstraction
│   │   └── schemas/       # Marshmallow schemas
│   ├── frontend/          # React + Vite + Tailwind UI
│   ├── test_agent/        # LangGraph test agent for evaluation
│   ├── scripts/           # Seed scripts (admin, security tests, eval suites)
│   └── migrations/        # Alembic migrations
│
├── mesh/                  # Data plane — Python sidecar
│   ├── runtime/sidecar/   # Sidecar with interceptor pipeline
│   ├── runtime/gateway/   # External A2A ingress gateway
│   └── examples/          # Agent A & B example agents
│
├── demo/mortgage/         # Mortgage origination demo
│   ├── agents/            # Customer, KYC/Credit, Core Banking, Compliance
│   ├── frontend/          # Demo React frontend
│   ├── mcp_servers/       # MCP tool implementations
│   └── stubs/             # Mock banking APIs
│
├── integrations/          # Third-party platform integrations
│   └── openclaw/          # OpenClaw governance plugin (v0 cooperative)
│
├── k8s/                   # Kubernetes deployment
│   ├── charts/recursant/  # Helm chart
│   ├── webhook/           # Sidecar injection webhook
│   └── scripts/           # Cluster lifecycle scripts
│
├── sdk/                   # Python SDK + CLI for agent developers
├── scripts/               # Top-level install / quickstart / teardown scripts
├── ARCHITECTURE.md        # System architecture deep-dive
├── FEATURES.md            # Capability catalog with code references
├── INSTALL.md             # Detailed installation guide
├── CONTRIBUTING.md        # How to contribute
└── AUTHOR.md              # About the author
```

---

## Documentation

| Document | Purpose |
|---|---|
| [`README.md`](./README.md) | This file |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Two-plane architecture, sidecar internals, observability pipeline |
| [`FEATURES.md`](./FEATURES.md) | Feature-by-feature catalog with code references |
| [`INSTALL.md`](./INSTALL.md) | Full install guide (prerequisites, env, alternatives) |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | How to file issues and submit PRs |
| [`AUTHOR.md`](./AUTHOR.md) | About the author |
| `sdk/README.md` | Python SDK and CLI for agent developers |
| `integrations/openclaw/README.md` | OpenClaw governance plugin (enrolment, interception, registry endpoints) |

---

## Useful commands

```bash
make k8s-all              # Full bring-up: cluster + build + deploy + smoke test
make k8s-test             # Run all integration tests
make k8s-status           # Pod and service status
make k8s-logs             # Tail registry + webhook logs
make k8s-port-forward     # Forward registry, frontend, mortgage demo to localhost
make k8s-down             # Tear down the Kind cluster
```

Run `make help` for the full list (Docker Compose, multi-cluster, individual
test suites, etc.).

---

## Tech stack

- **Backend**: Python 3.11+, Flask, SQLAlchemy, Alembic, Marshmallow
- **Frontend**: React 18, Vite, Tailwind CSS, D3 (visualizations)
- **Storage**: PostgreSQL (with pgvector), Redis, Weaviate
- **Streaming**: Apache Kafka (KRaft mode, no ZooKeeper)
- **Mesh**: A2A protocol (`a2a-sdk` 1.0+) over mTLS, JSON-RPC 2.0
- **Observability**: OpenTelemetry, Socket.IO (live updates), Prometheus-compatible metrics
- **Deploy**: Helm 3, Kubernetes 1.27+, Calico CNI (NetworkPolicy enforcement)

---

## License

[MIT](./LICENSE) — use, fork, and adapt freely. Attribution appreciated.

## Status

Recursant is an active project. The architecture is stable; APIs may evolve
before a 1.0 release. Issues and PRs welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).
