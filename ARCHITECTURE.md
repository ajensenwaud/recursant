# Architecture

Recursant is an enterprise agentic mesh platform that provides governance, security, and compliance for AI agent-to-agent (A2A) communication. It has two planes: a **control plane** (the registry) that manages agent lifecycle, policy, and tooling, and a **data plane** (mesh sidecars) that enforces policy at runtime.

## Component diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Control Plane                                                          │
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐ │
│  │   Frontend    │   │ Registry API │───│ PostgreSQL  │   │   Redis   │ │
│  │  (React/Vite) │──▶│   (Flask)    │   │  (HA opt.)  │   │(Sentinel) │ │
│  │  :8030        │   │  :8050       │   │  :5432      │   │  :6379    │ │
│  └──────────────┘   └──────┬───────┘   └────────────┘   └───────────┘ │
│                             │                                           │
│              ┌──────────────┼──────────────┐                            │
│              │              │              │                             │
│              ▼              ▼              ▼                             │
│     ┌──────────────┐ ┌───────────┐ ┌──────────────┐                    │
│     │  Test Agent   │ │  Webhook  │ │   Gateway    │                    │
│     │  (LLM proxy)  │ │ (Sidecar  │ │  (optional)  │                    │
│     │  :5001        │ │  Inject)  │ │  :8080       │                    │
│     └──────────────┘ │  :443     │ └──────────────┘                    │
│                       └───────────┘                                     │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Data Plane (Mesh)                                                      │
│                                                                         │
│  ┌─────────────────────────┐       ┌─────────────────────────┐         │
│  │  Pod: Agent A            │       │  Pod: Agent B            │         │
│  │  ┌─────────┐ ┌────────┐ │       │  ┌─────────┐ ┌────────┐ │         │
│  │  │ Agent A  │ │Sidecar │ │ mTLS  │  │ Agent B  │ │Sidecar │ │         │
│  │  │  :5010   │◀┤ :9901  │◀┼───────┼─▶│  :5011   │◀┤ :9902  │ │         │
│  │  │          │ │ :8443  │ │  A2A  │  │          │ │ :8444  │ │         │
│  │  └─────────┘ └────────┘ │       │  └─────────┘ └────────┘ │         │
│  └─────────────────────────┘       └─────────────────────────┘         │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐       │
│  │  Mortgage Demo                                                │       │
│  │  ┌──────────┐  ┌──────┐  ┌────────┐  ┌──────────┐           │       │
│  │  │ Customer  │  │ Auth │  │  KYC/  │  │   Core   │           │       │
│  │  │  Agent    │──│Agent │  │ Credit │  │ Banking  │           │       │
│  │  │  (hub)    │──│      │  │ Agent  │  │  Agent   │           │       │
│  │  │  :5020    │──│:5021 │  │ :5022/ │  │  :5024   │           │       │
│  │  └──────────┘  └──────┘  │  5023  │  └──────────┘           │       │
│  │       │                  └────────┘       │                  │       │
│  │       │        ┌────────────┐             │                  │       │
│  │       └────────│ Compliance │─────────────┘                  │       │
│  │                │  (CrewAI)  │                                 │       │
│  │                │   :5025    │                                 │       │
│  │                └────────────┘                                 │       │
│  │                                                               │       │
│  │  ┌──────────────┐  ┌──────────┐  ┌───────────────────┐      │       │
│  │  │   Mortgage    │  │ Stub APIs│  │   MCP Servers     │      │       │
│  │  │   Frontend    │  │ (banking │  │ (tool governance) │      │       │
│  │  │   :8031       │  │  mocks)  │  │                   │      │       │
│  │  └──────────────┘  └──────────┘  └───────────────────┘      │       │
│  └──────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Directory structure

