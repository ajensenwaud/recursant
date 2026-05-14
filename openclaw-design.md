# OpenClaw integration — design

Status: draft, v0 in progress
Branch: `feature/openclaw-design`

## Goal

Let a user spin up an OpenClaw instance, install a Recursant plugin into it,
register the instance with the Recursant registry, and have the registry
govern the instance's tool calls and LLM calls. OpenClaw is local-first
(Mac/Windows/Linux desktop), so there is **no Kubernetes data plane** for
this case. Recursant must govern OpenClaw cooperatively.

## What OpenClaw gives us (verified against their code)

OpenClaw is a TypeScript/Node monorepo (`github.com/openclaw/openclaw`).
Relevant seams found in `docs/plugins/` and `extensions/`:

- **Plugin entry**: `definePluginEntry({ id, register(api) { ... } })` from
  `openclaw/plugin-sdk/plugin-entry`. Manifest in `openclaw.plugin.json`,
  runtime entry in `dist/index.js`.
- **Hook bus, in-process, decision-capable**:
  - `before_tool_call` — rewrite params, `block`, or `requireApproval`
  - `before_agent_run` / `before_agent_reply` / `before_agent_finalize`
  - `llm_input` / `llm_output` / `model_call_started` / `model_call_ended`
  - `message_received` / `message_sending` / `before_dispatch`
  - `gateway_start` / `gateway_stop` — plugin-owned background services
  - `before_install` — block other plugin installs
- **Trusted tool policies**: `api.registerTrustedToolPolicy(...)` runs before
  ordinary hooks; host-level gate.
- **Provider plugins** (see `extensions/anthropic/`) own the HTTP path to
  the upstream LLM and declare `providerEndpoints.hosts`.

## Decisions for v0

1. **TS-native, in-process**. No spawned Python sidecar. The plugin embeds
   the interceptor logic directly in TypeScript and talks to the registry
   over HTTP. This avoids a Python runtime dependency on the user's machine
   and keeps the install footprint to a single npm package.
2. **Hook-only interception**. We do not replace OpenClaw's provider
   plugins in v0. Governance is cooperative: when the plugin is enabled,
   tool calls, LLM calls, and messages flow through Recursant interceptors;
   when it is disabled, OpenClaw runs unmodified. Enforcement (provider
   override, trusted tool policies, tamper detection) is v1.
3. **Token-in-config-file enrollment**. Admin issues an enrollment token in
   the registry UI, user pastes it into the plugin config. Plugin exchanges
   it for a longer-lived JWT bound to a stable machine fingerprint. OAuth
   device flow is a later improvement.

## Architecture (v0)

```
┌──────────────────────────────────────────────────────────────────┐
│  User laptop                                                      │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  OpenClaw process                                           │ │
│  │                                                             │ │
│  │  ┌────────────┐    api.on(before_tool_call, ...)           │ │
│  │  │ user input │──▶ api.on(llm_input, ...)                  │ │
│  │  └────────────┘    api.on(message_sending, ...)            │ │
│  │                                  │                          │ │
│  │                                  ▼                          │ │
│  │                      ┌───────────────────────┐              │ │
│  │                      │  Recursant plugin     │              │ │
│  │                      │  (TS, in-process)     │              │ │
│  │                      │                       │              │ │
│  │                      │  - Interceptor chain  │              │ │
│  │                      │  - Policy cache       │              │ │
│  │                      │  - Audit queue        │              │ │
│  │                      │  - Registry client    │              │ │
│  │                      └─────────┬─────────────┘              │ │
│  └────────────────────────────────┼──────────────────────────────│
└────────────────────────────────────┼──────────────────────────────┘
                                     │ HTTPS (JWT)
                                     ▼
                         ┌──────────────────────┐
                         │   Recursant registry  │
                         │   /v1/openclaw/*      │
                         │   /v1/agents          │
                         │   /v1/guardrails      │
                         │   /v1/audit           │
                         └──────────────────────┘
```

Interceptors are ports of the existing `mesh/runtime/sidecar/interceptors/`
chain to TypeScript:

```
Request → Authentication → Authorisation → Compliance → PII Redaction
       → Audit → Rate Limiting → Decision
```

For v0 only Authorisation, PII, Audit, and Rate Limiting are wired. The
others stub to allow.

## Plugin package layout

Lives in this repo at `integrations/openclaw/` during development; publishes
to npm as `openclaw-recursant` once stable.

