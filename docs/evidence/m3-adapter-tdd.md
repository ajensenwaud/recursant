# M3-A narrow request-bound adapter evidence

## Result and scope

PASS for the **narrow causal integration slice**, not the complete M3-A gate or M3.
Real, unmodified pinned Hermes and its real terminal tool executed against an
**explicitly SYNTHETIC scripted loopback HTTP provider**. No semantic model ran;
provider text and usage are fixtures, not inference/quality/cost measurements.
No install, image build/download, paid API call, personal profile modification,
router change, or existing observer change was made.

- Image actually executed: `sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b`.
- Hermes source: `d0288be5b3330d2442e3907185b8e9d0958297bb`.
- Probe verifies source HEAD and clean git status inside the image before import.
- Registration uses actual `PluginContext.register_middleware('llm_request', ...)`
  and actual observer registration/dispatch, not a substituted AIAgent.
- Completed response and attributable terminal result were consumed from AF_UNIX
  datagrams in the next `pre_api_request` observer, **before next HTTP dispatch**.
  The HTTP provider independently asserts that this check already happened.
- Both content-disabled and explicitly content-enabled runs pass. Each has exactly
  two inference HTTP requests, two completed response events, one tool event,
  exact header-to-event joins, and zero adapter send drops.
- The real terminal result is parsed as JSON and checked for exit code 0 and the
  exact synthetic marker. Final result must be completed with the exact scripted
  final response and no failed/partial/interrupted flag.

## TDD record

Each behavior below was introduced by an executed failing stdlib unittest, then
minimal adapter changes, then an executed green suite. No production behavior was
written ahead of its failing test. Related regression assertions were extended
vertically, rather than implementing the whole imagined interface at once.

| Slice | Observed RED | Observed GREEN |
|---|---|---|
| Disabled | `context adapter not implemented` assertion | 1 test |
| Exact base URL, header-only copy, bounded IDs, unique invocation token | `llm_request` missing | 2 tests |
| Completed response allowlist/content opt-in, retry and missing identity | `post_api_request` missing | 3 tests |
| Explicit tool join, interleaved branches and reordered tool callback | `post_tool_call` missing | 4 tests |
| Bounded nonblocking datagrams, loss counter, lifetime state cap | `nonblocking datagram sink missing` | 5 tests |
| Actual Hermes tool status vocabulary | `unknown != ok` | 5 tests |
| API error invalidation, reserved-header collision, bounded call counter | `api_request_error` missing | 6 tests |
| Incomplete/duplicate completed response | `True is not false` | 7 tests |
| Machine-readable invocation-vs-physical association boundary | missing association scope (then explicit assertion failure) | 7 tests |

Final offline command, from repository root:

```sh
python3 -m unittest discover -s deploy/hermes -p 'test_*.py' -v
```

Actual result: **11 tests, OK** (7 new adapter tests plus 4 existing observer/smoke
regressions). No C files changed; no C build/sanitizer result is claimed here.
`git diff --cached --check` passes. Static added-line scan found no shell=True,
os.system, eval/exec, or pickle use; its one credential-literal match is the
explicit synthetic loopback API key, not a credential. Independent review remains
for the parent before merge: this focused subagent has no delegate/reviewer tool,
and did not spawn another paid model call. The commit is not labeled independently
verified.

## Reproducible isolated runtime command

Run from the worktree root. Code files/directories must be readable/traversable
by UID 65534 (`chmod a+r` files, `chmod a+rx` adapter directory).

```sh
for mode in metadata content; do
  args=()
  if [ "$mode" = content ]; then args=(--content); fi
  docker run --rm --pull never --network none --read-only \
    --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /tmp:rw,nosuid,nodev,mode=1777 --workdir /tmp \
    -e HOME=/tmp/probe-home -e HERMES_HOME=/tmp/probe-hermes \
    -e PYTHONDONTWRITEBYTECODE=1 -e TERMINAL_ENV=local -e HERMES_YOLO_MODE=1 \
    -v "$PWD/deploy/hermes/context_adapter:/probe/context_adapter:ro" \
    -v "$PWD/bench/hermes_context_probe.py:/probe/run.py:ro" \
    --entrypoint python \
    sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b \
    /probe/run.py "${args[@]}" || exit
done
```

Only the owned adapter directory and probe file are mounted read-only. No project
root, secrets, Docker socket, host home, or personal Hermes profile is mounted.
The provider and Hermes run in the **same network-none container**, using its
loopback device. Fresh HOME/HERMES_HOME and runtime files live only in container
tmpfs; no raw artifacts are persisted to the host or committed. Synthetic tool
approval is restricted operationally by this isolated disposable container.

Actual successful metadata (both runs differ only in `content_enabled`):

```json
{"adapter_dropped":0,"consumer_ready_before_next_dispatch":true,"content_enabled":true,"headers_exact":true,"hermes_sha":"d0288be5b3330d2442e3907185b8e9d0958297bb","physical_attempt_uniqueness":"unproven","provider":"SYNTHETIC scripted loopback; no semantic inference","requests":2,"responses":2,"stream_association":"unsupported","terminal_executed":true,"tool_events":1,"upstream_gaps":"unknown"}
```

## Adapter contract / explicit integration requirement

