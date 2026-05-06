# Recursant vs Istio: Feature Gap Analysis

Features Recursant is missing compared to Istio service mesh.
Mark features you want implemented with `[x]`.

---

## Traffic Management

### [x] 1. Rate Limiting

Config already exists in Recursant but the interceptor is not wired into the pipeline.
Limits the number of requests a service can receive per time window (e.g., 100 req/s).
Prevents any single caller from overwhelming a destination. Can be applied per-client,
per-route, or globally. Istio supports both local (per-proxy) and global (Redis-backed
shared counter) rate limiting.

### [x] 2. Load Balancing Algorithms

Recursant currently uses sequential failover only (try destination 1, if it fails try 2, etc.).
Istio supports multiple strategies:
- **Round Robin** — cycles through endpoints sequentially (fair distribution)
- **Least Requests** — routes to the endpoint with fewest in-flight requests (best for uneven workloads)
- **Consistent Hash** — routes based on a hash of headers/cookies/IP so the same client always hits the same backend (useful for caching, session affinity)
- **Random** — picks a random healthy endpoint

### [ ] 3. Outlier Detection (Auto-Eject Unhealthy Hosts)

Passively monitors error rates per endpoint. If an endpoint returns too many consecutive
errors (e.g., 5 in a row), it is temporarily ejected from the load balancing pool. After a
cooldown period it is re-added. Prevents routing traffic to a known-bad instance. Different
from circuit breakers — outlier detection works across a pool of instances, circuit breakers
gate a single destination.

Key parameters: consecutive errors before ejection, ejection duration, max % of pool that
can be ejected (so you never eject all instances), analysis sweep interval.

### [ ] 4. Connection Pooling

Controls how many simultaneous connections and pending requests are allowed to each
upstream destination. Limits include:
- `maxConnections` — cap on TCP connections to a host
- `maxPendingRequests` — cap on queued requests waiting for a connection
- `maxRequestsPerConnection` — recycle connections after N requests
- `maxConcurrentStreams` — cap on HTTP/2 streams per connection

When limits are hit, new requests get immediate failure (503) rather than queuing
indefinitely. Provides backpressure and prevents resource exhaustion.

### [x] 5. Traffic Splitting (Weighted Routing)

Distribute traffic by percentage across multiple service versions. Example: send 90% of
requests to v1 and 10% to v2 during a canary rollout. The weights are configurable and
can be adjusted gradually (e.g., 95/5 -> 90/10 -> 50/50 -> 0/100). Foundation for
progressive delivery, A/B testing, and blue-green deployments.

### [ ] 6. Request Routing (Header/Path-Based)

Route requests to different destinations based on match conditions: HTTP headers, URI
paths, query parameters, source labels. Example: requests with header `x-env: staging`
go to the staging backend; requests to `/api/v2/*` go to the v2 service. Enables
sophisticated routing without application code changes. Recursant currently routes
by skill name only.

### [x] 7. Fault Injection

Introduces controlled failures for chaos/resilience testing:
- **Delay injection** — adds artificial latency (e.g., 5s delay on 30% of requests) to
  simulate slow networks or overloaded upstreams
- **Abort injection** — returns specific HTTP error codes (e.g., 503 on 10% of requests)
  to simulate upstream failures

Operates at the application layer so it works regardless of transport. Lets you verify
that retry logic, timeouts, and circuit breakers behave correctly under failure.

### [ ] 8. Traffic Mirroring (Shadow Traffic)

Sends a copy of live traffic to a mirrored service in fire-and-forget mode — responses
from the mirror are discarded. The mirrored service sees real production traffic patterns
but cannot affect actual users. Supports fractional mirroring (e.g., mirror 5% of traffic).
Useful for testing new versions, load testing, or validating ML model replacements against
real data with zero user impact.

### [ ] 9. Header Manipulation

Add, set, or remove HTTP request/response headers as traffic passes through the proxy.
Examples: inject tracing headers, add auth tokens for upstream services, strip internal
headers before responses reach external clients. Configured per-route.

---

## Security

### [x] 10. JWT / Request Authentication

Validate end-user identity by verifying JSON Web Tokens attached to requests. Configurable
with OIDC/JWT issuers and JWKS endpoints. Supports multiple token providers simultaneously
(Auth0, Keycloak, Firebase, etc.). Token claims can be extracted and used in authorization
policies (e.g., "only users with role=admin can access /admin/*"). Recursant currently
only supports API key authentication.

### [ ] 11. Permissive mTLS Mode

Accept both mTLS and plaintext connections on the same port. Essential for gradual migration:
when rolling out mTLS across a mesh, some callers may not have certificates yet. Permissive
mode lets them still connect while upgraded callers use mTLS. Istio supports three modes:
STRICT (mTLS only), PERMISSIVE (both), DISABLE. Recursant currently has no mixed mode —
it's either mTLS or plaintext.

### [ ] 12. External Authorization (OPA Integration)

