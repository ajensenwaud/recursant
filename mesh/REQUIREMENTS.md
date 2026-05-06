# Recursant Agentic Mesh — Sidecar Architecture & Requirements

**Version:** 0.1-draft  
**Date:** 2026-02-13  
**Status:** Architecture specification — original requirements document.
For the current shipping behaviour, see [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
and [`../FEATURES.md`](../FEATURES.md).

-----

## 1. Overview

Recursant is an agentic AI governance and operating platform that provides a federated “agentic mesh” for enterprises running distributed AI agents across multiple platforms (Salesforce AgentForce, LangChain/angGraph, Databricks, ServiceNow, etc.). It enables agents to communicate across domains and platforms via the **A2A protocol** (Google’s Agent2Agent, now a Linux Foundation open standard — v0.3 as of July 2025) while enforcing **centralised policy, security, compliance, and fault handling**.

The architecture is modelled on the **service mesh sidecar pattern** (analogous to Istio/Envoy), where each agent is deployed alongside a lightweight **Recursant Sidecar** that transparently intercepts, governs, and routes all agent-to-agent communication. The sidecar communicates with the **Recursant Control Plane** to receive policy configuration, agent registry data, and compliance rules.

### 1.1 Design Principles

1. **Transparency** — The sidecar intercepts A2A traffic without requiring changes to agent business logic, analogous to how Envoy sidecars in Istio mediate traffic without application code changes (source: [Istio Architecture docs](https://istio.io/latest/docs/ops/deployment/architecture/)).
1. **Centralised governance, federated execution** — Policy, compliance rules, and registry are managed centrally; enforcement happens at the edge via sidecars.
1. **A2A-native** — Communication follows the A2A protocol spec (JSON-RPC 2.0 over HTTP/HTTPS, SSE for streaming, Agent Cards for discovery) as defined by the [A2A project on GitHub](https://github.com/a2aproject/A2A).
1. **LangGraph-first** — Initial implementation targets LangChain/LangGraph agents, with extensibility to other runtimes such as ServiceNow, Crew.AI later on.
1. **Compliance by design** — Every data flow is tracked for GDPR, data sovereignty, and audit purposes as outlined in the Recursant investor thesis.
1. **Zero-trust** — All agent-to-agent communication is authenticated and encrypted (mTLS), with policy-based authorisation at the sidecar level.

### 1.2 Architectural Analogy: Istio → Recursant

|Istio Service Mesh             |Recursant Agentic Mesh             |
|-------------------------------|-----------------------------------|
|Envoy sidecar proxy            |Recursant Sidecar                  |
|Istiod control plane           |Recursant Control Plane            |
|Kubernetes service registry    |Recursant Agent Registry           |
|mTLS between services          |mTLS between agents                |
|Traffic routing rules          |Agent routing & discovery policies |
|Telemetry / distributed tracing|Compliance lineage & audit trails  |
|Circuit breakers / retries     |Agent resilience & failover routing|

-----

## 2. Architecture

### 2.1 High-Level Components

```
┌─────────────────────────────────────────────────────────┐
│                  RECURSANT CONTROL PLANE                 │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │  Policy   │ │  Agent   │ │ Compliance│ │ Telemetry │  │
│  │  Engine   │ │ Registry │ │  Engine   │ │ Collector │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬─────┘  │
│       └─────────────┼───────────┼──────────────┘        │
│                     │    gRPC / xDS-like push            │
└─────────────────────┼───────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│   Agent Host A   │    │   Agent Host B   │
│                  │    │                  │
│ ┌──────────────┐ │    │ ┌──────────────┐ │
│ │  LangGraph   │ │    │ │  LangGraph   │ │
│ │   Agent      │ │    │ │   Agent      │ │
│ └──────┬───────┘ │    │ └──────┬───────┘ │
│        │localhost │    │        │localhost │
│ ┌──────▼───────┐ │    │ ┌──────▼───────┐ │
│ │  Recursant   │ │    │ │  Recursant   │ │
│ │   Sidecar    │◄├────┤►│   Sidecar    │ │
│ │              │ │A2A │ │              │ │
│ └──────────────┘ │    │ └──────────────┘ │
└──────────────────┘    └──────────────────┘
```

### 2.2 Component Descriptions

#### 2.2.1 Recursant Sidecar (Data Plane)

The sidecar is a lightweight process deployed alongside each LangGraph agent. It acts as a **local proxy** that intercepts all outbound A2A requests and inbound A2A messages. Inspired by how Envoy works in Istio — where “each Kubernetes pod gets a proxy that handles all the networking complexities, leaving your application code blissfully unaware” (source: [Istio architecture](https://istio.io/latest/docs/ops/deployment/architecture/)).

**Responsibilities:**

- **A2A protocol handling** — Implements the A2A client and server spec (JSON-RPC 2.0, SSE streaming, Agent Card serving). The A2A spec defines Agent Cards as JSON documents at `/.well-known/agent.json` listing capabilities, endpoints, skills, and auth flows (source: [A2A GitHub spec](https://github.com/a2aproject/A2A)).
- **Agent discovery** — Queries the Recursant Agent Registry to resolve destination agents by skill/capability rather than hardcoded endpoints. Maps to A2A’s Agent Card discovery mechanism. The Recursant registry can be found here: ../registry
- **Policy enforcement** — Applies agnet access control, data classification, rate limiting, and routing rules received from the Control Plane.
- **Data compliance interception** — Inspects message payloads for sensitive data (PII, regulated data), applies data masking/redaction, and enforces sovereignty rules (e.g., data must not leave EU).
- **Audit logging** — Logs every A2A interaction (task creation, message exchange, artifact delivery) with full lineage metadata for regulatory audit.
- **mTLS termination** — Handles mutual TLS for all agent-to-agent traffic, with certificates managed by the Control Plane.
- **Resilience** — Implements circuit breakers, retries with exponential backoff, timeout management, and failover routing to alternative agents.
- **Telemetry emission** — Emits OpenTelemetry (OTLP) traces, metrics, and logs for every interaction. A2A already supports trace IDs and structured OTLP logging (source: [Apono A2A guide](https://www.apono.io/blog/what-is-agent2agent-a2a-protocol-and-how-to-adopt-it/)).

#### 2.2.2 Recursant Control Plane

Analogous to Istiod in Istio (source: [Istio architecture](https://istio.io/latest/docs/ops/deployment/architecture/)), the Control Plane is the central brain that configures all sidecars.

**Sub-components:**

- **Policy Engine** — Defines and distributes access control policies, data handling rules, routing rules, and rate limits to sidecars.
- **Agent Registry** — Central registry of all agents in the mesh, their capabilities (mapped to A2A Agent Card schema), versions, health status, and location. Agents register via their sidecar on startup. The registry has beeb implemented -- see the following folder: ../registry (REQUIREMENTS.md / DEPLOYMENT.md)
- **Compliance Engine** — Manages data classification rules, sovereignty boundaries, GDPR consent tracking, and PII detection models. Pushes compliance policies to sidecars.
- **Telemetry Collector** — Aggregates OpenTelemetry data from all sidecars for monitoring dashboards, alerting, and audit trail storage.
- **Certificate Authority** — Issues and rotates mTLS certificates for sidecar-to-sidecar communication (analogous to Istio’s Citadel component).

#### 2.2.3 Agent Registry (Detail)

The registry has already been built and can be found in the folder "../reigstry". There is a REQUIREMENTS.md describing the design and DEPLOYMENT.md describing how to run it. 

The registry will need to be modified with the reuqirements described in this document, i.e. side car abiltiy to register / deregister.

### 2.3 Observability Architecture

The observability dashboard ("Kiali for Agents") provides a unified view of mesh health, traffic flows, guardrail effectiveness, tool usage, security posture, and cost — combining traditional service mesh observability with AI-specific dimensions that no existing tool covers.

#### 2.3.1 Data Pipeline — Kafka Event Streaming

The observability pipeline uses **Apache Kafka** as the central event bus, replacing the current synchronous REST-based audit submission. This gives true real-time fan-out, backpressure handling, event replay, and independent consumer scaling.

```
┌─────────────┐         ┌──────────────────────────────────────────────────┐
│  Sidecar     │         │                KAFKA CLUSTER                     │
│  Interceptors│         │                                                 │
│              │  produce│  ┌──────────────────┐                           │
│  • A2A calls ├────────►│  │ mesh.audit       │  (partitioned by          │
│  • Tool calls│         │  │                  │   sidecar_id — preserves  │
│  • Egress    │         │  │                  │   hash-chain ordering)    │
│  • Guardrails├────────►│  ├──────────────────┤                           │
│              │         │  │ mesh.guardrails  │  (partitioned by          │
│              │         │  │                  │   agent_name)             │
│              │         │  ├──────────────────┤                           │
│              │         │  │ mesh.registrations│ (single partition —      │
│              │         │  │                  │   low volume)             │
│              │         │  ├──────────────────┤                           │
│              │         │  │ mesh.alerts      │  (produced by anomaly    │
│              │         │  │                  │   detector consumer)      │
│              │         │  ├──────────────────┤                           │
│              │         │  │ mesh.cost        │  (produced by cost       │
│              │         │  │                  │   aggregator consumer)    │
│              │         │  └────────┬─────────┘                           │
└─────────────┘         └───────────┼──────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────────┐
                    │               │                   │
              ┌─────▼─────┐  ┌─────▼──────┐  ┌────────▼────────┐
              │  PG Writer │  │  WS        │  │  Stream         │
              │  Consumer  │  │  Broadcaster│  │  Processors     │
              │            │  │  Consumer  │  │                 │
              │  Writes to │  │  Emits to  │  │  • Anomaly      │
              │  PostgreSQL│  │  Socket.IO │  │    detector     │
              │  (durable  │  │  /mesh     │  │  • Cost         │
              │   storage) │  │  namespace │  │    aggregator   │
              │            │  │            │  │  • Golden       │
              │            │  │            │  │    signals      │
              └─────┬──────┘  └─────┬──────┘  └────────┬────────┘
                    │               │                   │
                    ▼               ▼                   │
              ┌───────────┐  ┌───────────┐              │
              │PostgreSQL │  │ Frontend  │    produces to│
              │           │  │ Dashboard │    mesh.alerts│
              │ mesh_audit│  │ (real-time│    mesh.cost  │
              │  _logs    │  │  updates) │              │
              │ guardrail │  │           │              │
              │  _events  │  │           │◄─────────────┘
              │ mesh_     │  │           │  (via WS broadcaster
              │  anomalies│  │           │   consuming those topics)
              └───────────┘  └───────────┘
```

**Why Kafka:**

1. **True fan-out** — One event published by a sidecar is consumed independently by the PG writer, the WebSocket broadcaster, the anomaly detector, and the cost aggregator. Each consumer reads at its own pace. Adding a new consumer (e.g., a future Grafana exporter) requires zero changes to the existing pipeline.
2. **Backpressure** — If PostgreSQL is slow (table lock, vacuum, spike), events queue in Kafka (retained for configurable duration, default 7 days), not in sidecar memory. No data loss, no sidecar OOM.
3. **Replay** — Any consumer can rewind to any offset. This enables: disaster recovery (replay after PG restore), bootstrapping new consumers (process historical events), and reprocessing (fix a bug in the anomaly detector, replay from last week).
4. **Ordering guarantees** — Partitioning `mesh.audit` by `sidecar_id` ensures hash-chain integrity: all records from a given sidecar arrive in order within their partition.
5. **Horizontal scaling** — Add consumer instances to any consumer group to scale processing independently (e.g., scale PG writers separately from anomaly detectors).

**Topics:**

| Topic | Partition key | Producers | Consumers | Retention |
|-------|--------------|-----------|-----------|-----------|
| `mesh.audit` | `sidecar_id` | Sidecars | PG writer, WS broadcaster, anomaly detector, golden signals | 7 days |
| `mesh.guardrails` | `agent_name` | Sidecars | PG writer, WS broadcaster, effectiveness aggregator | 7 days |
| `mesh.registrations` | `agent_id` | Sidecars | PG writer, WS broadcaster | 7 days |
| `mesh.alerts` | `agent_name` | Anomaly detector | WS broadcaster, PG writer | 30 days |
| `mesh.cost` | `agent_name` | Cost aggregator | WS broadcaster, PG writer | 30 days |

**Consumer groups:**

| Group | Consumes | Responsibility |
|-------|----------|---------------|
| `pg-writer` | `mesh.audit`, `mesh.guardrails`, `mesh.registrations`, `mesh.alerts`, `mesh.cost` | Durable storage to PostgreSQL. Batch inserts (configurable batch size, default 100 records or 1 second, whichever comes first) |
| `ws-broadcaster` | All topics | Emits events to Socket.IO `/mesh` namespace for real-time frontend updates. Stateless — if it falls behind, it catches up automatically |
| `anomaly-detector` | `mesh.audit`, `mesh.guardrails` | Maintains sliding windows in memory. Produces to `mesh.alerts` when thresholds exceeded (traffic spikes >3σ, error bursts >10% for >2min, policy violation surges) |
| `cost-aggregator` | `mesh.audit` | Extracts token/cost data from audit record `details`. Maintains running per-agent/per-model totals. Produces to `mesh.cost` for budget threshold alerts |
| `golden-signals` | `mesh.audit` | Maintains sliding-window counters (request rate, error rate, p50/p95/p99 latency) per agent pair. Frontend queries these via REST endpoint backed by in-memory state |

**Sidecar changes:**

The sidecar's `AuditInterceptor` replaces its HTTP POST buffer flush with a Kafka producer:

- Current: `deque(maxlen=10000)` → periodic `POST /v1/mesh/audit` batch flush
- New: `confluent_kafka.Producer` → produce to `mesh.audit` topic with `key=sidecar_id`
- Hash-chain integrity is preserved: partition key = `sidecar_id` guarantees per-sidecar ordering within a partition
- The `POST /v1/mesh/audit` REST endpoint is retained as a fallback for sidecars that cannot reach Kafka directly (e.g., behind restrictive firewalls). When used, the registry API acts as a Kafka producer proxy

**Registry API changes:**

- The `POST /v1/mesh/audit` endpoint no longer writes to PostgreSQL or broadcasts via WebSocket directly. Instead, it produces to `mesh.audit` topic (Kafka producer proxy mode). This keeps the endpoint backward-compatible while routing through Kafka.
- WebSocket broadcasts are driven by the `ws-broadcaster` consumer group, not by the REST endpoint.
- REST query endpoints (`GET /v1/mesh/observability/*`) continue to read from PostgreSQL (populated by the `pg-writer` consumer).

#### 2.3.2 Real-Time Stream Processing

Instead of batch materialized views, observability aggregations are computed in real-time by Kafka consumer services:

**Golden signals (real-time):** The `golden-signals` consumer group maintains in-memory sliding windows per agent pair. Each audit event updates the counters immediately. The REST endpoint `/v1/mesh/observability/golden-signals` reads from this in-memory state — zero query latency, zero staleness. State is rebuilt from Kafka on consumer restart (replay from topic).

**Cost tracking (real-time):** The `cost-aggregator` consumer extracts `input_tokens`, `output_tokens`, `model_name`, and `estimated_cost_usd` from audit record `details` JSON. Running totals per agent per model are maintained in memory and periodically checkpointed to PostgreSQL. Budget threshold alerts are produced to `mesh.cost` topic immediately when thresholds are crossed.

**Anomaly detection (real-time):** The `anomaly-detector` consumer maintains 7-day rolling baselines per agent. Anomalies are detected within seconds of the triggering event and published to `mesh.alerts` — no batch delay.

**Guardrail effectiveness (real-time):** Block rate, false positive rate, and trigger counts per guardrail per attack category are maintained as running counters by a consumer in the `golden-signals` group. Updated on every guardrail event.

**Historical queries:** For time-range queries (charts, reports, trace views), the dashboard queries PostgreSQL directly. The `pg-writer` consumer ensures PostgreSQL is populated within seconds of each event. Indexes on `(tenant_id, timestamp)`, `task_id`, and `(source_agent_name, dest_agent_name)` keep these queries fast. No materialized views are needed — the volume that PostgreSQL handles for historical queries is modest compared to the real-time stream processing load.

#### 2.3.3 Trace Reconstruction

End-to-end request traces are reconstructed by following `task_id` across `mesh_audit_logs`. Each audit record already contains `source_agent_name`, `dest_agent_name`, `task_id`, `timestamp`, `latency_ms`, and interceptor decisions in the `details` JSON. No external tracing system (Jaeger, Zipkin) is needed — the existing audit data is sufficient for trace visualization.

A trace is the ordered sequence of audit records sharing the same `task_id`, sorted by timestamp. The trace view renders this as a waterfall/flame graph showing each hop, its latency, and interceptor decisions.

#### 2.3.4 Cost & Token Tracking

Extend the audit record `details` JSON to include token consumption data when available:

```json
{
  "input_tokens": 1250,
  "output_tokens": 340,
  "model_name": "claude-sonnet-4-5-20250929",
  "estimated_cost_usd": 0.0089
}
```

Sidecars extract this from LLM API response headers/metadata when proxying tool calls or from agent-reported metrics. Cost estimation uses a configurable model pricing table maintained in the registry.

#### 2.3.5 Frontend Architecture

The observability UI lives within the existing React frontend as a tabbed container:

```
┌─────────────────────────────────────────────────────────────────┐
│  ObservabilityShell                                             │
│  ┌──────────┬────────┬───────────┬───────┬──────────┬────────┐  │
│  │ Topology │ Traces │ Guardrails│ Tools │ Security │  Cost  │  │
│  └──────────┴────────┴───────────┴───────┴──────────┴────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                                                             │ │
│  │              Active tab content area                        │ │
│  │                                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Six views:**
1. **Topology** — Animated mesh graph with traffic particles, mTLS indicators, guardrail overlays, health cards, tool use
2. **Traces** — Waterfall/flame graph of request flows across agents, with interceptor decision timeline
3. **Guardrails** — Effectiveness matrix heatmap, false positive tracking, guardrail comparison (extends existing guardrail dashboard)
4. **Tools** — Tool usage topology, MCP server health, latency/error tracking, permission matrix
5. **Security** — Real-time alert feed, adversarial test results, composite security posture score
6. **Cost** — Per-agent token charts, cost breakdown by model/agent/period, budget tracking, projections

**Rendering strategy:** The topology view uses a hybrid canvas + SVG approach:
- HTML5 Canvas for particle animations (traffic flow dots moving along edges) and background rendering — high performance at scale
- SVG overlays for interactive node elements (click, hover, tooltips) — accessible and styleable
- This mirrors the approach used by Kiali and other production graph visualizers

#### 2.3.6 Backend Services

**Kafka consumer services** (standalone processes, deployed as separate containers/pods):

| Service | Consumer group | Consumes | Responsibility |
|---------|---------------|----------|---------------|
| `pg_writer.py` | `pg-writer` | All topics | Batch-insert events to PostgreSQL. Configurable batch size (default 100) and flush interval (default 1s). Handles backpressure by letting Kafka buffer. |
| `ws_broadcaster.py` | `ws-broadcaster` | All topics | Emit events to Socket.IO `/mesh` namespace. Stateless — reads from Kafka, emits to connected WebSocket clients. Replaces the current inline `socketio.emit()` calls in the REST endpoints. |
| `anomaly_detector.py` | `anomaly-detector` | `mesh.audit`, `mesh.guardrails` | Maintain 7-day rolling baselines per agent. Detect traffic spikes (>3σ), error bursts (>10% for >2min), policy violation surges. Produce alerts to `mesh.alerts` topic. |
| `cost_aggregator.py` | `cost-aggregator` | `mesh.audit` | Extract token/cost data from audit `details`. Maintain running per-agent/per-model totals. Produce budget threshold alerts to `mesh.cost`. Checkpoint state to PostgreSQL periodically. |
| `golden_signals.py` | `golden-signals` | `mesh.audit`, `mesh.guardrails` | Maintain in-memory sliding-window counters (request rate, error rate, latency percentiles, guardrail effectiveness) per agent pair. Expose state via REST endpoint. Rebuild from Kafka on restart. |

**Registry API services** (within the Flask app, query PostgreSQL for historical data):

| Service | Responsibility |
|---------|---------------|
| `trace_service.py` | Reconstruct traces from audit logs by task_id; compute per-hop latency |
| `alert_service.py` | Query and manage alerts (acknowledge, dismiss); read from `mesh_anomalies` table |
| `security_posture_service.py` | Compute composite security score from mTLS coverage, guardrail coverage, scan results, open anomaly count |

#### 2.3.7 New API Endpoints

All endpoints under `/v1/mesh/observability/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/traces/{task_id}` | GET | Full trace waterfall for a task |
| `/traces` | GET | List recent traces (paginated, filterable by agent/status/time) |
| `/golden-signals` | GET | Golden signals for all agent pairs (time range param) |
| `/golden-signals/{agent_name}` | GET | Golden signals for a specific agent |
| `/cost/summary` | GET | Cost summary by agent/model/period |
| `/cost/timeseries` | GET | Cost time series for charting |
| `/cost/budgets` | GET/PUT | Budget configuration and current spend |
| `/alerts` | GET | Active and recent alerts |
| `/alerts/{id}/acknowledge` | POST | Acknowledge an alert |
| `/security/posture` | GET | Composite security posture score and breakdown |
| `/security/anomalies` | GET | Detected anomalies |
| `/tools/metrics` | GET | Tool usage metrics (call count, latency, error rate) |
| `/tools/effectiveness` | GET | Guardrail × attack category effectiveness matrix |

#### 2.3.8 New Database Objects

**New table — `mesh_anomalies`:**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| tenant_id | VARCHAR | Tenant identifier |
| anomaly_type | VARCHAR | Type: `traffic_spike`, `error_burst`, `cost_anomaly`, `new_agent`, `policy_violation_surge` |
| severity | VARCHAR | `low`, `medium`, `high`, `critical` |
| agent_name | VARCHAR | Affected agent (nullable for mesh-wide anomalies) |
| description | TEXT | Human-readable description |
| details | JSON | Raw data supporting the anomaly detection |
| detected_at | TIMESTAMP | When the anomaly was detected |
| resolved_at | TIMESTAMP | When the anomaly was resolved (nullable) |
| is_acknowledged | BOOLEAN | Whether an operator has acknowledged it |

**New column on `guardrail_events`:**

- `is_false_positive` (BOOLEAN, default NULL) — Allows operators to mark guardrail triggers as false positives for effectiveness tracking.

No materialized views are needed — golden signals, cost aggregations, and guardrail effectiveness metrics are computed in real-time by Kafka stream processing consumers (see Section 2.3.2) and served from in-memory state. Historical queries hit PostgreSQL directly with existing indexes.

#### 2.3.9 WebSocket Event Types

All WebSocket events are now driven by the `ws-broadcaster` Kafka consumer (not inline in REST endpoints). The consumer subscribes to all Kafka topics and emits to the Socket.IO `/mesh` namespace:

| Event type | Kafka source topic | Payload | Purpose |
|------------|-------------------|---------|---------|
| `audit` | `mesh.audit` | `{source_agent_name, dest_agent_name, a2a_method, outcome, decision, task_id, timestamp}` | Live audit feed, topology edge animation |
| `guardrail-event` | `mesh.guardrails` | `{guardrail_name, agent_name, action, mechanism, latency_ms, timestamp}` | Guardrail effectiveness live updates |
| `registration` | `mesh.registrations` | `{type, agent_id, agent_name, sidecar_url, sovereignty_zone}` | Topology node add/remove |
| `alert` | `mesh.alerts` | `{alert_id, severity, anomaly_type, agent_name, description}` | Real-time alert notifications |
| `cost-event` | `mesh.cost` | `{agent_name, model_name, input_tokens, output_tokens, estimated_cost_usd}` | Live cost ticker |
| `heartbeat` | (internal timer) | `{timestamp}` | Connection keepalive |

The existing `audit`, `guardrail-event`, `registration`, and `heartbeat` event types are preserved. The `alert` and `cost-event` types are new.

-----

## 3. Sidecar Detailed Design

### 3.1 Sidecar Process Architecture

```
┌─────────────────────────────────────────────────────┐
│                  RECURSANT SIDECAR                   │
│                                                     │
│  ┌─────────────┐          ┌─────────────────────┐   │
│  │  A2A Server  │◄─inbound─┤  mTLS Termination   │◄──── from other sidecars
│  │  (JSON-RPC)  │          └─────────────────────┘   │
│  └──────┬──────┘                                    │
│         │                                           │
│  ┌──────▼──────────────────────────────────────┐    │
│  │            Interceptor Pipeline              │    │
│  │                                              │    │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐  │    │
│  │  │ AuthZ  │→│Compliance│→│ Data   │→│Audit │  │    │
│  │  │ Check  │ │ Check   │ │Redact  │ │ Log  │  │    │
│  │  └────────┘ └────────┘ └────────┘ └──────┘  │    │
│  └──────┬──────────────────────────────────────┘    │
│         │                                           │
│  ┌──────▼──────┐          ┌─────────────────────┐   │
│  │  A2A Client  │─outbound─►│  mTLS Origination   │───► to other sidecars
│  │  (JSON-RPC)  │          └─────────────────────┘   │
│  └──────┬──────┘                                    │
│         │                                           │
│  ┌──────▼──────┐  ┌────────────┐  ┌──────────────┐  │
│  │  Registry   │  │  Config    │  │  Telemetry   │  │
│  │  Client     │  │  Sync      │  │  Emitter     │  │
│  │  (discover) │  │  (xDS/gRPC)│  │  (OTLP)      │  │
│  └─────────────┘  └────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 3.2 Interceptor Pipeline (Middleware Chain)

Every inbound and outbound A2A message passes through a configurable middleware chain. Each interceptor can **pass**, **modify**, or **reject** a message.

**Interceptors (in order):**

1. **Authentication interceptor** — Validates mTLS client certificates or OAuth2 tokens. Rejects unauthenticated requests.
1. **Authorisation interceptor** — Checks the calling agent’s identity against the policy engine’s access control rules (e.g., “agent X in domain Y can invoke skill Z on agent W”).
1. **Compliance interceptor** — Evaluates the message against compliance rules:
- Data sovereignty: Is the destination agent in an allowed sovereignty zone?
- Data classification: Does the message contain data classified above the destination agent’s clearance?
- Consent: For GDPR, has data subject consent been recorded for this data flow?
1. **Data redaction interceptor** — Scans message payloads for PII (names, emails, account numbers, etc.) and applies redaction or tokenisation based on policy. Uses configurable PII detection (regex + optional NER model).
1. **Audit logging interceptor** — Creates an immutable audit record containing: source agent, destination agent, timestamp, task ID, message hash, compliance decisions, data classifications detected, and outcome.
1. **Rate limiting interceptor** — Enforces per-agent and per-domain rate limits.
1. **Resilience interceptor** (outbound only) — Applies circuit breaker logic, retry policies, and failover routing.

### 3.3 Integration with LangGraph Agents

LangGraph organises agent logic as directed graphs with nodes (agent steps) and edges (control flow) supporting cycles, conditionals, and parallel execution (source: [LangChain blog](https://blog.langchain.com/langchain-langgraph-1dot0/)). The sidecar integrates with LangGraph agents in two ways:

#### 3.3.1 Transparent Proxy Mode (Recommended)

The sidecar runs as a separate process on `localhost`. The LangGraph agent is configured to send all A2A requests to `http://localhost:{SIDECAR_PORT}/a2a` instead of directly to remote agents. The sidecar handles discovery, routing, security, and compliance transparently.

```python
# In the LangGraph agent's tool definition
from recursant.client import RecursantA2AClient

# Client points to local sidecar, not directly to remote agents
client = RecursantA2AClient(sidecar_url="http://localhost:9901")

# Agent discovers and calls remote agent by skill — the sidecar
# resolves the actual destination via the Agent Registry
async def call_remote_agent(task_description: str, required_skill: str):
    """Tool node in LangGraph that calls a remote agent via the sidecar."""
    response = await client.send_task(
        skill=required_skill,
        message=task_description,
        # Sidecar handles: discovery, auth, compliance, routing, audit
    )
    return response.artifacts
```

#### 3.3.2 LangGraph Custom Node Mode

For deeper integration, Recursant provides a custom LangGraph node that wraps sidecar communication:

```python
from langgraph.graph import StateGraph, START, END
from recursant.langgraph import RecursantA2ANode

# Define the graph
builder = StateGraph(AgentState)

# Add a Recursant-managed remote agent call as a graph node
builder.add_node(
    "check_credit_score",
    RecursantA2ANode(
        skill="credit-score-check",
        sidecar_port=9901,
        timeout_seconds=30,
        fallback_skill="credit-score-check-v2",  # Resilience
    )
)

builder.add_edge(START, "check_credit_score")
builder.add_edge("check_credit_score", "process_application")
# ...
graph = builder.compile()
```

### 3.4 Agent Card Management

Each sidecar serves the A2A Agent Card for its associated agent at `/.well-known/agent.json`. The sidecar enriches the base Agent Card (defined by the agent developer) with Recursant governance metadata and registers it with the central registry on startup.

**Lifecycle:**

1. Agent starts → Sidecar reads local `agent_card.yaml` config
1. Sidecar registers with registry (gRPC handshake, mTLS)
1. Register issues certificate, returns policy config
1. Sidecar publishes enriched Agent Card to Control Plane 
1. Sidecar begins serving A2A endpoints and heartbeating
1. On shutdown → Sidecar deregisters from the registry

### 3.5 A2A Protocol Mapping

The sidecar implements the full A2A v0.3 spec (source: [Google Cloud blog, July 2025](https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade)):

|A2A Method                            |Sidecar Behaviour                                                       |
|--------------------------------------|------------------------------------------------------------------------|
|`tasks/send`                          |Intercept → pipeline → route to destination sidecar                     |
|`tasks/sendSubscribe` (SSE)           |Intercept → pipeline → establish SSE stream to destination, relay events|
|`tasks/get`                           |Query local task store or proxy to destination                          |
|`tasks/cancel`                        |Propagate cancellation, log audit event                                 |
|`tasks/pushNotification/set`          |Register push notification endpoint with destination via sidecar        |
|Agent Card (`/.well-known/agent.json`)|Served by sidecar with enriched metadata                                |

### 3.6 Configuration

Sidecar configuration is delivered via two channels:

**Static config** (`recursant-sidecar.yaml` — deployed with agent):

```yaml
recursant:
  sidecar:
    port: 9901                          # Local proxy port
    a2a_port: 8443                      # External A2A-facing port (mTLS)
    control_plane_url: "grpcs://control.recursant.ai:443"
    agent_card_path: "./agent_card.yaml"
    log_level: "info"
    
    interceptors:
      authentication:
        enabled: true
        schemes: ["mtls", "oauth2"]
      compliance:
        enabled: true
        pii_detection: "regex"          # or "ner_model"
      audit:
        enabled: true
        storage: "control_plane"        # logs shipped to control plane
      rate_limiting:
        enabled: true
      resilience:
        circuit_breaker:
          failure_threshold: 5
          recovery_timeout_seconds: 30
        retry:
          max_attempts: 3
          backoff_base_seconds: 1
```

**Dynamic config** (pushed from Control Plane via gRPC stream):

- Access control policies (which agents can talk to which)
- Data classification rules and sovereignty boundaries
- Rate limits (per-agent, per-domain)
- Failover routing tables
- Certificate rotations

-----

## 4. Functional Requirements

### 4.1 Agent Discovery & Routing

|ID    |Requirement                                                                                                   |Priority|
|------|--------------------------------------------------------------------------------------------------------------|--------|
|FR-D01|Sidecar SHALL resolve destination agents by skill/capability via the Agent Registry, not by hardcoded endpoint|P0      |
|FR-D02|Sidecar SHALL cache registry lookups locally with configurable TTL (default 60s)                              |P0      |
|FR-D03|Sidecar SHALL support version-aware routing (e.g., route to v2.x of an agent if v1.x is deprecated)           |P1      |
|FR-D04|Sidecar SHALL register its agent’s Agent Card with the registry on startup and deregister on shutdown         |P0      |
|FR-D05|Sidecar SHALL send periodic heartbeats to the registry (default every minute)                                 |P0      |
|FR-D06|Sidecar SHALL support domain-scoped discovery (agent can only discover agents it is authorised to see)        |P1      |

NB: The registry (found in "../registry) will need to be modidfied so it supports the abov requriements with support for sidecar registration, heartbeat, and deregistration. This should take place via API calls.

### 4.2 Security

|ID    |Requirement                                                                                                   |Priority|
|------|--------------------------------------------------------------------------------------------------------------|--------|
|FR-S01|All sidecar-to-sidecar communication SHALL use mTLS with certificates issued by the Recursant CA              |P0      |
|FR-S02|Sidecar SHALL validate the identity of calling agents via mTLS client certificate or OAuth2 bearer token      |P0      |
|FR-S03|Sidecar SHALL enforce authorisation policies received from the Control Plane before forwarding any A2A message|P0      |
|FR-S04|Sidecar SHALL reject any A2A request from an agent not registered in the Agent Registry                       |P0      |
|FR-S05|Sidecar SHALL support automatic certificate rotation without agent restart                                    |P1      |
|FR-S06|Sidecar SHALL never log or persist raw credentials, tokens, or private keys                                   |P0      |

### 4.3 Compliance & Data Governance

|ID    |Requirement                                                                                                                |Priority|
|------|---------------------------------------------------------------------------------------------------------------------------|--------|
|FR-C01|Sidecar SHALL inspect outbound message payloads for PII and sensitive data based on configurable rules                     |P0      |
|FR-C02|Sidecar SHALL block or redact data flows that violate sovereignty rules (e.g., EU personal data to non-EU agent)           |P0      |
|FR-C03|Sidecar SHALL enforce data classification levels — an agent with “internal” clearance SHALL NOT receive “confidential” data|P0      |
|FR-C04|Sidecar SHALL track GDPR consent metadata and block data flows where consent is not recorded                               |P1      |
|FR-C05|Compliance decisions SHALL be included in audit log entries                                                                |P0      |
|FR-C06|Sidecar SHALL support pluggable PII detection (regex-based for v1, NER model-based for v2)                                 |P1      |

### 4.4 Audit & Lineage

|ID    |Requirement                                                                                                                                                                                                        |Priority|
|------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
|FR-A01|Sidecar SHALL create an immutable audit record for every A2A interaction (inbound and outbound)                                                                                                                    |P0      |
|FR-A02|Each audit record SHALL include: timestamp, source agent ID, destination agent ID, task ID, A2A method, message hash (SHA-256), compliance decision, data classifications detected, outcome (success/blocked/error)|P0      |
|FR-A03|Audit records SHALL be shipped to the Control Plane telemetry collector in near-real-time                                                                                                                          |P0      |
|FR-A04|Sidecar SHALL propagate distributed trace context (W3C Trace Context / OpenTelemetry) across all A2A calls                                                                                                         |P0      |
|FR-A05|Audit trail SHALL support full end-to-end lineage reconstruction: given a task ID, reconstruct the complete chain of agent interactions                                                                            |P1      |
|FR-A06|Audit records SHALL be tamper-evident (hash-chained or signed)                                                                                                                                                     |P2      |

### 4.5 Resilience & Fault Handling

|ID    |Requirement                                                                                                                                                   |Priority|
|------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|
|FR-R01|Sidecar SHALL implement circuit breaker pattern: after N consecutive failures to a destination, stop sending for a configurable recovery period               |P0      |
|FR-R02|Sidecar SHALL retry failed A2A requests with exponential backoff (configurable max attempts and base interval)                                                |P0      |
|FR-R03|Sidecar SHALL support failover routing to alternative agents (as specified in registry metadata `failover_agents`) when the primary destination is unavailable|P0      |
|FR-R04|Sidecar SHALL enforce configurable timeouts for A2A requests (default 30s for sync, 300s for long-running tasks)                                              |P0      |
|FR-R05|Sidecar SHALL continue serving cached registry data if the Control Plane is temporarily unreachable (graceful degradation)                                    |P1      |
|FR-R06|Sidecar SHALL emit health status (`/healthz`, `/readyz`) endpoints for container orchestration                                                                |P0      |

### 4.6 Observability

|ID    |Requirement                                                                                                            |Priority|
|------|-----------------------------------------------------------------------------------------------------------------------|--------|
|FR-O01|Sidecar SHALL emit OpenTelemetry traces (OTLP) for every A2A interaction                                               |P0      |
|FR-O02|Sidecar SHALL emit metrics: request count, latency histogram, error rate, circuit breaker state — per destination agent|P0      |
|FR-O03|Sidecar SHALL emit structured logs (JSON) for all interceptor decisions                                                |P0      |
|FR-O04|Sidecar SHALL expose a Prometheus-compatible `/metrics` endpoint                                                       |P1      |
|FR-O05|Sidecar SHALL support configurable log levels (debug, info, warn, error) via Control Plane dynamic config              |P0      |

### 4.7 Unified Observability Dashboard (Kiali for Agents)

Requirements for the observability dashboard described in Section 2.3. Organized by view.

#### 4.7.1 Unified Topology View

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V01 | Topology SHALL render agents as interactive nodes and A2A connections as edges, with animated particle dots flowing along edges to represent live traffic direction and volume | P0 |
| FR-V02 | Each edge SHALL display mTLS status (locked padlock icon for mTLS-verified, warning icon for plaintext or cert-expired) | P0 |
| FR-V03 | Agents with active guardrails SHALL display a shield overlay icon; clicking the shield navigates to that agent's guardrail detail in the Guardrail Effectiveness Center | P1 |
| FR-V04 | A policy overlay toggle SHALL highlight sovereignty zone boundaries, blocked cross-zone connections (red dashed lines), and allowed cross-zone connections (green) | P1 |
| FR-V05 | A time-machine slider SHALL allow replaying topology state and traffic patterns over a configurable historical window (default: last 24 hours) | P2 |
| FR-V06 | Each agent node SHALL display a health card on hover/click showing golden signals: request rate, error rate, p95 latency, and availability (green/yellow/red) | P0 |
| FR-V07 | Agents SHALL be visually clustered by sovereignty zone (EU, US, APAC) with labeled zone boundaries | P1 |
| FR-V08 | Clicking an agent node SHALL navigate to a detail panel showing agent metadata, recent traces, guardrail status, and cost summary | P0 |
| FR-V09 | The topology SHALL perform smoothly with 200+ agent nodes using canvas rendering for particles and virtualized SVG for nodes | P1 |
| FR-V10 | Tools and MCP servers SHALL be rendered as distinct node types in the topology (different shape/icon from agent nodes — e.g., hexagon for tools, diamond for MCP servers). Edges from agents to tools SHALL show tool call traffic with the same particle animation as A2A edges | P0 |
| FR-V11 | Tool nodes SHALL display health status (healthy/degraded/unreachable) based on recent call success rate, and SHALL show call count, p95 latency, and error rate on hover/click | P0 |
| FR-V12 | MCP server nodes SHALL group their child tools visually (collapsible cluster). Expanding an MCP server node reveals its individual tools; collapsing shows the server as a single node with aggregate metrics | P1 |

#### 4.7.2 Request Trace View

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V13 | Given a `task_id`, the trace view SHALL render a waterfall/flame graph showing every hop across agents, with per-hop duration bars | P0 |
| FR-V14 | Each hop SHALL display interceptor decision rows (auth, compliance, data redaction, guardrail) with pass/block/modify indicators | P0 |
| FR-V15 | For hops involving LLM calls, the trace view SHALL display chain-of-thought audit data inline (expandable) if present in the audit record | P1 |
| FR-V16 | Per-hop latency SHALL be displayed as horizontal bars proportional to duration, with total end-to-end latency shown at the top | P0 |
| FR-V17 | Traces SHALL be accessible from: topology view (click an edge), audit log (click a task_id), and direct URL (`/observability/traces/{task_id}`) | P0 |

#### 4.7.3 Guardrail Effectiveness Center

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V18 | The existing guardrail dashboard (guardrail event list, block/allow counts) SHALL be preserved as a sub-view within the Guardrails tab | P0 |
| FR-V19 | An effectiveness matrix heatmap SHALL display guardrails (rows) × attack categories (columns), with cell color intensity representing block rate. Cells SHALL be clickable to drill into individual events | P0 |
| FR-V20 | Operators SHALL be able to mark guardrail events as false positives (`is_false_positive` flag), and the effectiveness matrix SHALL display false positive rates alongside block rates | P1 |
| FR-V21 | A guardrail comparison view SHALL allow selecting 2-3 guardrails and displaying their block rates, latency overhead, and false positive rates side-by-side | P2 |

#### 4.7.4 Tool & MCP Observatory

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V22 | Per-tool detailed metrics SHALL be displayed in a dedicated view: call count, p50/p95 latency, error rate, last called timestamp, calling agents breakdown | P0 |
| FR-V23 | A tool permission matrix SHALL display which agents have access to which tools (derived from `MeshToolAssignment`), with status indicators (approved, suspended, unassigned) | P1 |

Note: Tool and MCP server topology rendering is covered in the Unified Topology View (Section 4.7.1) — tools and MCP servers appear as first-class nodes in the mesh graph, not only in this tab.

#### 4.7.5 Security Command Center

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V24 | A real-time alert feed SHALL display anomalies and policy violations as they are detected, with severity-colored badges and acknowledge/dismiss actions | P0 |
| FR-V25 | Adversarial test results from the security scan pipeline SHALL be summarized showing pass/fail counts by attack category, with drill-through to individual test details | P1 |
| FR-V26 | A composite security posture score (0-100) SHALL be computed from: mTLS coverage, guardrail coverage, recent scan pass rate, open anomaly count, policy violation rate. Breakdown visible on hover | P1 |
| FR-V27 | Anomaly detection SHALL flag: traffic spikes (>3σ from 7-day baseline), error bursts (>10% error rate sustained >2min), new unregistered agents, policy violation surges, cost anomalies | P1 |

#### 4.7.6 Cost & Resource Dashboard

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-V28 | Audit records for LLM-proxied calls SHALL include `input_tokens`, `output_tokens`, `model_name`, and `estimated_cost_usd` in the `details` JSON | P0 |
| FR-V29 | Per-agent token consumption SHALL be displayed as time-series charts (hourly/daily granularity) with model breakdown | P0 |
| FR-V30 | Cost breakdown SHALL be viewable by: model, agent, sovereignty zone, and time period (day/week/month) | P0 |
| FR-V31 | Budget tracking SHALL compare actual spend against configurable per-agent and mesh-wide quotas, with visual indicators (green/yellow/red) and alerts at 80%/90%/100% thresholds | P1 |
| FR-V32 | Cost anomaly detection SHALL flag agents whose spend exceeds 2× their 7-day rolling average | P1 |
| FR-V33 | Projected monthly cost SHALL be estimated from the trailing 7-day average and displayed alongside actual spend | P2 |

-----

## 5. Non-Functional Requirements

|ID    |Requirement                             |Target                                                           |
|------|----------------------------------------|-----------------------------------------------------------------|
|NFR-01|Sidecar added latency per request       |< 5ms p99 (excluding network)                                    |
|NFR-02|Sidecar memory footprint                |< 128 MB baseline                                                |
|NFR-03|Sidecar CPU overhead                    |< 0.25 vCPU at 100 req/s                                         |
|NFR-04|Startup time (sidecar ready to serve)   |< 3 seconds                                                      |
|NFR-05|Control Plane config propagation latency|< 2 seconds to all sidecars                                      |
|NFR-06|Audit log delivery guarantee            |At-least-once (buffered locally if Control Plane unavailable)    |
|NFR-07|Availability target                     |99.99% (sidecar should not be a single point of failure)         |
|NFR-08|Language / runtime                      |Python 3.11+ (aligned with LangGraph ecosystem)                  |
|NFR-09|Containerisation                        |Docker image, Kubernetes-native deployment with sidecar injection|
|NFR-10|A2A protocol version                    |v0.3+ (gRPC + HTTP/JSON-RPC)                                     |

-----

## 6. Technology Stack (Initial Implementation)

|Component                 |Technology                                        |Rationale                                                                                                                                                  |
|--------------------------|--------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
|Sidecar runtime           |Python 3.11+ / `asyncio`                          |Alignment with LangGraph/LangChain ecosystem (both Python-native)                                                                                          |
|A2A protocol              |`a2a-python` SDK                                  |Official A2A Python SDK (source: [A2A GitHub](https://github.com/a2aproject/A2A))                                                                          |
|HTTP server               |`Flask` + `uvicorn`                             |High-performance async HTTP, native SSE support for A2A streaming                                                                                          |
|gRPC (Control Plane comms)|`grpcio` / `grpcio-tools`                         |Control Plane config sync and registry operations                                                                                                          |
|mTLS                      |Python `ssl` module + `cryptography` lib          |Certificate handling and TLS termination                                                                                                                   |
|Telemetry                 |`opentelemetry-sdk`, `opentelemetry-exporter-otlp`|Industry-standard observability (A2A already emits OTLP — source: [Apono](https://www.apono.io/blog/what-is-agent2agent-a2a-protocol-and-how-to-adopt-it/))|
|PII detection             |`presidio-analyzer` (Microsoft) or regex engine   |Pluggable PII detection for compliance interceptor                                                                                                         |
|Config management         |`pydantic` models + YAML                          |Type-safe configuration with validation                                                                                                                    |
|Testing                   |`pytest` + `pytest-asyncio`                       |Async test support for the sidecar                                                                                                                         |
|Event streaming           |Apache Kafka (KRaft mode)                         |Real-time event fan-out, backpressure, replay. KRaft eliminates ZooKeeper dependency. `confluent-kafka` Python client for producers/consumers               |
|Container                 |Docker (Alpine-based)                             |Minimal footprint for sidecar deployment                                                                                                                   |
|Orchestration:     LangChain/LangGraph

-----

## 7. Project Directory Structure

TBD by Claude Code

-----

## 8. Implementation Phases

### Phase 1: Core Sidecar (MVP)

**Goal:** Two LangGraph agents communicating via A2A through sidecars with basic governance, using the existing Recursant Agent Registry (../registry) as the control plane.

**Scope:**

- Sidecar with Flask server implementing A2A `tasks/send` and Agent Card serving
- A2A client for outbound requests
- Authentication interceptor (mTLS)
- Authorisation interceptor (simple allow/deny policies)
- Audit logging interceptor (local file + stdout)
- Existing Recursant Agent Registry used as the control plane — new `/v1/mesh/*` REST endpoints added for sidecar registration, heartbeat, deregistration, discovery, and policy distribution
- Basic `RecursantA2AClient` for LangGraph integration
- Docker Compose setup for local development (includes registry, DB, Redis alongside sidecars and agents)
- Unit and integration tests
- Agents run on Claude, Gemini, or GPT

### Phase 2: Compliance & Resilience

**Goal:** Production-grade compliance and fault tolerance.

**Scope:**

- Compliance interceptor (sovereignty rules, data classification) with compliance rules defined as code for now
- Circuit breaker and retry logic
- Failover routing
- SSE streaming support for long-running A2A tasks
- gRPC-based Control Plane config sync (upgrade from REST polling to push-based)
- OpenTelemetry tracing and metrics
- `RecursantA2ANode` for LangGraph graph integration

### Phase 2a: Build of visualisation tool for tracing the mesh

**Goal:** Build a visualiation tool to view and track mesh interactions in real-time

- Build a new mesh visualisaiton tool (inside the registry)
- The tool shows the real-time message exchanges betwee agents in a visualised graph of agents 
- Each node in the graph represents an agent (with the agent's name) 
- Connections between agents represents A2A message flows
- When an interaction happens, the connection is lit up (changes colour) for a five seconds (configurable
- There is a message log on the right hand side of the visualiser, which shows all the communications in text (interaction log, e.g. 'Agent A communicated with agent B' + timestamp)
- If an agent tries to communicate with another agent it is not allowed to talk to, it should be flagged with a differnet colour
- Agents that run on the same Langgraph instance should be grouped / clustered together visually and using the same node colour so it is clear that they run on the same instance / host
- Connections between nodes should only be drawn if there has ever been an interaction. If there has never been an interaction, the connection should not be drawn. Once the interaction happens, the connection should be drawn automatically
- If you hover or press an agent note, information should pop up with the agent's name, endpoint, capabiltiy, deployment platform (e.g. Langgraph), all sidecar information
- The tool should work both for normal laptops and iPads
- To support settings with hundreds of agents, it should be possible to zoom in and out to get an overview. You will need to add a zoom and panning facility (i.e. with press to drag and pan the canvas)
- The tool should therefore use vector graphics so zooming in and out and panning is possible
- When new agents /sidecars are added or removed, the tool should update automatically the canvas in real-time

### Phase 

### Phase 3: Production Hardening

**Goal:** Enterprise-ready deployment.

**Scope:**

- Certificate Authority and automatic mTLS certificate rotation
- NER-based PII detection (using Presidio or custom model)
- Hash-chained tamper-evident audit logs
- GDPR consent tracking

### Phase 4a: Kubernetes support

**Goal:** Make the mesh run on Kubernetes

**Scope:**

- Port mesh to Kubernetes
- Port registry to Kubernetes
- Make all tests, demos (origination) etc. run smoothly on Kubernetes


### Phase 4b: Kubernetes controls

**Goal:** Shift from Docker Compose to Kubernetes

**Scope:**

- Kubernetes sidecar injection (webhook-based, like Istio)
- Prometheus metrics endpoint
- Grafana monitoring
- Enable automatic fail-over if one registry is down (high availability)

### Phase 5: Observability Dashboard (Kiali for Agents)

**Goal:** Build a unified observability dashboard that combines service mesh visibility with AI-specific monitoring (guardrails, chain-of-thought, adversarial testing, cost tracking, tool/MCP governance).

**Sub-phases:**

#### O-1: Backend Foundation

- Deploy Kafka to Kind cluster (single-node KRaft mode — no ZooKeeper dependency)
- Add `confluent-kafka` Python dependency to sidecar and registry
- Refactor sidecar `AuditInterceptor` to produce to `mesh.audit` topic (retain `POST /v1/mesh/audit` as Kafka producer proxy fallback)
- Build Kafka consumer services: `pg_writer`, `ws_broadcaster`, `anomaly_detector`, `cost_aggregator`, `golden_signals`
- Create Kafka topics: `mesh.audit`, `mesh.guardrails`, `mesh.registrations`, `mesh.alerts`, `mesh.cost`
- Add `trace_service`, `alert_service`, `security_posture_service` to `app/services/`
- Create `mesh_anomalies` table and `is_false_positive` column on `guardrail_events`
- Add all `/v1/mesh/observability/*` API endpoints (traces, golden signals, cost, alerts, security posture, tool metrics, effectiveness matrix)
- Wire WebSocket broadcasts through `ws-broadcaster` consumer (remove inline `socketio.emit()` from REST endpoints)
- Integration tests for all new endpoints and Kafka consumer services

#### O-2: Enhanced Topology View

- Build `ObservabilityShell` container with tab navigation
- Implement hybrid canvas + SVG topology renderer
- Animated particle flows along edges (direction and volume)
- mTLS status indicators on edges
- Guardrail shield overlays on agent nodes
- Policy overlay toggle (sovereignty zones, blocked/allowed cross-zone)
- Golden signal health cards on hover/click
- Sovereignty zone clustering
- Click-through navigation to agent detail panels
- Performance testing at 200+ nodes

#### O-3: Trace View

- Waterfall/flame graph renderer for request traces
- Interceptor decision timeline rows (auth, compliance, data redaction, guardrail)
- Chain-of-thought audit inline display (expandable)
- Per-hop latency bars
- Navigation from topology edges, audit log task_ids, and direct URL

#### O-4: Guardrail Effectiveness Center

- Preserve existing guardrail dashboard as sub-view
- Effectiveness matrix heatmap (guardrails × attack categories)
- False positive marking and tracking
- Guardrail comparison view (side-by-side metrics)

#### O-5: Tool Observatory + Security Center + Cost Dashboard

- Tool usage topology (agents connected to tools, edge thickness = call volume)
- MCP server health indicators
- Per-tool metrics (call count, latency, error rate)
- Tool permission matrix view
- Real-time alert feed with severity badges and acknowledge/dismiss
- Adversarial test results summary
- Composite security posture score (0-100)
- Per-agent token consumption charts
- Cost breakdown by model/agent/zone/period
- Budget tracking with threshold alerts
- Projected monthly cost

#### O-6: Observability Shell + Demo Environment

- Wire all views into `ObservabilityShell` tabbed container
- Build `seed_observability_demo.py` script (agents, tools, guardrails, policies)
- Build `simulate_observability_demo.py` script (continuous traffic generation)
- End-to-end integration testing with demo environment
- Cross-browser and iPad testing

#### O-7: Stretch — Time Machine + Anomaly Detection + Performance

- Time-machine slider for historical topology replay
- Anomaly detection engine (traffic spikes, error bursts, cost anomalies)
- Canvas rendering optimizations for 500+ nodes
- Cost anomaly detection and projection algorithms

-----

## 9. Observability Demo Environment

### 9.1 Purpose

The observability demo extends the existing mortgage origination demo to exercise all six views of the observability dashboard. It adds agents across multiple sovereignty zones, MCP tools, diverse guardrail types, and scripted traffic patterns that generate interesting observability data (cross-zone blocks, guardrail triggers, tool failures, cost variations).

### 9.2 Agent Topology — 12 Agents across 3 Sovereignty Zones

**EU Zone (8 agents):**

| Agent | Risk Level | Data Classification | Connections |
|-------|-----------|---------------------|-------------|
| Customer Agent (existing) | medium | PII | Receives requests from Customer Support, Fraud Detection |
| Auth Agent (existing) | high | credentials | Authenticates all inbound requests |
| KYC Agent (existing) | high | PII | Called by Fraud Detection, Risk Assessment |
| Credit Check Agent (existing) | critical | financial | Called by Fraud Detection, Risk Assessment |
| Core Banking Agent (existing) | critical | financial | Central processing |
| Compliance Agent (existing) | high | regulatory | Monitors all EU agents |
| Fraud Detection Agent (new) | critical | financial | Fan-out to KYC, Credit, Customer; feeds Risk Assessment |
| Document Processing Agent (new) | medium | PII | Uses 3 MCP tools (search_documents, ocr_extract, summarize_text) |

**US Zone (1 agent):**

| Agent | Risk Level | Data Classification | Connections |
|-------|-----------|---------------------|-------------|
| Customer Support Agent (new) | low | PII | Cross-zone call to Customer Agent (EU) — sovereignty test point |

**APAC Zone (1 agent):**

| Agent | Risk Level | Data Classification | Connections |
|-------|-----------|---------------------|-------------|
| Data Pipeline Agent (new) | medium | PII | Attempts cross-zone call to Credit Check (EU) — blocked by sovereignty policy |

**Cross-zone (2 agents):**

| Agent | Risk Level | Data Classification | Connections |
|-------|-----------|---------------------|-------------|
| Risk Assessment Agent (new) | critical | financial | EU zone; hub consumer from Fraud, Credit, KYC |
| Monitoring Agent (new) | low | none | EU zone; read-only access to all agents |

### 9.3 MCP Tools — 6 Tools

| Tool | Assigned To | Backend | Purpose |
|------|------------|---------|---------|
| `search_documents` | Document Processing Agent | Mock HTTP endpoint | Search document corpus |
| `ocr_extract` | Document Processing Agent | Mock HTTP endpoint | Extract text from document images |
| `summarize_text` | Document Processing Agent | Mock HTTP endpoint | Summarize extracted text |
| `search_knowledge_base` | Customer Support Agent | Mock HTTP endpoint | Search support knowledge base |
| `check_fraud_signals` | Fraud Detection Agent | Mock HTTP endpoint | Query fraud signal database |
| `query_transaction_history` | Risk Assessment Agent | Mock HTTP endpoint | Query transaction records |

### 9.4 Guardrails — 10 Guardrails across 4 Mechanisms

| Guardrail | Mechanism | Assigned To | Purpose |
|-----------|-----------|------------|---------|
| PII Email Filter | regex | Customer Agent, Customer Support | Block email addresses in responses |
| PII SSN Filter | regex | KYC Agent, Credit Check | Block SSN patterns |
| SQL Injection Detector | regex | All agents | Block SQL injection attempts |
| Prompt Injection (Known) | vector_lookup | All agents | Match against known prompt injection library |
| Jailbreak Detector | vector_lookup | All agents | Match against known jailbreak patterns |
| Financial Advice Guard | llm_judge | Credit Check, Core Banking | Prevent unauthorized financial advice |
| PII Leak Detector | llm_judge | Customer Agent, Document Processing | Detect PII leaks in free-text responses |
| Toxicity Classifier | ml_classifier | Customer Support, Customer Agent | Block toxic/abusive content |
| Fraud Pattern Detector | ml_classifier | Fraud Detection | Detect known fraud communication patterns |
| Compliance Language Check | llm_judge | Compliance Agent | Ensure regulatory-compliant language |

### 9.5 Traffic Patterns

The `simulate_observability_demo.py` script generates continuous traffic with these proportions:

| Pattern | Proportion | Description |
|---------|-----------|-------------|
| Normal flow | 70% | Standard mortgage origination requests flowing through EU agents; tool calls succeeding; guardrails passing |
| Guardrail triggers | 15% | Requests containing PII, prompt injection attempts, or toxic content that trigger guardrails — generates data for effectiveness matrix |
| Policy violations | 10% | Cross-zone requests (US→EU, APAC→EU) that test sovereignty enforcement — some allowed (Customer Support→Customer), some blocked (Data Pipeline→Credit Check) |
| Cross-zone allowed | 5% | Successful cross-zone flows to show the policy overlay working correctly |

**Additional injected scenarios (periodic):**

- **Tool failures:** Intermittent 500s from `ocr_extract` mock (exercises tool error tracking)
- **Latency spikes:** Periodic slow responses from Credit Check (exercises golden signal alerting)
- **Cost variation:** Fraud Detection uses larger prompts (higher token count) — exercises cost anomaly detection
- **mTLS expiry:** One agent's cert expires during simulation (exercises security posture scoring)

### 9.6 Scripts

| Script | Purpose | Idempotent |
|--------|---------|-----------|
| `scripts/seed_observability_demo.py` | One-time setup: register 12 agents, 6 tools, tool assignments, 10 guardrails, sovereignty policies, egress rules, budget quotas | Yes |
| `scripts/simulate_observability_demo.py` | Continuous traffic: generates A2A messages, tool calls, and guardrail-triggering requests per the traffic pattern table above. Runs until stopped (Ctrl-C). Configurable rate via `--rps` flag (default: 2 requests/second) | N/A (stateless) |

Both scripts read connection details and credentials from `.env` / environment variables (per testing rules).

-----

## 10. Sections Reserved

(Sections 10 reserved for future use.)

-----

## 11. Glossary

|Term            |Definition                                                                                       |
|----------------|-------------------------------------------------------------------------------------------------|
|A2A             |Agent2Agent protocol — open standard for agent-to-agent communication (Google / Linux Foundation)|
|Agent Card      |JSON document describing an agent’s capabilities, endpoint, and auth requirements (A2A spec)     |
|Agentic Mesh    |Recursant’s term for the governed network of interconnected AI agents                            |
|Registry        |Recursant's existing agent registry capability, see folder "../"                                 |
|Control Plane   |Centralised management layer that configures sidecars (cf. Istiod in Istio)                      |
|Consumer group  |Kafka concept — a set of consumers that share a subscription to topics, each partition read by one consumer in the group. Enables parallel processing and independent scaling |
|Data Plane      |The set of sidecars that handle actual agent-to-agent traffic                                    |
|Interceptor     |A middleware component in the sidecar pipeline that inspects/modifies/blocks A2A messages        |
|Kafka           |Apache Kafka — distributed event streaming platform used as the observability event bus. Runs in KRaft mode (no ZooKeeper). Provides durable ordered event log with fan-out to multiple consumer groups |
|KRaft           |Kafka Raft — Kafka's built-in consensus protocol replacing ZooKeeper for metadata management. Simplifies deployment to a single process |
|MCP             |Model Context Protocol (Anthropic) — standard for agent-to-tool/data-source communication        |
|mTLS            |Mutual TLS — both client and server authenticate via certificates                                |
|OTLP            |OpenTelemetry Protocol — standard for emitting traces, metrics, and logs                         |
|Sidecar         |Lightweight proxy process deployed alongside each agent                                          |
|Sovereignty zone|Geographic/legal boundary within which data must remain (e.g., EU, APAC)                         |
|xDS             |Discovery Service protocol family (used by Envoy/Istio for config distribution)                  |

-----

## 12. Behavioral Changes & Audit Trail

### 12.1 Rolling Update Race Condition Fix

During rolling updates, a terminating pod's sidecar would deregister from the mesh, inadvertently deleting the replacement pod's registration (since both share the same agent name). Fix: sidecar deregistration is now `sidecar_url`-aware — a deregister call only removes the registration if the `sidecar_url` matches the calling sidecar. If a replacement pod has already re-registered with a new `sidecar_url`, the old pod's deregister is a no-op. Sidecars also auto re-register on heartbeat failure as a safety net.

### 12.2 NetworkPolicy Enforcement

A Kubernetes NetworkPolicy (`{release}-agent-ingress`) blocks direct agent-to-agent communication on application ports. All inter-agent traffic must flow through sidecar A2A/mTLS ports (default range 8443-8500). This prevents agents from bypassing the governance pipeline (authentication, authorization, compliance, audit).

- **Toggle:** `networkPolicy.enabled` in Helm values (default: `true`)
- **CNI requirement:** Requires a CNI that enforces NetworkPolicy (Calico, Cilium). Kind's default kindnet silently ignores policies — the `kind-up.sh` script installs Calico automatically.
- **Infrastructure exemption:** Pods without the `recursant.io/sidecar-inject` label (registry, test-agent, gateway, DB, Redis) have full access to agent pods on any port.
- **Localhost unaffected:** K8s NetworkPolicies never affect loopback, so agent-to-sidecar communication within a pod works regardless.

### 12.3 Sidecar-Enforced Communication Model

The intended communication path between agents:

```
Agent A → localhost → Sidecar A → mTLS A2A port → Sidecar B → localhost → Agent B
```

Direct pod-to-pod calls on application ports (e.g. agent-b curling agent-a:5010) are blocked by the NetworkPolicy. This ensures every inter-agent message passes through the interceptor pipeline (auth, compliance, audit, rate limiting, resilience).

### 12.4 Tool Governance — Registry-Controlled Tool Authorization and Egress Control

The sidecar now governs tool calls (MCP tools / HTTP backend APIs) and arbitrary egress HTTP requests, in addition to A2A agent-to-agent traffic. This closes the gap where tool calls bypassed the sidecar entirely.

**Architecture:**

```
Agent → Sidecar POST /tools/call → Sidecar validates (approved? assigned?) → HTTP to backend API → audit record
Agent → Sidecar POST /egress     → Sidecar checks URL allowlist → HTTP to external URL → audit record
```

**Registry models:**

- `MeshTool` — registered tool with name, endpoint_url, http_method, status (draft/approved/suspended)
- `MeshToolAssignment` — maps tool to agent (unique on tenant_id + tool_id + agent_name)
- `MeshEgressRule` — URL allowlist/denylist (glob patterns via fnmatch, priority-ordered, first match wins)

**Sidecar endpoints:**

- `POST /tools/call` — accepts `{tool_name, arguments}`, validates tool is approved+assigned, makes HTTP call, returns result. Blocked calls return 403.
- `POST /egress` — accepts `{method, url, headers, body}`, evaluates URL against egress rules, proxies if allowed. Default deny.

**Audit trail:**

All tool calls and egress requests create audit records in `MeshAuditLog` using the existing audit pipeline:

| Traffic type | a2a_method | dest_agent_name | details |
|---|---|---|---|
| A2A message | `message/send` | receiving agent | interceptor decisions |
| Tool call | `tools/call` | tool name | tool_name, endpoint_url, arguments_hash, response_status |
| Egress HTTP | `egress/http` | URL | method, url, response_status |

**Agent integration:**

Agents use `SidecarToolClient` (drop-in replacement for `MCPToolClient`) which POSTs to `{sidecar_url}/tools/call`. Controlled by `USE_SIDECAR_TOOLS` env var (default `0`; set to `1` to enable).

**Sync:**

The sidecar periodically fetches tool assignments and egress rules from the registry (configurable via `tool_sync_interval_seconds`, default 30s). Cached data is used if the registry is temporarily unreachable.

**Enforcement model:**

Application-level enforcement only (agents must use `SidecarToolClient`). Network-level egress enforcement (iptables/NetworkPolicy blocking direct outbound from agent containers) is future work.

**Risks:**

1. Agents can bypass the sidecar by calling APIs directly (network enforcement is future work)
2. Tool suspension takes up to 30s to propagate (cache staleness)
3. `USE_SIDECAR_TOOLS=0` disables governance for debugging but also disables enforcement

-----

## 13. References

1. **A2A Protocol Spec & GitHub** — https://github.com/a2aproject/A2A
1. **A2A v0.3 Announcement (Google Cloud, July 2025)** — https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade
1. **A2A Launch Blog (Google, April 2025)** — https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
1. **Linux Foundation A2A Project Launch (June 2025)** — https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project
1. **IBM A2A Explainer** — https://www.ibm.com/think/topics/agent2agent-protocol
1. **Istio Architecture Documentation** — https://istio.io/latest/docs/ops/deployment/architecture/
1. **Istio Sidecar vs Ambient Mode** — https://istio.io/latest/docs/overview/dataplane-modes/
1. **LangGraph 1.0 & LangChain 1.0 Release (Oct 2025)** — https://blog.langchain.com/langchain-langgraph-1dot0/
1. **LangGraph Platform GA (Oct 2025)** — https://blog.langchain.com/langgraph-platform-ga/
1. **A2A Adoption Analysis (fka.dev, Sept 2025)** — https://blog.fka.dev/blog/2025-09-11-what-happened-to-googles-a2a/
1. **A2A Protocol Overview (Apono)** — https://www.apono.io/blog/what-is-agent2agent-a2a-protocol-and-how-to-adopt-it/
1. **Recursant Investor Thesis (Jan 2026)** — Internal document

-----

*End of specification. Ready for Claude Code implementation starting with Phase 1.*