This is a small embeddable supported-middleware adapter, not an automatically
installed user plugin. Use `install(ctx, enabled=True, endpoint=exact_base_url)`,
then `adapter.configure_sink(private_unix_datagram_path)`. Text defaults off;
`adapter.content_enabled = True` is explicit content authorization. Configure
before starting the agent and call `adapter.close()` during shutdown. Disabled
installation returns None without hooks, sockets, workers, or other resources.
No workers are created even when enabled.

Only the `llm_request` middleware changes requests, and only their
`extra_headers`, preserving existing nonreserved headers and all body parameters
(prompt/history/model/tools/budgets). It compares the **Hermes base_url string**
exactly to the configured API base URL; it does not normalize slashes, match
prefixes, or guess the eventual HTTP path. Reserved-header collisions abstain.
The correlation header names are `X-Recursant-task-id`, `-session-id`, `-turn-id`,
`-api-request-id`, `-api-call-count`, and `-attempt`. Four identity strings must
be nonempty printable ASCII, at most 128 characters. Call count must be an int
(not bool) from 0 through 999999999. Values are not parsed, repaired, or hashed.
**These headers are correlation, never tenant authentication or authority.**

A random attempt token is assigned per accepted middleware invocation. State
keys contain the explicit task/session/turn/request tuple; opaque IDs are never
split. Logical request IDs can recur during retries. Any repeated invocation,
observed error, duplicate response, or incomplete finish invalidates exact
eligibility for that identity. Tool observations additionally require a prior
attributed completed response containing the exact tool-call ID. No temporal,
"last request", prompt-similarity, or cross-branch guess is used.

Export is a fresh allowlist: identity/association metadata, limited tool status,
and optional bounded strings only. The normalized `assistant_message.content`
and `.reasoning_content` are the only response text sources. Raw provider
responses, request bodies, tool arguments, arbitrary extra hook fields, encrypted
reasoning details and credentials are not serialized. Text is truncated to 2048
characters per field; tool-call associations are capped at 32 per response.
This allowlist is **not** a claim of PII redaction inside authorized text.

State retains at most 256 logical identities for the adapter's lifetime, with no
eviction that could turn an old retry into a new exact match. After capacity,
new requests still get headers but their response/tool association is missing and
text/outcomes are ineligible. Recreate only at an explicit isolated run boundary.
A datagram is capped at 24576 UTF-8 bytes. Send is nonblocking, no retry/HTTP export
or disk persistence; failures increment a local drop count. Sequence and drop
counts describe adapter emission only; **upstream gaps remain unknown**. Consumer
must enforce its own receipt/sequence/freshness rules, revoke ambiguous facts,
and retain baseline routing on incomplete feeds. This slice does not implement
a production authenticated receiver or a router policy consumer.

## Source findings and limits

Read from the pinned image using `--pull never --network none --entrypoint python`:

- `agent/turn_api_request.py` passes explicit task/session/turn/request IDs and
  call count into supported `apply_llm_request_middleware` before the pre hook.
- `hermes_cli/middleware.py` accepts `{'request': dict, 'source': ..., 'reason': ...}`.
- `agent/turn_response_intake.py` emits explicit identities and normalized
  `assistant_message` at `post_api_request`, before tool execution/next request.
- `agent/api_request_hooks.py`'s response dictionary omits reasoning; therefore
  the adapter selects only explicitly exposed text from normalized message.
- `model_tools.py` emits explicit API and tool-call IDs; its successful status
  is `ok`, not `success` (the runtime exposed this during the RED phase).

Important limits:

1. `association_scope=middleware_invocation`: `routing_eligible` describes only
   this logical evidence join. **Physical routing eligibility is always false**;
   `physical_attempt_uniqueness=unproven`. SDK/transport retries can reuse one
   header token below the hook. No physical-attempt uniqueness, exact billing,
   or retry-free transport claim is made. A consumer requiring physical attempts
   MUST abstain. Retry ambiguity at observed middleware/hook level drops text and
   tool outcome eligibility. Retry fallback was tested with callback fixtures,
   not a successful live provider-retry scenario.
2. Streams are not subscribed to or attempt-authoritative. Their missing IDs,
   retries, drops and reordering cannot be repaired by arrival order. Only
   completed normalized response text is supported; encrypted/other reasoning
   representations are deliberately excluded. No token-live semantic feed claim.
3. Interleaved parallel branch isolation and reordered/missing callback fallback
   are covered by unit fixtures. Actual simultaneous multi-agent callback safety,
   distributed branch/auth authority, load/backpressure and full retry matrix are
   **not established** by this single-agent runtime proof.
4. Delivery was proven before subsequent inference with a diagnostic pre-request
   consumer drain. The adapter itself does not await a receiver. Production async
   readiness and latency/SLO coverage remain separate gates.
5. No automatic model selection, semantic interpreter, savings, task quality,
   real-model inference, or complete M3 acceptance is claimed.

Runtime debugging found a real Hermes `/api/show` capability lookup before model
inference; the synthetic provider now responds 404 to that metadata lookup and
does not count it as inference. Initial failing probe stopped on that path; a
subsequent failure exposed the actual `ok` tool status. Both were diagnosed from
real image source/output, not replaced with invented successful results. Probe
assertion failures now exit immediately to avoid upstream retry sleeps. The pinned
upstream `pm/shell.py` emits a Python SyntaxWarning for its `\W` docstring escape;
upstream was left unmodified. Final isolated runs exited 0 despite that warning.