```
recursant/
├── registry/              # Control plane
│   ├── app/
│   │   ├── api/           # 11 Flask blueprints (agents, approval, audit, auth,
│   │   │                  #   certificates, consent, dashboard, evaluation,
│   │   │                  #   mesh, security, users)
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Marshmallow schemas
│   │   ├── services/      # Business logic
│   │   └── llm/           # LLM provider abstraction (Anthropic, OpenAI, Google)
│   ├── frontend/          # React + Vite + Tailwind UI
│   ├── test_agent/        # LLM-backed test agent for evaluation
│   ├── scripts/           # Seed scripts (admin user, security tests, eval suites)
│   └── migrations/        # Alembic database migrations
├── mesh/                  # Data plane
│   ├── runtime/
│   │   └── sidecar/       # Sidecar proxy runtime
│   │       ├── interceptors/  # Request/response interceptor pipeline
│   │       ├── app.py         # Flask HTTP server
│   │       ├── server.py      # Dual-listener setup (HTTP + mTLS)
│   │       ├── lifecycle.py   # Agent registration and discovery
│   │       └── registry_client.py  # Policy sync client
│   ├── docker/            # Dockerfiles (sidecar, agent, gateway)
│   └── examples/          # Demo agents A & B with configs
├── demo/mortgage/         # Mortgage origination demo
│   ├── agents/            # Customer, KYC/Credit, Core Banking, Compliance
│   ├── frontend/          # Mortgage demo React frontend
│   ├── mcp_servers/       # MCP tool governance servers
│   ├── stubs/             # Stub banking APIs
│   └── docker/            # Dockerfiles for demo components
└── k8s/                   # Kubernetes deployment
    ├── charts/recursant/  # Helm chart (values, 43 templates)
    ├── scripts/           # Cluster lifecycle and test scripts
    └── webhook/           # Mutating admission webhook for sidecar injection
```

## Control plane (Registry)

The registry is a Flask API backed by PostgreSQL and Redis. It is the single source of truth for agent metadata, policies, and governance state.

### Agent lifecycle

Every agent passes through a governed pipeline before it can participate in the mesh:

```
DRAFT → SUBMITTED → TESTING → EVALUATING → PENDING_APPROVAL → APPROVED → ACTIVE
```

- **DRAFT**: Agent registered, metadata provided.
- **SUBMITTED**: Triggers automated security scanning (prompt injection, data exfiltration, tool abuse — 11 LLM-driven test categories).
- **TESTING**: Security scan in progress.
- **EVALUATING**: LLM-as-a-judge guardrails evaluation against seeded test suites.
- **PENDING_APPROVAL**: Human review required.
- **APPROVED → ACTIVE**: Agent joins the mesh and can communicate with other active agents.

### Key capabilities

- **Security scanning** — Automated tests for prompt injection, data exfiltration, tool abuse, and other attack vectors. Uses LLM calls to probe the agent and regex-based evaluation of responses.
- **Evaluation** — LLM-as-a-judge guardrails testing against configurable evaluation suites. Supports multiple LLM providers (Anthropic, OpenAI, Google).
- **Mesh management** — Sidecar registration, policy distribution, agent discovery, and full audit trail.
- **Tool governance** — MCP tool registration, approval workflows, per-agent tool assignment, and egress rules.
- **Certificate management** — mTLS certificate issuance and rotation for sidecar identities.

### Frontend

React single-page application (Vite + Tailwind CSS) providing dashboards for agent management, approval workflows, security scan results, evaluation reports, mesh visualisation, and audit logs.

## Data plane (Mesh sidecars)

The data plane follows a sidecar proxy pattern — analogous to Istio/Envoy, but purpose-built for AI agents. Every agent pod gets an injected sidecar container that mediates all communication.

### Dual-listener architecture

Each sidecar runs two listeners:

1. **HTTP proxy port** (e.g. 9901) — Agent-facing. The agent sends requests to its sidecar on localhost over plain HTTP.
2. **mTLS A2A port** (e.g. 8443) — Mesh-facing. Sidecars communicate with each other over mutual TLS using the A2A protocol (JSON-RPC 2.0 over HTTPS).

The TLS listener runs in a daemon thread via `werkzeug.serving.make_server()` with a custom handler that extracts peer certificates from the TLS handshake.

### Interceptor pipeline

Every request passes through a chain of interceptors:

```
Request → Authentication → Authorisation → Compliance → PII Redaction
       → Audit → Rate Limiting → Resilience → Target Sidecar
```