Delegate authorization decisions to an external service (e.g., Open Policy Agent) via gRPC
or HTTP. Allows complex policy-as-code logic that goes beyond pattern matching — temporal
rules, cross-resource checks, attribute-based access control. The sidecar calls out to the
external authorizer and blocks/allows based on its response.

### [ ] 13. SPIFFE Identity

Replace CN-based certificate identity with SPIFFE URIs in the format
`spiffe://trust-domain/ns/namespace/sa/service-account`. SPIFFE is a standard for
workload identity across heterogeneous environments (Kubernetes, VMs, multi-cloud).
Enables interoperability with other SPIFFE-aware systems and provides a more structured
identity model than flat CN strings.

---

## Observability

### [x] 14. Prometheus /metrics Endpoint

Expose the existing OpenTelemetry metrics (request count, duration histograms, interceptor
decisions, cache hit/miss rates) via an HTTP `/metrics` endpoint in Prometheus exposition
format. Enables scraping by Prometheus, Datadog Agent, Grafana Agent, or any compatible
monitoring system. Recursant currently collects metrics internally via OTel but doesn't
expose them for external scraping.

### [ ] 15. Service Graph Visualization

Real-time topology visualization showing agent-to-agent communication graphs, traffic flow
rates, response codes, and health status. Istio integrates with Kiali for this. In
Recursant's context, this would be a frontend dashboard showing which agents talk to which,
message volumes, error rates, and sovereignty zone boundaries.

### [ ] 16. Active Health Checking (Upstream Probing)

Periodically probe upstream agent endpoints to detect failures before routing traffic to
them. Currently Recursant only discovers agents via registry and has `/healthz` for its own
health, but doesn't actively check if destination agents are healthy. Active probes would
remove dead agents from the routing pool before any user request fails.

---

## Ingress / Egress

### [x] 17. Ingress Gateway

A dedicated edge proxy that manages all traffic entering the mesh from external sources.
Provides TLS termination, authentication, rate limiting, and routing at the mesh boundary.
Currently external callers must know individual sidecar addresses. An ingress gateway gives
a single entry point with centralized security and observability.

### [ ] 18. Egress Gateway

A centralized exit point for all traffic leaving the mesh (calls to external APIs, databases,
third-party services). Provides auditing of outbound traffic, TLS origination (encrypt
connections to external services), access control (which agents can reach which external
endpoints), and dedicated egress IPs for firewall allowlisting.

---

## High Availability / Multi-Cluster

### [x] 19. Registry High Availability

NB - should be active/active with replication to another Kubernetes cluster

The registry is currently a single instance — if it goes down, no new registrations,
discoveries, or policy updates can occur (existing sidecars degrade gracefully with cached
data). HA options:
- **Multi-primary** — multiple registry instances each handling requests, with shared or
  replicated state (PostgreSQL replication, Redis cluster)
- **Primary-standby** — one active registry with a hot standby that takes over on failure
- **Leader election** — multiple instances coordinate via consensus (etcd/Raft)

### [ ] 20. Multi-Cluster Discovery

Merge service endpoints across multiple Kubernetes clusters or deployment environments.
Agents in cluster A can discover and route to agents in cluster B transparently. Requires
cross-cluster registry synchronization and network connectivity (via east-west gateways
or flat networking).

---

## Extensibility

### [x ] 21. Audit Log Explorer (Real-Time Interaction Viewer)

A comprehensive audit log system in the registry with a frontend UI for browsing,
searching, and inspecting all agent-to-agent interactions in real time. The current
audit log is too simple — records are shipped from sidecars and stored, but there is
no way to explore them.

**Real-time feed:** A live-updating view of all mesh interactions as they happen,
with WebSocket push so new entries appear immediately without polling. Each entry
shows source agent, destination agent, method, timestamp, outcome (success/blocked/
error), and which interceptors fired.

**Search and filtering:** Full-text search across audit records. Filter by source
agent, destination agent, time range, outcome (success/blocked/error), interceptor
decisions (e.g., "show me all compliance blocks"), data classification level,
sovereignty zone, and trace ID.

**Detail inspection:** Click any audit entry to expand a detailed view showing: the
full interceptor pipeline decisions (which interceptors passed/blocked/modified and
why), request/response metadata, trace context for distributed tracing correlation,
compliance decisions with rule references, any PII detections and redactions applied,
circuit breaker state at time of request, and the hash-chain integrity fields.

**Trace reconstruction:** Given a task ID or trace ID, reconstruct the full end-to-end
chain of agent interactions across the mesh — showing the complete flow from the
initiating request through all downstream agent calls, with timing and outcomes at
each hop.

**Aggregated views:** Summary dashboards showing interaction volumes over time,
top agent pairs by traffic, error rate trends, most common compliance violations,
and blocked interaction patterns.

### [ ] 22. Custom Interceptor Plugin System

Allow loading custom interceptors at runtime without modifying sidecar code. Istio uses
WebAssembly for this. In Recursant's Python context, this could be a plugin mechanism
where users drop in Python modules that implement the interceptor interface, and the
sidecar loads them from a configured directory. Enables custom policy logic, telemetry
collection, or payload transformation without forking the sidecar.
