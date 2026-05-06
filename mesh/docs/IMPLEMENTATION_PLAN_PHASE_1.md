# Phase 1 Implementation Plan: Core Sidecar (MVP)

**Version:** 1.1
**Date:** 2026-02-13
**Goal:** Two LangGraph agents communicating via A2A through Recursant sidecars with basic governance, using the existing Recursant Agent Registry (`../registry`) as the control plane.

---

## 1. End-State Demo Scenario

Before diving into components, here's what Phase 1 delivers:

```
┌───────────────────────────────────────────────────────────┐
│             RECURSANT REGISTRY (Control Plane)             │
│                    ../registry                             │
│                                                           │
│  Existing:          New /v1/mesh/* endpoints:              │
│  ┌──────────────┐   ┌─────────────┐ ┌──────────────────┐  │
│  │ Agent CRUD   │   │ Register /  │ │ Discovery /      │  │
│  │ Security     │   │ Heartbeat / │ │ Policy /         │  │
│  │ Evaluation   │   │ Deregister  │ │ Audit Collection │  │
│  │ Approval     │   └─────────────┘ └──────────────────┘  │
│  └──────────────┘         ▲                 ▲              │
│                           │    REST API     │              │
└───────────────────────────┼─────────────────┼─────────────┘
                            │                 │
          ┌─────────────────┴──┐   ┌──────────┴──────────┐
          ▼                    │   │                      ▼
┌─────────────────────────┐   │   │  ┌─────────────────────────┐
│  Agent Host A            │   │   │  │  Agent Host B            │
│                          │   │   │  │                          │
│  LangGraph Agent         │   │   │  │  LangGraph Agent         │
│  "Research Assistant"    │   │   │  │  "Fact Checker"          │
│  (Claude/GPT/Gemini)     │   │   │  │  (Claude/GPT/Gemini)     │
│       │                  │   │   │  │       ▲                  │
│       │ localhost:9901   │   │   │  │       │ localhost:9901   │
│       ▼                  │   │   │  │       │                  │
│  ┌──────────────┐        │   │   │  │  ┌──────────────┐        │
│  │  Sidecar A   │────────┼───┘   └──┼──│  Sidecar B   │        │
│  │  (port 8443) │◄───────┼──A2A─────┤  │  (port 8444) │        │
│  └──────────────┘        │          │  └──────────────┘        │
└─────────────────────────┘          └─────────────────────────┘
```

Agent A asks Agent B to fact-check a claim. The sidecars handle discovery (via registry), authentication (mTLS), authorisation (policies from registry), audit logging (shipped to registry), and A2A protocol translation — all transparently. The existing Recursant registry serves as the control plane from day one.

---

## 2. Registry as Control Plane

The existing Recursant Agent Registry (`../registry`) already manages agent lifecycle (submission, security testing, evaluation, approval). In Phase 1, we extend it to also serve as the **control plane** for the mesh by adding `/v1/mesh/*` endpoints. This avoids building a mock or separate control plane component.

**The registry provides:**

| Control Plane Function | Registry Capability |
|------------------------|---------------------|
| Agent catalogue & approval | Existing — agents must be ACTIVE to join the mesh |
| Sidecar registration/heartbeat | New — `/v1/mesh/register`, `/v1/mesh/heartbeat`, `/v1/mesh/deregister` |
| Agent discovery by skill | New — `/v1/mesh/discover` (queries existing Capability model) |
| Authorisation policy distribution | New — `/v1/mesh/policies` (serves allow/deny rules to sidecars) |
| Audit log collection | New — `/v1/mesh/audit` (receives audit records from sidecars) |
| Agent Card storage | New — `/v1/mesh/agents/{id}/card` (stores A2A Agent Cards uploaded by sidecars) |

**Key constraint:** Only agents in ACTIVE status (having passed security testing, evaluation, and approval) can register via the mesh endpoints. The mesh registration is a runtime concern — "this approved agent is currently online at this sidecar URL".

---

## 3. Project Directory Structure