| Interceptor | Purpose |
|-------------|---------|
| Authentication | mTLS certificate validation + API key verification |
| Authorisation | Policy-based access control (tool and capability checks) |
| Compliance | CrewAI-powered compliance checking |
| PII Redaction | Detects and redacts personally identifiable information |
| Audit | Immutable request/response logging |
| Rate Limiter | Per-agent rate limiting |
| Fault Injection | Chaos testing support |

Interceptors are individually configurable via the sidecar's YAML config.

### Policy sync

Sidecars poll the registry every 30 seconds to fetch updated policies, tool assignments, and agent discovery information.

### A2A protocol

Agent-to-agent communication uses JSON-RPC 2.0 over HTTP (localhost) or HTTPS (cross-sidecar). The protocol supports task creation, status queries, streaming (SSE), and tool invocations.

## Sidecar injection webhook

A Kubernetes mutating admission webhook automatically injects sidecar containers into annotated pods.

Annotations control injection:

| Annotation | Purpose |
|------------|---------|
| `recursant.io/inject-sidecar: "true"` | Enable single-sidecar injection |
| `recursant.io/inject-sidecars: '<JSON>'` | Inject multiple sidecars (JSON array) |
| `recursant.io/agent-name` | Agent display name |
| `recursant.io/agent-port` | Agent application port |
| `recursant.io/sidecar-config` | ConfigMap name for sidecar YAML config |
| `recursant.io/cert-secret` | Secret name containing mTLS certificates |

The webhook injects: the sidecar container, environment variables (ports, registry URL, API key from secrets), volume mounts for config and TLS certificates, and container port definitions for both HTTP and A2A listeners.

## Networking

```
Agent A ──HTTP──▶ Sidecar A ──mTLS──▶ Sidecar B ──HTTP──▶ Agent B
(localhost)        :9901       A2A       :8444      (localhost)
                   :8443
```

- Agents talk to their own sidecar on **localhost over plain HTTP**.
- Sidecars talk to each other over **mTLS** on A2A ports (8443–8455).
- **NetworkPolicy** blocks direct agent-to-agent traffic, forcing all communication through sidecars.
- **Calico CNI** is required in Kind for NetworkPolicy enforcement (Kind's default kindnet does not support it).

## Mortgage demo

The mortgage origination demo showcases a hub-and-spoke agent topology:

```
                    ┌──────────────────┐
                    │  Customer Agent   │
                    │     (hub)         │
                    └────────┬─────────┘
               ┌─────┬──────┼──────┬─────────┐
               ▼     ▼      ▼      ▼         ▼
            ┌─────┐┌─────┐┌─────┐┌────────┐┌──────────┐
            │Auth ││ KYC ││Cred-││  Core  ││Compliance│
            │     ││     ││ it  ││Banking ││ (CrewAI) │
            └─────┘└─────┘└─────┘└────────┘└──────────┘
             spoke   spoke  spoke   spoke     spoke
```

- **Customer Agent** (hub) orchestrates the mortgage workflow, dispatching tasks to spoke agents.
- **Spoke agents** (Auth, KYC, Credit, Core Banking, Compliance) handle individual domain tasks.
- Spokes **cannot talk to each other** — NetworkPolicy enforces hub-and-spoke topology.
- **Compliance agent** uses [CrewAI](https://www.crewai.com/) for multi-step compliance reasoning.
- **MCP servers** provide tool governance — agents invoke backend systems (stub APIs) through governed MCP tool calls rather than direct HTTP.

## Security model

Recursant enforces a zero-trust security model:

- **Authentication**: All inter-agent traffic is mutually authenticated via mTLS. Sidecar identities are tied to registry-issued certificates.
- **Authorisation**: Policy engine evaluates every request against per-agent rules (allowed targets, permitted tools, capability constraints).
- **PII redaction**: The PII interceptor detects and redacts sensitive data before it leaves the sidecar.
- **Audit**: Every request and response is logged to an immutable audit trail, queryable through the registry API.
- **Network isolation**: Kubernetes NetworkPolicy prevents agents from bypassing their sidecars. All traffic must flow through the mesh.
- **Governance pipeline**: No agent can join the mesh without passing automated security scanning and human approval.
