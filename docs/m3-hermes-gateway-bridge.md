# Optional Hermes → gateway context bridge

`deploy/hermes/context_adapter/gateway.py` is a companion subclass of the existing
AF_UNIX adapter. The original `install()` and adapter are unchanged. This uses
supported `llm_request`, `post_api_request`, `post_tool_call`, and
`api_request_error` registration, not patched Hermes source.

## Explicit startup, default off

```python
from deploy.hermes.context_adapter.gateway import install_gateway

# Application startup, with actual lifecycle IDs already assigned; BEFORE agent dispatch.
bridge = install_gateway(
    plugin_context,
    enabled=True,                 # omitted/False registers nothing and opens nothing
    endpoint="http://127.0.0.1:8080/v1",
    task_id=actual_task_id,
    session_id=actual_session_id,
    branch="main",
    source_key_env="RECURSANT_CONTEXT_SOURCE_KEY",
    content_enabled=False,        # separate explicit consent for exposed text
    queue_capacity=32,
    timeout=1.0,
)
# Do not catch startup failure and then dispatch an associated agent unscoped.
# On application shutdown (not per request):
bridge.close(timeout=0.2)
```

The caller supplies a supported plugin context and actual IDs; this is not an
automatic discovery of a running Hermes task. One bridge owns exactly one
registered task/session/branch. Do not install multiple overlapping bridge
middlewares. Do not run the legacy AF_UNIX installer alongside this bridge for
one request. Unknown task/session callbacks do not get guessed into this scope.

`/v1/context/open` is authenticated synchronously **at startup**, and its echoed
scope and server-returned 32-hex generation are validated before hooks are
registered. A failed open is fatal to installation. There is no lazy open in
middleware, automatic re-registration, timestamp join, or reassignment of old
events after a gateway restart. The gateway enforces that its source credential
is separate from the inference credential. The bridge only reads the explicitly
named source environment variable; it never copies inference Authorization into
the exporter, source Authorization into a model request, or keys into bodies.

URLs must have a numeric IP host, exact `/v1` path, and no credentials, query,
fragment, whitespace or controls. HTTP is loopback-only. HTTPS uses normal
stdlib certificate verification; hostnames are deliberately unsupported to avoid
unbounded libc DNS in startup. `http.client` uses no proxy environment or
redirect handling. Errors do not log raw bodies, exposed text, or credentials.

## Mandatory scope is independent of optional telemetry

Valid requests keep the existing four logical IDs and per-middleware invocation
UUID, adding `X-Recursant-generation` and `X-Recursant-branch`. Model, messages,
tools, budgets, and original headers are not rewritten.

Known matching task/session requests **retain generation, branch, task and
session headers even when API count/turn/API metadata is invalid, the exporter
queue is full, the exporter failed, or `close()` has stopped it**. Incomplete
correlation does not invent a turn, API ID, or invocation UUID. Conflicting or
duplicate supplied headers are preserved for gateway rejection, not silently
repaired. Malformed non-convertible `extra_headers` is an explicit error; this
companion is not a security boundary for Hermes swallowing plugin exceptions.
The gateway must independently enforce association and pin authority, including
missing or malformed headers (see parent finding M3-GATEWAY-003).

Callbacks only update bounded local state and enqueue with `put_nowait`. The
owned daemon worker never holds the callback state lock over network IO. It does
not wait for semantic interpretation or snapshot readiness. A temporary daemon
watchdog bounds the HTTP transaction even under slow header/body drips; TCP/TLS
connection establishment separately uses the configured socket timeout. Replies
are limited to 4096 bytes. The queue bound is 1–256; original invocation tracking
remains bounded to 256. The one coalesced loss-marker slot contains metadata only.

`close()` stops future export, discards queued text while recording drops, wakes
the worker, and joins for a bounded timeout. An already in-flight transaction can
finish afterwards; inspect `bridge.worker.is_alive()` if the caller needs to know
whether it exited. Shutdown is not a flush/acceptance guarantee. Scope headers
remain intact; close does not reset continuity. Applications should stop agent
dispatch before shutdown, rather than treating a closed exporter as a new scope.

## Evidence, privacy, and failure semantics

- Default metadata mode exports no text. With `content_enabled=True`, only the
  adapter's exposed `content`/`reasoning_content` are considered. Hidden/encrypted
  reasoning, arbitrary callback fields, request bodies and tool arguments are
  never substituted.
- The wrapper preserves raw `assistant_plan`/`reasoning` text and explicit
  truncation flags. Nonempty segments must fit **1024 UTF-8 bytes** each. Oversize,
  truncated, invalid Unicode, NUL-containing or empty fields are rejected as
  losses; no trimming, splitting, sanitizing or false truncation flag repairs.
- The gateway labels accepted segments `model_claim`. Tool results are not
  supported by this API. They become a loss/invalidation using the actual known
  invocation, never text relabeled as a model plan or executor success.
- Sequence/revision are monotonic within this instance's registered scope. Loss
  increases `dropped`; `upstream_gaps` remains `unknown`. Full source identities
  come only from observed middleware invocations. Missing identities are not
  fabricated to send a loss marker; local loss is carried by later known events.
- Queue loss and HTTP errors attempt a metadata-only invalidation after queued
  events; already queued events also inherit cumulative drops before transmission.
  A final lost event therefore does not require a subsequent agent callback to
  attempt notification. The gateway conservatively fences exact eligibility for
  its boot on drop/invalidation. If the network/authentication also prevents that
  notification, delivery cannot be guaranteed; loss is retained locally and in
  future events, never represented as successful completion.
- No event is retried, reopened, or rebound. An early `409` (physical teardown not
  yet complete) is conservatively treated as loss. The current contract permits
  identical unaccepted-revision retries, but this narrow bridge does not rely on
  disambiguating early/replay/conflict `409` responses.
- Source flags describe only middleware-invocation association:
  `physical_routing_eligible=false`, uniqueness `unproven`, stream association
  `unsupported`. Physical dispatch counts, exactness, replayability and mandatory
  continuity/pins remain gateway-owned.

## Current API mismatch (do not silently work around it)

The frozen gateway source API requires nonempty text for an accepted response;
metadata-only `response` returns **400**, then our explicit loss invalidation
returns **409** while fencing source eligibility. Metadata mode therefore cannot
establish semantic completion or a cheaper-route snapshot. The bridge never opts
into text or invents a segment to obtain 202. This behavior was exercised against
the actual C binary, not inferred from a mock. Separate metadata-only completion
would require a future server contract decision; no C gateway changes are made
in this branch.

## Verification

```sh
python3 -m unittest deploy.hermes.test_context_adapter deploy.hermes.test_gateway_bridge -v
RECURSANT_CONTEXT_BRIDGE_BIN=/absolute/path/to/context-enabled/recursant \
  python3 -m unittest discover -s tests/integration -p test_gateway_bridge_live.py -v
```

The first suite uses real stdlib loopback HTTP capture with controlled stall,
slow-drip and queue fixtures. The second launches the supplied C production binary
and scripted loopback provider/interpreter, proving authenticated open, physical
HTTP identity tags, 202 ingestion, `model_claim` provenance, and current metadata
400/loss409 behavior. No external endpoint, real model, installation, live profile,
service or credential file is touched. Timing bounds are fixture safety assertions,
not production latency measurements. No native AIAgent closed-loop, semantic
accuracy, dollar savings, deployment readiness or full M3 acceptance is claimed.
