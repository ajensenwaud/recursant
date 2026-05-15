# openclaw-recursant

Recursant governance plugin for [OpenClaw](https://www.openclaw.ai).

Registers the OpenClaw instance with a Recursant registry, then governs the
instance's tool calls, LLM calls, and chat messages via in-process
interceptors: authorisation, PII redaction, rate limiting, and audit.

This is v0 — cooperative governance only. Provider replacement and
host-level enforcement are not yet implemented.

## Install

```bash
# Once published:
npm install -g openclaw-recursant
# OpenClaw will pick it up via plugin discovery.
```

## Configure

Plugin config (via OpenClaw plugin config, env, or
`~/.recursant/openclaw.json`):

```json
{
  "registryUrl": "https://recursant.example.com",
  "enrollmentToken": "<one-time token from registry UI>",
  "tenantId": "default"
}
```

Override the config-file path with `RECURSANT_OPENCLAW_CONFIG=/path/to.json`.

## Build / test

```bash
pnpm install
pnpm build
pnpm test
```

## What it intercepts

| OpenClaw hook    | Behaviour                                                 |
|------------------|-----------------------------------------------------------|
| `before_tool_call` | Authz + PII + rate-limit; block / rewrite params         |
| `llm_input`      | PII + rate-limit on prompts; audit                        |
| `message_received` | Audit inbound chat                                       |
| `message_sending`  | PII redaction on outbound chat                           |
| `gateway_start`/`gateway_stop` | Enrol, heartbeat, deregister              |

## How it talks to Recursant

| Path                                       | Purpose                            |
|--------------------------------------------|------------------------------------|
| `POST /v1/openclaw/instances/enroll`       | Exchange enrolment token for JWT   |
| `POST /v1/openclaw/instances/heartbeat`    | Liveness + plugin version          |
| `GET  /v1/openclaw/instances/policy`       | Fetch current policy               |
| `POST /v1/openclaw/instances/audit`        | Push audit batches                 |
| `POST /v1/openclaw/instances/deregister`   | Graceful shutdown                  |

See `openclaw-design.md` at the repo root for the full design and the v1
roadmap.
