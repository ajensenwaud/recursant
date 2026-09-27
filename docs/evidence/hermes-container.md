# Isolated vanilla Hermes container baseline

Status: **direct private smoke passed**. This is a harness/tool/observer integration result, not a token-efficiency benchmark or M3 context-engine result.

## Verified identities

- Upstream: `https://github.com/NousResearch/hermes-agent.git`
- Source SHA: `d0288be5b3330d2442e3907185b8e9d0958297bb`
- Image: `recursant-v4-hermes:local`
- Exercised image ID: `sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b`
- Base: `python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d`
- Observer Python SHA-256: `a4ed9ee5fcf691dd973c07bca3128268b95e5c0337d4de2376ca9f5ce6dcaef8`
- Observer manifest SHA-256: `74142249fa82976b4a04a94c1100d6e7402fddb304b74add572339b211eb80ed`

The wrapper verifies exact HEAD and empty `git status --porcelain` before loading upstream. An independent, offline, read-only container verification also passed after the smoke. Upstream source is not patched. Installation is the upstream default Python dependency set, not stage2 OS extras. `pip check` passed; the image contains 65 Python distributions. Apt and transitive dependencies are not fully lockfile-pinned: reuse the verified image ID for comparison, rather than assuming future builds are byte-identical.

## Reproduce

From the repository root:

```sh
docker build -t recursant-v4-hermes:local deploy/hermes
python3 -m unittest discover -s deploy/hermes -p 'test_*.py'
python3 bench/hermes_smoke.py
```

The exercised inference command was `python3 bench/hermes_smoke.py`, using `http://gx10:8888/v1` and model `GLM-5.3-Flash-EXL3`. The runner resolves gx10 on the host and supplies a container-local `--add-host` entry. It does not change host networking; the resolved private address is not published in this report.

For a later private routed smoke, reuse the **same image ID and observer**:

```sh
python3 bench/hermes_smoke.py \
  --image sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b \
  --label routed \
  --network container:ROUTER_CONTAINER_NAME \
  --base-url http://127.0.0.1:8080/v1
```

Replace `ROUTER_CONTAINER_NAME` with the parent's router container, configured to route this model exclusively to the approved private endpoint. Network namespace sharing does not share its filesystem, secrets, or Docker socket. Loopback endpoints are rejected without container network sharing. The runner rejects public endpoint addresses and host networking; it cannot validate a router's downstream policy. Routed integration is left to the parent; only direct private inference was exercised here.

## Execution and isolation

`deploy/hermes/run.py` calls the pinned upstream `AIAgent.run_conversation` Python API, not a reimplementation or a CLI transcript replay. The source constructor and hook discovery/dispatch were inspected at the pinned revision. Stock tool selection, prompt construction, memory/context behavior and reasoning defaults are retained. Explicit test settings are the private custom Chat Completions provider, max 3 iterations, max 2048 tokens per request, 180-second agent budget and quiet output. The host runner enforces a 240-second wall deadline. No public-provider credentials enter the container.

Every run uses fresh tmpfs-backed `HOME=/isolated/home`, `HERMES_HOME=/isolated/hermes`, `/workspace` and `/tmp`. Only that run's ignored artifact directory is bind-mounted. The root filesystem is read-only, the user is the invoking host UID/GID, all capabilities are dropped, privilege escalation is disabled, and CPU/memory/PID limits are set. No host profile, personal memory, local Hermes source, credentials, repository workspace or Docker socket is mounted. The new synthetic profile enables only the observer and reasoning-delta opt-in; no active user profile is read or modified.

The synthetic task asks for one `terminal` call running `printf ROUTING_OK`, followed by a matching final response. Tool execution acceptance requires a `post_tool_call` with name `terminal`, status `ok`, result exit code 0 and exact expected output; merely mentioning a command is insufficient.

## Observed result

Run: `20260927T032422Z-37548511`; elapsed 31.329 seconds; container exit 0; completed true. Actual terminal execution and the exact final-response check both passed.

| Hook | Count |
|---|---:|
| on_session_start | 1 |
| pre_api_request | 2 |
| post_api_request | 2 |
| on_stream_start | 2 |
| on_stream_delta | 11 |
| on_stream_end | 2 |
| post_tool_call | 1 |
| on_session_end | 1 |

Of the stream deltas, 10 were reasoning and 1 text. Both observed main requests targeted the approved private URL and had `max_tokens=2048`. Both response hooks contained usage objects. No API-error, auxiliary-call or observer-storage-limit events were observed. Missing auxiliary events do not establish broader auxiliary accounting completeness.

The observer registers only read-only hooks: request pre/post/error, auxiliary pre/post, stream start/delta/end, post-tool, session start/end and agent-loop-stopped. It registers no modifying pre-tool/pre-LLM hooks, transforms, providers or execution wrappers, and every callback returns `None`.

## Private artifacts and limits

All raw artifacts remain local and git-ignored:

- `.hermes/runtime/hermes/20260927T032422Z-37548511/summary.json` — metadata-only status/counts.
- Same directory: `command.json` (exact Docker argv), `source.json`, `events.jsonl`, `result.json`, `console.log`.
- Raw `events.jsonl`: 116260 bytes in the passing run.
- Build logs: `.hermes/runtime/hermes/build.log`, `build-editable.log`, `build-permissions.log`.

The runner checks `git check-ignore` before starting and creates run directories mode 0700, files under umask 077. Observer storage is capped at 8 MiB; it stops with a metadata truncation marker rather than rotating away earlier records. Console capture is capped at 4 MiB; individual wrapper files have a 16 MiB OS file-size limit; transient profile/workspace storage has tmpfs caps. Runs are individually bounded but historical run directories are retained until explicitly removed; do not publish/commit raw traces or chat/reasoning bodies.

Stream completeness remains **unknown**: upstream uses bounded per-callback queues that can drop oldest events, and separate event dispatchers do not promise global ordering. Observer sequence numbers mean arrival order only. Stream IDs lack an explicit request-attempt identity, so exact retry/request joins must not be inferred. Usage objects are retained, but provider-boundary reconciliation and the gross-input accounting adapter remain separate work. No cost or token-efficiency claim is made.

## Issues and verification

1. Initial non-editable `pip install /opt/hermes` failed because pinned upstream intentionally rejects wheel/sdist builds. Fixed **inside the Dockerfile only** with supported editable installation, `pip install -e /opt/hermes`; upstream-generated untracked packaging metadata is cleaned before integrity checks. No dependency pins were changed.
2. First container start failed before upstream ran because copied wrapper files were not readable by the non-root runtime UID. Added image-local `chmod -R a+rX` for wrapper/observer. That preflight attempt had zero hooks and no inference; artifact directory `20260927T032349Z-b084980b` preserves the error.
3. The next run passed and is the only model-using smoke executed by this baseline task.
4. Three offline stdlib tests passed: observer read-only/bounded behavior, terminal-success acceptance (including negative cases), and private/loopback endpoint validation. Failing tests were observed before implementing their corresponding behavior.

No host installation, model download, inference service change, commit or push was performed.