```
mesh/
├── REQUIREMENTS.md                          # Architecture spec (exists)
├── docs/
│   └── IMPLEMENTATION_PLAN_PHASE_1.md # This document
├── pyproject.toml                     # Python project config
├── runtime/
│   ├── __init__.py
│   ├── sidecar/
│   │   ├── __init__.py
│   │   ├── app.py                     # Flask app factory + A2A endpoint wiring
│   │   ├── config.py                  # Pydantic config models (YAML + env)
│   │   ├── server.py                  # A2A JSON-RPC server (inbound handler)
│   │   ├── client.py                  # A2A client (outbound requests)
│   │   ├── agent_card.py              # Agent Card loading, enrichment, serving
│   │   ├── registry_client.py         # REST client for registry control plane API
│   │   ├── interceptors/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Base interceptor interface
│   │   │   ├── pipeline.py            # Interceptor chain runner
│   │   │   ├── authentication.py      # mTLS cert validation
│   │   │   ├── authorisation.py       # Policy enforcement (policies from registry)
│   │   │   └── audit.py               # Audit log (local + shipped to registry)
│   │   └── lifecycle.py               # Startup registration, heartbeat, shutdown
│   ├── client/
│   │   ├── __init__.py
│   │   └── a2a_client.py              # RecursantA2AClient for LangGraph agents
│   └── common/
│       ├── __init__.py
│       └── models.py                  # Shared Pydantic models (A2A types, policies)
├── examples/
│   ├── agent_a/
│   │   ├── agent.py                   # LangGraph "Research Assistant" agent
│   │   ├── agent_card.yaml            # Agent Card config
│   │   └── recursant-sidecar.yaml     # Sidecar config
│   └── agent_b/
│       ├── agent.py                   # LangGraph "Fact Checker" agent
│       ├── agent_card.yaml
│       └── recursant-sidecar.yaml
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_interceptors.py
│   │   ├── test_agent_card.py
│   │   ├── test_registry_client.py
│   │   └── test_server.py
│   └── integration/
│       ├── test_a2a_roundtrip.py      # Two sidecars talking to each other
│       └── test_registry_lifecycle.py  # Register → heartbeat → deregister
├── docker/
│   ├── Dockerfile.sidecar             # Sidecar container image
│   └── certs/                         # Dev mTLS certs (generated)
│       ├── ca.pem
│       ├── ca-key.pem
│       └── generate-certs.sh          # Script to generate dev certs
└── docker-compose.yaml                # Full demo: registry + 2 agents + 2 sidecars
```

---

## 4. Implementation Steps

### Step 1: Project Scaffolding & Configuration

**Files:** `pyproject.toml`, `recursant/sidecar/config.py`, `recursant/common/models.py`

**Work:**
- Create `pyproject.toml` with dependencies:
  - `a2a-sdk[http-server]` — official A2A Python SDK
  - `flask` — HTTP server (aligns with registry stack)
  - `pydantic>=2.0` — config validation
  - `pyyaml` — YAML config parsing
  - `cryptography` — mTLS cert handling
  - `httpx` — async HTTP client (used by a2a-sdk)
  - `structlog` — structured JSON logging
  - `pytest`, `pytest-asyncio` — testing
- Implement `SidecarConfig` (Pydantic model) that loads from `recursant-sidecar.yaml`:
  - `port` (local proxy, default 9901)
  - `a2a_port` (external A2A-facing, default 8443)
  - `registry_url` (Recursant registry REST API base URL — the control plane)
  - `registry_api_key` (API key for authenticating to registry)
  - `agent_card_path` (path to local `agent_card.yaml`)
  - `log_level` (debug/info/warn/error)
  - `interceptors` config block (auth, authz, audit — each with `enabled` flag)
  - `tls.cert_path`, `tls.key_path`, `tls.ca_path` for mTLS
  - `policy_sync_interval` (how often to fetch policies from registry, default 30s)
- Define shared Pydantic models in `common/models.py`:
  - `InterceptorDecision` (pass/block/modify + reason)
  - `AuditRecord` (timestamp, source_agent_id, dest_agent_id, task_id, method, message_hash, decision, outcome)
  - `PolicyRule` (source_agent, dest_agent, action: allow/deny)

**Acceptance criteria:**
- `SidecarConfig.from_yaml("recursant-sidecar.yaml")` loads and validates config
- Invalid config raises clear Pydantic validation errors
- Unit tests for config loading

---

### Step 2: Agent Card Loading & Serving

**Files:** `recursant/sidecar/agent_card.py`

