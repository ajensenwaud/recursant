# Features

A catalog of what Recursant ships, grouped by capability. Implementation
references point to the file or directory where each feature lives, so you can
read the code without grep'ing the tree.

For a higher-level overview of how the pieces fit together, see
[`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Table of contents

1. [Agent governance lifecycle](#1-agent-governance-lifecycle)
2. [Security testing](#2-security-testing)
3. [Evaluation (LLM-as-a-judge)](#3-evaluation-llm-as-a-judge)
4. [Guardrails (runtime enforcement)](#4-guardrails-runtime-enforcement)
5. [Adversarial testing](#5-adversarial-testing)
6. [Mesh data plane (sidecar)](#6-mesh-data-plane-sidecar)
7. [Mesh control plane (registry)](#7-mesh-control-plane-registry)
8. [Tool governance and egress](#8-tool-governance-and-egress)
9. [Compliance and data governance](#9-compliance-and-data-governance)
10. [Observability](#10-observability)
11. [Discovery](#11-discovery)
12. [Resilience](#12-resilience)
13. [Identity and certificates](#13-identity-and-certificates)
14. [LLM provider integrations](#14-llm-provider-integrations)
15. [Web UI](#15-web-ui)
16. [Deployment](#16-deployment)
17. [Demo: mortgage origination](#17-demo-mortgage-origination)

---

## 1. Agent governance lifecycle

Every agent passes through a workflow before it can join the mesh. Each state is
gated; agents only become discoverable to other agents when `ACTIVE`.

```
DRAFT → SUBMITTED → TESTING → EVALUATING → PENDING_APPROVAL → APPROVED → ACTIVE
                          ↓             ↓
                  SECURITY_FAILED  EVALUATION_FAILED
                                                                     ↓
                                                            SUSPENDED → DECOMMISSIONED
```

- **State machine** with role-gated approvals (Team Lead, Security Reviewer, Governance Board, CISO) — `registry/app/services/agent_service.py`
- **Risk-tier driven approval rules** — low/medium agents auto-approve at team level; high/critical require multi-party approval — `registry/app/services/approval_service.py`
- **Soft-delete** via `deleted_at` timestamp; agent metadata is never purged — regulatory retention (7 years for security/eval/approval results)

## 2. Security testing

Automated security scans run when an agent is submitted. 11 LLM-driven attack
categories probe the agent and grade responses with regex-based evaluation.

- **Prompt injection resistance** — direct, indirect, jailbreak patterns; OWASP LLM Top 10 coverage
- **Data exfiltration** — verify the agent doesn't leak training data, system prompts, secrets
- **Tool abuse** — confirm tools can't be misused beyond declared permissions
- **Credential handling** — hardcoded-secret detection
- **Input validation** — malformed, oversized, malicious inputs
- **Egress validation** — agent only calls declared endpoints
- **Custom test cases** — admin-defined security tests via the web UI
- **Signed scan results** for audit (HMAC-SHA256)

Implementation: `registry/app/services/security_scan_service.py`, `registry/scripts/seed_security_tests.py`.

## 3. Evaluation (LLM-as-a-judge)

LLM-as-judge guardrails evaluation against test suites. Multiple LLM providers
supported as the judge.

- **Configurable test suites** with grading criteria, weights, passing thresholds
- **Two seed suites**: Baseline (all agents) and Extended (high/critical risk tier)
- **Pluggable judge providers** — Anthropic, OpenAI, Google, Moonshot, OpenRouter
- **Per-test-case scores and reasoning** with cryptographic signing for audit
- **Aggregation methods** — weighted average, strict (all must pass), threshold

Implementation: `registry/app/services/evaluation_service.py`, `registry/app/llm/`, `registry/scripts/seed_evaluation_suites.py`.

## 4. Guardrails (runtime enforcement)

Pre-processing and post-processing guardrails enforced at runtime by the
sidecar — distinct from the one-shot evaluation suites.

**Mechanisms** (configurable per guardrail):

- **Regex** — pattern matching (PII filters, SQL injection, prompt injection)
- **Vector lookup** — Weaviate similarity search against known-attack libraries
- **LLM-as-judge** — call out to a separate LLM to score the request/response
- **ML classifier** — toxicity, fraud-pattern, bias detection

**Lifecycle**:

- Draft mode (testable) → Active (enforced)
- Per-agent or fleet-wide assignment
- Real-time push to sidecars (default 30s sync interval)
- Effectiveness matrix dashboard (guardrails × attack categories, block rate, false-positive rate)

**Chain-of-thought auditing** (LlamaFirewall-style): post-processing
inspection of intermediate steps (tool calls, retrieval results, decisions)
for goal hijacking and hidden prompt injection. Reasoning-level findings
attached to the hash-chained audit log.

Implementation:
`mesh/runtime/sidecar/interceptors/pre_guardrail.py`,
`mesh/runtime/sidecar/interceptors/post_guardrail.py`,
`registry/app/services/guardrail_service.py`,
`registry/app/api/guardrails.py`.

## 5. Adversarial testing

Auto-generates adversarial inputs (jailbreaks, injection variants, encoding
tricks) and tests them against active guardrails, reporting evasion rates.

- **One-off or scheduled** runs; alerts when evasion rate exceeds a threshold
- **Custom attack library** — admin-managed via UI; bulk import/export
- **LLM-generated attack variants** — three strategies: mutation (rephrase
  existing attacks), category-targeted, creative (payload splitting,
  encoding chains)
- **Graceful degradation** — runs complete with static + custom inputs even
  if the attacker LLM fails

Implementation: `registry/app/services/adversarial_service.py`, `registry/app/api/adversarial.py`.

## 6. Mesh data plane (sidecar)

A Python sidecar process is injected next to each agent pod and mediates all
agent-to-agent traffic.

**Dual-listener architecture**:

- **HTTP proxy port** (e.g. 9901) — agent ↔ sidecar over localhost (plain HTTP)
- **mTLS A2A port** (e.g. 8443) — sidecar ↔ sidecar over mutual TLS, JSON-RPC 2.0

**Interceptor pipeline** (each can pass / modify / reject):

| Interceptor | Purpose |
|---|---|
| Authentication | mTLS cert CN, API key, JWT validation |
| Authorisation | Priority-ordered allow/deny with wildcard agent matching |
| Compliance | Sovereignty zones, data classification, GDPR consent |
| Pre-guardrail | Inbound request guardrails (regex/vector/LLM/ML) |
| Redaction | PII detection (regex or Microsoft Presidio), redact/block/warn |
| Post-guardrail | Response guardrails + chain-of-thought audit |
| Audit | Hash-chained tamper-evident records |
| Rate limiter | Token-bucket per source agent |
| Fault injection | Chaos testing: delay + abort with percentage triggers |

Implementation: `mesh/runtime/sidecar/`.

**A2A protocol support** (`a2a-sdk` 1.0.x):
`message/send`, `tasks/get`, `tasks/cancel`, `tasks/sendSubscribe` (SSE),
`tasks/pushNotification/set`, agent card serving at `/.well-known/agent.json`.

## 7. Mesh control plane (registry)

The registry is the single source of truth for agent metadata, policies, mesh
state, certificates, and audit.

- **Sidecar registration / heartbeat / deregistration** — `/v1/mesh/registrations`
- **Mesh policies** — priority-ordered allow/deny rules with wildcards
- **Tool registry** with approval workflow and per-agent assignment
- **Egress rules** — URL allowlist/denylist (glob, priority-ordered)
- **Configuration sync** — sidecars poll every 30s; gRPC push fallback also implemented
- **Multi-registry failover** — sidecars probe alternate URLs with background recovery
- **Multi-cluster active-active HA** — Postgres replication + Redis-backed event bridge

Implementation: `registry/app/api/mesh.py`, `registry/app/services/mesh_service.py`, `mesh/runtime/sidecar/registry_client.py`.

## 8. Tool governance and egress

Sidecar-mediated tool calls and arbitrary outbound HTTP — the only
governance-aware paths an agent has to the outside world.

- **`POST /tools/call`** — validates the tool is approved AND assigned to the
  caller, makes the HTTP call, writes an audit record
- **`POST /egress`** — evaluates URL against the egress rules (default deny);
  proxies if allowed
- **MCP tool registration** — admin defines a tool (name, endpoint, method,
  auth), approves it, assigns it to specific agents
- **Application-level enforcement** — agents must use `SidecarToolClient`;
  network-level egress lockdown is the next iteration

Implementation: `mesh/runtime/sidecar/tools.py`, `mesh/runtime/sidecar/app.py` (`/tools/call`, `/egress`).

## 9. Compliance and data governance

Recursant treats compliance as a first-class concern, not bolt-on instrumentation.

- **Sovereignty zones** — block/allow data flows between geographic regions (EU, US, APAC). Configurable per-agent zone.
- **Data classification** — `internal | confidential | restricted | public` × `none | pii | phi | financial | secret`. The mesh prevents high-classification data flowing to lower-clearance agents.
- **GDPR consent enforcement** — query consent before processing; block uncovered flows. Consent revocation propagates to the audit log.
- **PII redaction** — pluggable detector. Regex (default) or Microsoft Presidio (NER) for production-grade.
- **EU AI Act compliance module** — risk classification wizard, Annex IV
  documentation tracker, conformity assessment, gap reporting per agent

Implementation: `mesh/runtime/sidecar/interceptors/compliance.py`, `mesh/runtime/sidecar/interceptors/redaction.py`, `registry/app/api/compliance.py`.

## 10. Observability

Real-time, end-to-end visibility into mesh traffic, governance, cost, and
guardrail effectiveness — built on Apache Kafka.

**Pipeline**:

```
sidecars → mesh.audit (Kafka) → consumer groups → Postgres / WebSocket / alerts
```

Five Kafka topics (`mesh.audit`, `mesh.guardrails`, `mesh.registrations`,
`mesh.alerts`, `mesh.cost`) and five consumer services (`pg-writer`,
`ws-broadcaster`, `anomaly-detector`, `cost-aggregator`, `golden-signals`).

**Dashboards** (in the registry web UI):

- **Topology view** — animated mesh graph (canvas + SVG hybrid). Particle
  flows along edges show live traffic; mTLS status, guardrail shields,
  sovereignty zone clustering, golden-signal hover cards. Pan/zoom. Tools and
  MCP servers are first-class node types.
- **Trace view** — given a `task_id`, waterfall/flame graph of every hop
  across agents with per-hop latency and interceptor decisions.
- **Guardrail effectiveness centre** — heatmap of guardrails × attack
  categories, false-positive marking, side-by-side comparison.
- **Tool & MCP observatory** — per-tool metrics, permission matrix.
- **Security command centre** — live alert feed, adversarial test results,
  composite security posture score.
- **Cost dashboard** — per-agent token consumption, breakdown by
  model/agent/zone/period, budget tracking, projected monthly spend, anomaly
  detection (>2× rolling average).

**Anomaly detection**: traffic spikes (>3σ from 7-day baseline), error bursts
(>10% sustained 2+ min), policy violation surges, cost anomalies — produced
to `mesh.alerts` for real-time notification.

**Standards**: OpenTelemetry traces (OTLP), W3C Trace Context propagation,
Prometheus-compatible `/metrics` endpoint, structured JSON logs.

Implementation: `registry/app/consumers/`, `registry/app/api/observability.py`, `registry/app/services/golden_signals_service.py`, `mesh/runtime/sidecar/telemetry.py`.

## 11. Discovery

How an agent finds another agent without hardcoded endpoints.

- **Attribute search** — name, team, classification, risk tier, status, capability, endpoint type
- **Semantic capability search** — natural-language query → vector similarity (pgvector) over capability descriptions
- **Schema-based matching** — find agents whose input/output schemas are compatible (exact + structural)
- **Health filtering** — only `ACTIVE` agents are returned by default
- **Discovery audit log** — who searched for what, when

Implementation: `registry/app/api/discovery.py`, `registry/app/services/discovery_service.py`.

## 12. Resilience

Production-grade fault tolerance built into the sidecar.

- **Circuit breaker** — CLOSED / OPEN / HALF_OPEN per destination, configurable failure threshold + recovery timeout
- **Retry with exponential backoff** — configurable max attempts, base, jitter
- **Timeouts** — per-destination, distinct sync (30s) vs streaming (300s) defaults
- **Failover routing** — try each destination in order, fall back on failure
- **Connection pooling** — max connections, max pending requests
- **Load balancing** — 5 algorithms: round-robin, random, least-requests, consistent-hash, weighted

Implementation: `mesh/runtime/sidecar/resilience.py`, `mesh/runtime/sidecar/load_balancer.py`, `mesh/runtime/sidecar/client.py`.

## 13. Identity and certificates

Zero-trust identity for every sidecar.

- **Registry-issued mTLS certificates** for sidecar-to-sidecar identity
- **CSR-based renewal** with hot-swap SSL context — no agent restart on rotation
- **Certificate authority** internal to the registry (out of the box) — pluggable for production CAs

Implementation: `mesh/runtime/sidecar/cert_rotation.py`, `registry/app/api/certificates.py`.

## 14. LLM provider integrations

Pluggable LLM provider abstraction used by the test agent, the eval judge,
and the runtime guardrail LLM-judge mechanism.

| Provider | Model namespace |
|---|---|
| Anthropic | `claude-*` |
| OpenAI | `gpt-*` |
| Google | `gemini-*` |
| Moonshot | `kimi-*` (Kimi K2.5, OpenAI-compatible) |
| OpenRouter | `openrouter/auto` or any `<provider>/<model>` (one key, many models) |

Implementation: `registry/app/llm/`, `mesh/runtime/sidecar/llm_client.py`.

## 15. Web UI

React + Vite + Tailwind, served by nginx.

- Agent submissions, security scans, evaluations, approvals, active agents
- Mesh sidecars, mesh visualiser, mesh audit explorer
- Tools (submitted, approved), tool detail, metric store
- Guardrails (CRUD, configurations, observability, insights)
- Adversarial testing, custom attack library
- Network discovery, EU AI Act compliance, audit log
- User management, group management, webhooks

Auth: JWT (login flow); admin user seeded from `.env` on first startup.

Implementation: `registry/frontend/`.

## 16. Deployment

- **Helm chart** — `k8s/charts/recursant/` with `values.yaml`, mortgage demo overlay (`values-mortgage.yaml`), and multi-cluster overlays
- **Mutating admission webhook** — auto-injects sidecars based on annotations
  (`recursant.io/inject-sidecar: "true"`, `recursant.io/inject-sidecars: '<JSON>'` for multi-agent pods)
- **NetworkPolicy** — blocks direct agent-to-agent traffic on application ports; all inter-agent communication must traverse the sidecar mTLS layer (Calico CNI required for enforcement)
- **Multi-registry failover** — sidecars accept multiple registry URLs; health-based promotion with background recovery
- **Multi-cluster active-active HA** — PostgreSQL streaming replication, Redis Sentinel, Kafka cross-cluster mirroring
- **Kind cluster scripts** for local development; Helm charts production-ready

Implementation: `k8s/`, `Makefile`.

## 17. Demo: mortgage origination

A full multi-agent demo showcasing hub-and-spoke topology with realistic
governance constraints.

- **Customer agent** (hub) orchestrates the mortgage application end-to-end
- **Spokes**: Authentication, KYC (n8n workflow), Credit, Core Banking, Compliance (CrewAI)
- **MCP tools** governed via the registry: `verify_customer`, `verify_identity`,
  `assess_credit_capacity`, `make_credit_decision`, `disburse_loan`,
  `check_lending_regulations`, `verify_document_completeness`,
  `calculate_compliance_score`
- **NetworkPolicy** enforces hub-and-spoke (spokes can't talk to each other)
- **Multi-modal**: passport image OCR, payslip parsing
- **End-to-end e2e test** — `demo/mortgage/scripts/test_e2e.py`
- **Continuous traffic generator** for screen-recording demos —
  `demo/mortgage/scripts/generate_demo_traffic.py`

Implementation: `demo/mortgage/`.

---

## What's intentionally NOT in scope

- A general-purpose agent runtime — Recursant governs *other people's* agents (LangChain, LangGraph, CrewAI, AgentForce, custom HTTP). Bring your own.
- A vector database for RAG — agents handle their own knowledge. Recursant uses pgvector and Weaviate for capability discovery and guardrail vector lookup respectively.
- An LLM. The platform is provider-agnostic.
