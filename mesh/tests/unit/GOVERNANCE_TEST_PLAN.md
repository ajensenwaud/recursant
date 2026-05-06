# Governance Enforcement Test Plan

Tests to validate that only ACTIVE agents can participate in the mesh.

## A. Authorisation Interceptor — Governance Status (`test_interceptors.py`)

### A1. All non-ACTIVE statuses are blocked
Test each governance status individually to confirm they're all rejected:
- `draft`
- `submitted`
- `testing`
- `evaluating`
- `pending_approval`
- `suspended`
- `decommissioned`
- `rejected`
- `security_failed`
- `evaluation_failed`

### A2. Both agents non-ACTIVE — source checked first
When both source and destination are non-ACTIVE, the error message should
reference the source agent (fail fast, don't leak info about destination).

### A3. Governance enforced on inbound direction
Current tests use outbound context. Verify governance blocks inbound
requests too (e.g. a DRAFT agent receiving a message from another sidecar).

### A4. Registry client exception handling
If `fetch_agent_status()` raises an unexpected exception (not just returns
None), the interceptor should fail closed (block), not crash or pass.

### A5. Full pipeline integration — blocked agent produces no audit
Wire up the full interceptor pipeline (auth -> authz -> compliance ->
redaction -> audit) with a DRAFT destination agent. Verify:
- Pipeline result is BLOCKED
- Blocking interceptor is "authorisation"
- Reason mentions governance/status
- No audit record created (audit interceptor never runs)

### A6. Governance check skipped when authorisation disabled
If `config.enabled = False`, governance check should also be skipped
(no registry call made).


## B. Registry Client — `fetch_agent_status()` (`test_registry_client.py`)

### B1. Returns status on successful lookup
Mock GET /v1/mesh/agents/lookup returning `{"status": "active"}`.
Verify returns `"active"`.

### B2. Returns None when agent not found (404)
Mock returning 404. Verify returns None.

### B3. Cache hit — no HTTP call on second request
Call twice within TTL. Verify httpx.get called only once.

### B4. Cache expiry — fresh fetch after TTL
Call once, sleep past TTL, call again. Verify httpx.get called twice.

### B5. Registry down with stale cache — returns stale value
First call succeeds (caches "active"), expire cache, second call gets
ConnectError. Verify returns stale "active" (fail-open for resilience).

### B6. Registry down with no cache — returns None
First call gets ConnectError, no prior cache. Verify returns None
(fail-closed when no data available).

### B7. Non-200 response with stale cache — returns stale value
First call succeeds, expire cache, second call returns 500. Verify
returns stale cached value.

### B8. Non-200 response with no cache — returns None
First call returns 500, no prior cache. Verify returns None.


## C. Integration — Lifecycle Wiring

### C1. Registry client wired into authz on startup
After `LifecycleManager.startup()`, verify that the authz interceptor's
`_registry_client` is set (not None).

### C2. Governance check active after registration
After startup, verify that calling authz.process() with a non-ACTIVE
agent triggers the registry client lookup (mock it to return "draft",
confirm block).