**Work:**
- Load agent card from local `agent_card.yaml` (YAML format with fields mapping to A2A `AgentCard` schema)
- Enrich with Recursant governance metadata (add `extensions` field with sidecar version, registry URL, tenant)
- Convert to A2A SDK `AgentCard` type
- Serve at `GET /.well-known/agent.json` (standard A2A discovery endpoint)
- The YAML format should be human-friendly:

```yaml
name: "Fact Checker Agent"
description: "Verifies factual claims using multiple sources"
version: "1.0.0"
provider:
  name: "Recursant"
  url: "https://recursant.ai"
skills:
  - id: "fact-check"
    name: "Fact Check"
    description: "Verifies a factual claim and returns evidence"
    tags: ["verification", "fact-checking"]
    examples: ["Is the Eiffel Tower 330m tall?"]
default_input_modes: ["text"]
default_output_modes: ["text"]
capabilities:
  streaming: false
  push_notifications: false
security_schemes:
  mtls:
    type: "mutualTLS"
security:
  - mtls: []
```

**Acceptance criteria:**
- `GET /.well-known/agent.json` returns valid A2A Agent Card JSON
- Card includes Recursant extension metadata
- Unit tests for YAML loading and enrichment

---

### Step 3: Interceptor Pipeline

**Files:** `recursant/sidecar/interceptors/base.py`, `pipeline.py`, `authentication.py`, `authorisation.py`, `audit.py`

**Work:**

#### 3a: Base interceptor interface

```python
class Interceptor(ABC):
    @abstractmethod
    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        """Inspect/modify/reject an A2A message. Returns pass/block/modify."""
```

`InterceptorContext` holds: direction (inbound/outbound), A2A method name, message payload, source agent ID, destination agent ID, client cert info, task ID.

#### 3b: Pipeline runner

- Ordered chain of interceptors. Runs each in sequence.
- If any interceptor returns `block`, stop processing and return error response.
- If interceptor returns `modify`, pass modified payload to next interceptor.
- Logs structured JSON for every interceptor decision.

#### 3c: Authentication interceptor (FR-S01, FR-S02)

- For inbound requests: extract client certificate from mTLS handshake, validate against trusted CA.
- Extract agent identity (CN or SAN from cert) and attach to `InterceptorContext`.
- Reject requests without valid client cert.
- For Phase 1: also support a simpler API key mode for local development (header `X-Sidecar-API-Key`) so the demo works without full PKI.

#### 3d: Authorisation interceptor (FR-S03, FR-S04)

- Fetch allow/deny policy rules from the registry control plane via `GET /v1/mesh/policies`.
- Cache policies locally with configurable refresh interval (default 30s via `policy_sync_interval`).
- Policies are managed in the registry (admin can define which agents can talk to which via the registry UI or API).
- Match source agent ID + destination agent ID against rules. First match wins.
- Reject if no matching allow rule (default deny).
- Check that source agent is registered in registry (FR-S04) via cached registry data.
- Fall back to static config rules if registry is unreachable (graceful degradation):

```yaml
interceptors:
  authorisation:
    enabled: true
    default_action: deny
    fallback_rules:
      - source: "research-assistant"
        destination: "fact-checker"
        action: allow
```

#### 3e: Audit logging interceptor (FR-A01, FR-A02, FR-A03)

- Create `AuditRecord` for every A2A interaction (inbound and outbound).
- Fields: timestamp, source_agent_id, dest_agent_id, task_id, a2a_method, SHA-256 message hash, interceptor decisions, outcome.
- Write to: structured JSON log file + stdout (structured logging via `structlog`).
- Ship audit records to registry control plane via `POST /v1/mesh/audit` in near-real-time.
- Buffer locally if registry is temporarily unreachable; retry with backoff (at-least-once delivery per NFR-06).

**Acceptance criteria:**
- Pipeline runs interceptors in order; blocks on first rejection
- Auth interceptor validates mTLS certs (and API key fallback)
- Authz interceptor fetches and caches policies from registry; falls back to static config
- Audit interceptor logs all interactions with correct fields and ships to registry
- Unit tests for each interceptor in isolation
- Unit test for pipeline chain behaviour (pass-through, block, modify)

---

### Step 4: A2A Server (Inbound Handler)

**Files:** `recursant/sidecar/server.py`, `recursant/sidecar/app.py`