```
integrations/openclaw/
├── openclaw.plugin.json       # id: "recursant", activation.onStartup: true
├── package.json               # openclaw: { extensions, runtimeExtensions }
├── tsconfig.json
├── README.md
├── src/
│   ├── index.ts               # definePluginEntry + hook wiring
│   ├── config.ts              # config schema + file loader
│   ├── registry-client.ts     # enroll, heartbeat, policy poll, audit push
│   ├── machine-id.ts          # stable per-machine fingerprint
│   ├── interceptors/
│   │   ├── chain.ts           # runs the chain
│   │   ├── authorisation.ts
│   │   ├── pii.ts
│   │   ├── audit.ts
│   │   └── rate-limit.ts
│   └── types.ts
└── test/
    └── interceptors.test.ts   # offline unit tests
```

## Registry-side changes

Small, additive:

- New table `openclaw_instances`: `id`, `agent_id` (FK), `machine_id`,
  `instance_fingerprint`, `os`, `openclaw_version`, `plugin_version`,
  `enrolled_at`, `last_heartbeat_at`, `status`.
- New table `openclaw_enrollment_tokens`: `id`, `token_hash`, `created_by`,
  `expires_at`, `consumed_at`, `consumed_by_instance_id`.
- New blueprint `registry/app/api/openclaw.py` mounted at `/v1/openclaw`:
  - `POST /v1/openclaw/enrollment-tokens` (admin) — issue token
  - `POST /v1/openclaw/instances/enroll` — instance exchanges token for JWT
  - `POST /v1/openclaw/instances/heartbeat` (instance JWT) — report status
  - `GET  /v1/openclaw/instances` (admin) — list
  - `GET  /v1/openclaw/instances/<id>` (admin)
- Service: `registry/app/services/openclaw_service.py`.
- Alembic migration for the two new tables.

The instance is represented as a regular `Agent` row with
`endpoint.type = "openclaw"` and `endpoint.url = "local://<machine-id>"`
so it can use the existing governance pipeline (DRAFT → ... → ACTIVE),
guardrails, audit, and observability without inventing a parallel one.

## Lifecycle

1. **Enrollment**: admin clicks "New OpenClaw instance" in the registry UI,
   gets a one-time token. User pastes the token (plus registry URL) into
   the plugin's config file (default `~/.recursant/openclaw.json` or via
   OpenClaw's plugin config surface).
2. **`gateway_start`**: plugin loads config, computes `machine_id`, POSTs
   `/v1/openclaw/instances/enroll` with the token, gets back JWT + agent_id.
   Pulls initial policy + guardrails. Starts the heartbeat timer (30s).
3. **Hook traffic**: every intercepted call runs the local interceptor
   chain. Allowed calls return; blocks return the OpenClaw block result.
   Audit events are queued and flushed to `/v1/audit` (or the mesh audit
   endpoint) in batches.
4. **Heartbeat**: every 30s the plugin posts version, hooks installed,
   policy version it's running on. Registry flags drift / silence.
5. **`gateway_stop`**: flush audit queue, deregister.

## Out of scope for v0 (explicit)

- Provider plugin replacement / forced LLM routing
- Trusted tool policy host-level enforcement
- OS-level enforcement (iptables / pf)
- mTLS to the registry (we use JWT only)
- OAuth device flow
- Multi-tenant per-user isolation inside one OpenClaw instance
- ClawHub publication

These are tracked for v1 once the v0 cooperative path is real.

## Testing

Per project rules: no mocks for integration tests. v0 plan:

- Plugin unit tests for the interceptor chain (offline, no LLM).
- Registry integration tests for the new endpoints run inside the registry
  pod via `kubectl exec` against `registry_test` DB.
- End-to-end test: a tiny TypeScript test harness that loads the plugin
  outside OpenClaw and calls the `register(api)` callback with a stub
  `api` object, then drives a fake `before_tool_call` event through the
  chain to a live registry. Lives at `integrations/openclaw/test/`.

A real OpenClaw smoke test (launch OpenClaw, install plugin, send a chat
message) is manual for v0 until we have a CI runner with OpenClaw built.

## Open questions for v1

- How do we ship the npm package alongside Recursant releases? Separate
  semver?
- Do we want a `recursant openclaw enroll` CLI on top of the SDK for the
  user-side flow?
- Provider-override v1: which providers do we ship (anthropic, openai,
  google) and how do we handle OpenClaw's existing auth credentials?