**Work:**
- Implement Flask routes that handle inbound A2A JSON-RPC requests:
  - `POST /a2a` — main A2A endpoint (handles `message/send`, `tasks/get`, `tasks/cancel` methods)
  - `GET /.well-known/agent.json` — Agent Card (from Step 2)
  - `GET /healthz` — liveness probe (FR-R06)
  - `GET /readyz` — readiness probe (FR-R06); checks registry connectivity
- For each inbound A2A request:
  1. Parse JSON-RPC envelope
  2. Run through interceptor pipeline (inbound direction)
  3. If pipeline passes: forward to the local agent (on `localhost:{agent_port}`)
  4. Return agent's response through the A2A JSON-RPC response envelope
- The sidecar acts as a reverse proxy: external requests arrive on `a2a_port` (8443, mTLS), get intercepted, then forwarded to the local agent.
- Use the `a2a-sdk` types for request/response serialisation (`SendMessageRequest`, `SendMessageResponse`, etc.)
- Flask app factory in `app.py` that wires routes, loads config, initialises interceptors.

**A2A JSON-RPC format:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-123",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "Is the Eiffel Tower 330m tall?"}],
      "messageId": "msg-abc"
    }
  }
}
```

**Acceptance criteria:**
- Sidecar accepts A2A JSON-RPC `message/send` on `/a2a` endpoint
- Interceptor pipeline runs on every inbound request
- Valid requests forwarded to local agent; response relayed back
- Blocked requests return JSON-RPC error response
- Health endpoints return 200 when ready; readyz checks registry
- Unit tests for JSON-RPC parsing and routing

---

### Step 5: A2A Client (Outbound Requests)

**Files:** `recursant/sidecar/client.py`

**Work:**
- Implement outbound A2A client that the sidecar uses to forward requests to remote sidecars.
- Uses `httpx.AsyncClient` with mTLS configuration (client cert + CA).
- For outbound requests:
  1. Agent sends request to local sidecar (via `RecursantA2AClient`, Step 7)
  2. Sidecar resolves destination agent via registry (Step 6)
  3. Run through interceptor pipeline (outbound direction)
  4. If pipeline passes: send A2A JSON-RPC request to destination sidecar's `a2a_port`
  5. Return response to the local agent
- Implements configurable timeouts (FR-R04): default 30s.
- The local proxy endpoint (`POST /a2a/send` on port 9901) is separate from the external A2A endpoint. The local agent calls the sidecar's local port; the sidecar calls the remote sidecar's external port.

**Local proxy endpoint:**
```
POST http://localhost:9901/a2a/send
{
  "skill": "fact-check",
  "message": "Is the Eiffel Tower 330m tall?"
}
```

The sidecar:
1. Looks up "fact-check" skill in registry → resolves to Agent B's sidecar URL
2. Constructs A2A `SendMessageRequest`
3. Runs outbound interceptor pipeline
4. Sends to Agent B's sidecar via mTLS
5. Returns response to caller

**Acceptance criteria:**
- Outbound client sends well-formed A2A JSON-RPC requests
- mTLS client certs sent on outbound connections
- Timeouts enforced
- Outbound interceptor pipeline runs before sending
- Unit tests with mocked HTTP

---

### Step 6: Registry Control Plane Endpoints & Sidecar Client

**Files:** `../registry/app/api/mesh.py`, `../registry/app/models/mesh.py`, `../registry/app/schemas/mesh.py`, `recursant/sidecar/registry_client.py`, `recursant/sidecar/lifecycle.py`

This is the largest step — it adds the mesh control plane API to the existing registry and builds the sidecar client that talks to it.

**Work:**

#### 6a: New registry models (in `../registry`)

Add new models to store mesh runtime state:

```python
class MeshRegistration(db.Model):
    """Runtime sidecar registration — tracks which approved agents are currently online."""
    __tablename__ = 'mesh_registrations'

    id = db.Column(UUID, primary_key=True, default=uuid.uuid4)
    agent_id = db.Column(UUID, db.ForeignKey('agents.id'), nullable=False, unique=True)
    sidecar_url = db.Column(db.String(2048), nullable=False)      # e.g. https://host-a:8443
    agent_card = db.Column(JSON, nullable=False)                   # Full A2A Agent Card
    sovereignty_zone = db.Column(db.String(50), nullable=True)     # e.g. "eu", "us"
    registered_at = db.Column(db.DateTime(timezone=True))
    last_heartbeat = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(20), default='healthy')           # healthy / unhealthy / stale

class MeshPolicy(db.Model):
    """Authorisation policies for agent-to-agent communication."""
    __tablename__ = 'mesh_policies'

    id = db.Column(UUID, primary_key=True, default=uuid.uuid4)
    tenant_id = db.Column(db.String(255), nullable=False, default='default')
    source_agent_name = db.Column(db.String(255), nullable=False)  # agent name or "*"
    dest_agent_name = db.Column(db.String(255), nullable=False)    # agent name or "*"
    action = db.Column(db.String(10), nullable=False)              # "allow" or "deny"
    priority = db.Column(db.Integer, default=0)                    # lower = higher priority
    created_at = db.Column(db.DateTime(timezone=True))

class MeshAuditLog(db.Model):
    """Audit records received from sidecars."""
    __tablename__ = 'mesh_audit_logs'

    id = db.Column(UUID, primary_key=True, default=uuid.uuid4)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    source_agent_id = db.Column(UUID, nullable=False)
    dest_agent_id = db.Column(UUID, nullable=True)
    task_id = db.Column(db.String(255), nullable=True)
    a2a_method = db.Column(db.String(100), nullable=False)
    message_hash = db.Column(db.String(64), nullable=False)        # SHA-256
    decision = db.Column(db.String(20), nullable=False)            # pass / block
    outcome = db.Column(db.String(20), nullable=False)             # success / blocked / error
    details = db.Column(JSON, nullable=True)                       # interceptor decisions, etc.
    sidecar_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True))
```

#### 6b: New registry REST endpoints (in `../registry/app/api/mesh.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/mesh/register` | POST | Sidecar registers its agent on startup. Validates agent is ACTIVE in registry. |
| `/v1/mesh/heartbeat` | POST | Sidecar sends periodic heartbeat. Updates `last_heartbeat`. |
| `/v1/mesh/deregister` | POST | Sidecar deregisters on shutdown. Removes `MeshRegistration`. |
| `/v1/mesh/discover` | GET | Discover agents by skill. Queries existing `Capability` model, joins with `MeshRegistration` to return only online agents. Params: `skill`, `version`, `sovereignty_zone`. |
| `/v1/mesh/agents/{id}/card` | GET | Get agent's A2A Agent Card from `MeshRegistration`. |
| `/v1/mesh/policies` | GET | Get authorisation policies for a tenant. Sidecars poll this. |
| `/v1/mesh/policies` | POST | Create/update a policy rule (admin). |
| `/v1/mesh/audit` | POST | Receive audit records from sidecars. Batch endpoint (accepts array). |
| `/v1/mesh/audit` | GET | Query audit log (for admin UI). |

Register the `mesh` blueprint in `../registry/app/api/__init__.py`.

**Registration payload:**
```json
{
  "agent_id": "uuid",
  "sidecar_url": "https://host-a:8443",
  "agent_card": { "name": "...", "skills": [...], ... },
  "sovereignty_zone": "eu"
}
```

**Registration response:**
```json
{
  "status": "registered",
  "agent_id": "uuid",
  "policies": [
    {"source": "research-assistant", "destination": "fact-checker", "action": "allow"},
    {"source": "*", "destination": "*", "action": "deny"}
  ]
}
```

The registration response includes current policies so the sidecar has them immediately without a separate fetch.

**Discovery response:**
```json
{
  "agents": [
    {
      "agent_id": "uuid",
      "name": "Fact Checker",
      "sidecar_url": "https://host-b:8444",
      "skills": ["fact-check"],
      "version": "1.0.0",
      "status": "healthy",
      "last_heartbeat": "2026-02-13T10:00:00Z"
    }
  ]
}
```

**Heartbeat logic:** A background task (or cron) in the registry marks registrations as `unhealthy` if no heartbeat received for 2 minutes, and `stale` (excluded from discovery) after 5 minutes.

#### 6c: Registry client (in sidecar)

`RegistryClient` — REST client that calls the registry's `/v1/mesh/*` endpoints:
- `register(agent_card)` — called on startup; stores returned policies
- `heartbeat()` — called every 30s (configurable)
- `deregister()` — called on shutdown (SIGTERM handler)
- `discover(skill)` — find agents by skill, returns sidecar URLs
- `fetch_policies()` — fetch latest policies from registry (called on interval)
- `ship_audit(records)` — send batch of audit records to registry
- Local cache with configurable TTL (default 60s) for discovery results (FR-D02)
- Authenticates to registry via API key (header `X-Mesh-API-Key`)

#### 6d: Lifecycle manager

- On startup: load config → load agent card → register with registry (receives policies) → start heartbeat loop → start policy sync loop → start HTTP servers
- On shutdown (SIGTERM/SIGINT): flush pending audit records → stop heartbeat → deregister from registry → graceful HTTP shutdown
- Background tasks: heartbeat loop (30s), policy sync (30s), audit flush (5s)

#### 6e: Database migration

Add Alembic migration for `mesh_registrations`, `mesh_policies`, `mesh_audit_logs` tables.

**Acceptance criteria:**
- Registry mesh endpoints accept register/heartbeat/deregister/discover/policy/audit calls
- Registration rejects agents not in ACTIVE status
- Sidecar registers on startup, heartbeats every 30s, deregisters on shutdown
- Discovery returns only healthy, online agents matching the requested skill
- Policy fetch returns current policies; sidecar caches them
- Audit records are shipped to registry and queryable
- Stale registrations (no heartbeat for 5 min) excluded from discovery
- Integration test: register → discover → deregister lifecycle
- Integration test: audit record roundtrip (sidecar → registry → query)

---

### Step 7: RecursantA2AClient (LangGraph Integration)

**Files:** `recursant/client/a2a_client.py`

**Work:**
- Implement `RecursantA2AClient` — the developer-facing client that LangGraph agents use to communicate via the sidecar.
- Provides a simple, synchronous-friendly API (with async support):

```python
from recursant.client import RecursantA2AClient

client = RecursantA2AClient(sidecar_url="http://localhost:9901")

# Send a task to a remote agent by skill
response = client.send_task(
    skill="fact-check",
    message="Is the Eiffel Tower 330m tall?",
    timeout=30,
)

print(response.status)     # "completed"
print(response.artifacts)  # [{"kind": "text", "text": "Yes, ..."}]
```

- Under the hood: sends `POST http://localhost:9901/a2a/send` with the skill + message.
- Returns a typed response object with status, artifacts, and task ID.
- Handles errors (blocked by policy, destination unreachable, timeout) with clear exceptions:
  - `AuthorisationDeniedError`
  - `AgentNotFoundError`
  - `SidecarTimeoutError`

**Acceptance criteria:**
- Client sends requests to local sidecar
- Response deserialized into typed objects
- Error cases raise appropriate exceptions
- Works both sync and async
- Unit tests with mocked sidecar

---

### Step 8: mTLS Certificate Generation (Dev)

**Files:** `docker/certs/generate-certs.sh`

**Work:**
- Shell script that generates a dev PKI:
  - Root CA cert + key
  - Sidecar A cert + key (CN=`sidecar-a`, SAN=`localhost,host-a`)
  - Sidecar B cert + key (CN=`sidecar-b`, SAN=`localhost,host-b`)
- Uses `openssl` commands (or Python `cryptography` lib)
- Certs are for development only — not production CA
- Sidecar config references these certs:

```yaml
tls:
  cert_path: "/certs/sidecar-a.pem"
  key_path: "/certs/sidecar-a-key.pem"
  ca_path: "/certs/ca.pem"
```

**Acceptance criteria:**
- Script generates valid CA + two sidecar certs
- Certs enable mTLS between two sidecars
- Certs are gitignored (generated at build time)

---

### Step 9: Example LangGraph Agents

**Files:** `examples/agent_a/agent.py`, `examples/agent_b/agent.py`, YAML configs

**Work:**
- **Agent A ("Research Assistant"):** A LangGraph agent that accepts a research query, produces a claim, then uses `RecursantA2AClient` to ask Agent B to fact-check the claim. Returns the combined result.
- **Agent B ("Fact Checker"):** A LangGraph agent that accepts a factual claim and returns a verification result with evidence.
- Both agents are simple LangGraph graphs (3-4 nodes each) using an LLM (configurable: Claude, GPT, or Gemini via environment variable).
- Each agent runs as a standalone A2A server (using `a2a-sdk`'s server utilities) on a local port. The sidecar proxies to this port.
- Each agent has its own `agent_card.yaml` and `recursant-sidecar.yaml`.

**Agent A graph:**
```
START → generate_claim → fact_check_via_sidecar → compile_result → END
```

**Agent B graph:**
```
START → parse_claim → verify_claim → format_evidence → END
```

**Pre-requisite:** Both agents must be registered and ACTIVE in the registry before the demo runs. A seed script (`examples/seed_demo_agents.py`) creates the agent entries in the registry with ACTIVE status, capabilities, and the correct skill names.

**Acceptance criteria:**
- Both agents run standalone and respond to A2A requests
- Agent A successfully calls Agent B through sidecars
- Configurable LLM provider (env var)
- Agent Cards accurately describe their skills
- Seed script creates demo agents in the registry

---

### Step 10: Docker Compose Setup

**Files:** `docker-compose.yaml`, `docker/Dockerfile.sidecar`

**Work:**
- `Dockerfile.sidecar`: Alpine-based Python 3.11+ image, installs the `recursant` package, runs the sidecar process.
- `docker-compose.yaml` with services:
  - `registry-db` — PostgreSQL (shared with existing registry)
  - `registry-redis` — Redis (shared with existing registry)
  - `registry` — existing Recursant registry API (built from `../registry`), serving as control plane
  - `agent-a` — Research Assistant LangGraph agent
  - `sidecar-a` — Recursant Sidecar for Agent A
  - `agent-b` — Fact Checker LangGraph agent
  - `sidecar-b` — Recursant Sidecar for Agent B
  - `seed` — one-shot container that runs `seed_demo_agents.py` to create ACTIVE agent entries + mesh policies in the registry
- Network: all services on same Docker network. Sidecars communicate via mTLS.
- Volumes: mount dev certs into sidecar containers.
- Environment: LLM API key + registry API key passed via env vars.
- Depends-on: sidecars wait for registry; seed runs before sidecars start.

**Service topology:**
```
                        ┌──────────────────────┐
                        │  registry (port 5000) │
                        │  + PostgreSQL + Redis  │
                        │  (Control Plane)       │
                        └──────┬───────┬────────┘
                               │       │
               ┌───────────────┘       └───────────────┐
               ▼                                       ▼
agent-a (5010) ←→ sidecar-a (local:9901, a2a:8443)   sidecar-b (local:9902, a2a:8444) ←→ agent-b (5011)
                              │                                 ▲
                              └──────────── mTLS ───────────────┘
```

**Acceptance criteria:**
- `docker compose up` starts the full demo
- Seed script creates demo agents + policies in registry
- Agent A can call Agent B through sidecars
- Audit logs visible both in sidecar stdout and queryable via registry API
- Health endpoints accessible
- Demo teardown is clean (deregistration on `docker compose down`)

---

### Step 11: Integration Tests

Tests to be run via Makefile targets as with the agent registry

**Files:** `tests/integration/test_a2a_roundtrip.py`, `test_registry_lifecycle.py`

**Work:**
- **A2A roundtrip test:** Start two sidecars (in-process or via subprocess), send a task from Sidecar A to Sidecar B, verify response and audit log entries in registry.
- **Registry lifecycle test:** Register → heartbeat → discover → deregister, verify each step against registry API.
- **Policy enforcement test:** Configure deny policy in registry, verify sidecar fetches it and blocks the request.
- **Audit shipping test:** Send a request through sidecar, verify audit record appears in registry via `GET /v1/mesh/audit`.
- **Interceptor tests:**
  - Verify that unauthenticated request is rejected
  - Verify that unauthorised agent pair is blocked (policy from registry)
  - Verify that audit log contains correct fields
- Tests use pytest fixtures for sidecar/registry setup and teardown.
- Mock LLM calls in agents (don't require API keys for CI).

**Acceptance criteria:**
- All integration tests pass
- Tests are deterministic (no flaky timing issues)
- CI-friendly (no external dependencies beyond Docker)

---

## 5. Requirements Coverage Matrix (Phase 1)

| Requirement | Covered | Implementation |
|-------------|---------|----------------|
| FR-D01 (skill-based discovery) | Yes | Step 6 — registry `/v1/mesh/discover` endpoint |
| FR-D02 (cached lookups, 60s TTL) | Yes | Step 6 — registry client local cache |
| FR-D03 (version-aware routing) | Partial | Discovery returns version; routing by version deferred to Phase 2 |
| FR-D04 (register/deregister) | Yes | Step 6 — lifecycle manager + registry endpoints |
| FR-D05 (heartbeat) | Yes | Step 6 — background heartbeat loop + registry staleness tracking |
| FR-D06 (domain-scoped discovery) | No | Phase 2 |
| FR-S01 (mTLS) | Yes | Step 8 — dev certs; Step 3c — auth interceptor |
| FR-S02 (identity validation) | Yes | Step 3c — cert CN extraction |
| FR-S03 (authz policies) | Yes | Step 3d — policies fetched from registry control plane |
| FR-S04 (reject unregistered) | Yes | Step 3d — registry check via cached mesh registrations |
| FR-S05 (cert rotation) | No | Phase 3 |
| FR-S06 (no credential logging) | Yes | Step 3e — audit interceptor excludes creds |
| FR-A01 (audit every interaction) | Yes | Step 3e |
| FR-A02 (audit record fields) | Yes | Step 3e |
| FR-A03 (ship to control plane) | Yes | Step 3e + Step 6 — audit records shipped to registry |
| FR-A04 (trace context) | No | Phase 2 (OpenTelemetry) |
| FR-R06 (health endpoints) | Yes | Step 4 |

---

## 6. Dependencies & Tech Stack

| Component | Package | Version |
|-----------|---------|---------|
| A2A SDK | `a2a-sdk[http-server]` | latest |
| HTTP server | `flask` | >=3.0 |
| ASGI (for mTLS) | `uvicorn` | >=0.30 |
| HTTP client | `httpx` | >=0.27 |
| Config | `pydantic>=2.0`, `pyyaml` | - |
| Crypto | `cryptography` | >=42.0 |
| Logging | `structlog` | >=24.0 |
| LangGraph | `langgraph` | >=1.0 |
| LLM providers | `langchain-anthropic`, `langchain-openai`, `langchain-google-genai` | latest |
| Testing | `pytest`, `pytest-asyncio`, `pytest-httpx` | - |

---

## 7. Implementation Order & Estimated Effort

| Step | Description | Depends On | Relative Size |
|------|-------------|------------|---------------|
| 1 | Project scaffolding & config | — | Small |
| 2 | Agent Card loading & serving | 1 | Small |
| 3 | Interceptor pipeline | 1 | Medium |
| 4 | A2A server (inbound) | 2, 3 | Medium |
| 5 | A2A client (outbound) | 3 | Medium |
| 6 | Registry control plane endpoints + sidecar client | 1 | Large |
| 7 | RecursantA2AClient | 5 | Small |
| 8 | mTLS cert generation | — | Small |
| 9 | Example LangGraph agents + seed script | 6, 7 | Medium |
| 10 | Docker Compose | 4, 5, 6, 8, 9 | Medium |
| 11 | Integration tests | All | Medium |

**Critical path:** 1 → 3 → 4/5 → 6 → 7 → 9 → 10 → 11

Steps 2 and 8 can be done in parallel with early steps. Step 6 (registry control plane additions) is the largest step since it touches both the existing registry codebase and builds the sidecar client. Consider splitting it: registry models/endpoints first, then sidecar client/lifecycle.

---

## 8. Open Questions / Decisions

1. **Flask vs Starlette for sidecar:** The spec says Flask (aligns with registry), but the `a2a-sdk` has native Starlette support (`A2AStarletteApplication`). Using Flask means we handle JSON-RPC parsing ourselves rather than using the SDK's built-in server. Recommendation: Use Flask for consistency with registry, and use `a2a-sdk` types for serialisation only.

2. **Agent-to-sidecar communication:** Should the local agent also speak A2A to the sidecar (so the sidecar is a pure A2A proxy), or use a simpler REST API (like `POST /a2a/send` with `{skill, message}`)? Recommendation: simpler REST API on the local port for developer ergonomics; A2A protocol only on the external port.

3. **Registry `/v1/mesh/*` auth:** Sidecars authenticate to the registry via API key (`X-Mesh-API-Key` header). A single shared key is configured in the registry's `.env` and distributed to sidecars via their config. Phase 2 can upgrade to per-sidecar mTLS auth.

4. **Agent process model:** Each example agent runs as a separate container (matches the sidecar pattern — sidecar is a companion process, not embedded in the agent).

5. **Registry mesh UI:** Should the registry's existing React frontend get a "Mesh" page showing online agents, audit logs, and policies? Recommendation: yes, minimal — a table of mesh registrations and an audit log viewer. This can be deferred to a fast follow-up if needed.

---

*End of Phase 1 Implementation Plan.*
