# R1–R3 runner repairs — parent re-review required, NOT live approval

Base: `45c1de43524330c3b152cbdd58028282b3c63f27` in the isolated `recursant-v4-m3-full-task-evaluation` worktree. Production edits are confined to `bench/evaluation/live.py`. No core gateway, observer, main-checkout, serving/profile, credential, dependency or image changes. No inference, installs, downloads, pulls or pushes.

## Original independent failure remains authoritative history

Read the entire parent report, including both embedded reproduction scripts:
`/home/aj/projects/recursant-v4/docs/evidence/m3-full-task-runner-review.json`.
Its SHA-256 is `583661e243d2a237b31265fca33cbf06eb2b4472d4b028262e4dd8b01d61202a`.
`original-review.json` is an unchanged copy, still `FAIL_DO_NOT_RUN_LIVE`. The original committed fixture result and tests log were not modified. All earlier failed attempts and review artifacts were left in place. New test logs use new paths; no RED or intermediate run was overwritten.

## Vertical TDD evidence

| Slice | Observed RED before implementation | GREEN |
|---|---|---|
| R1 public egress | `r1-red.log`: real C route returned 502; exact final-M2 control rejected by nonfixture admission | `r1-green.log`: C route reaches one loopback provider, metered once; exact `allow_fallbacks:false` accepted and routing/pricing extensions rejected |
| R2 SSE prefix/raw evidence | `r2-prefix-red.log`: all comment/event prefixes return 502 | `r2-prefix-green.log`: byte-identical relay, usage and durable exact evidence retained |
| R2 optional detail null | `r2-null-red.log`: `None.get` AttributeError | `r2-null-green.log`: null optional details become unknown, actual usage/cost retained |
| R2 error tails | `r2-tail-red.log`: missing provider error, lost earlier usage, nonobject AttributeError | `r2-tail-green.log`: valid error envelope relayed unchanged and marked; malformed tails return 502 without losing prior usage/raw |
| R2 usage semantics | `r2-semantics-red.log`: malformed tail changed retained usage semantics to unknown | `r2-semantics-green.log`: known inclusive semantics/tokenizer retained |
| R3 allocation ceiling | `r3-red.log` and corrected-isolation `r3-red-isolated.log`: $9.9900001/$10 accepted; create/egress bypass caps | `r3-green.log`: Decimal cap <=$9.99 and integer physical count <=188 enforced at all three boundaries |
| R2 event delimiter | `r2-framing-red.log`: a single terminal newline incorrectly dispatched an incomplete SSE event | `r2-framing-green.log`: blank event delimiter required |

The first R3 test reused an allocation filename across subtests, so the second invalid case encountered FileExistsError. The revised test gives each invalid cap its own filename and independently exercises create/egress; all six intended failures were then observed before production edits. Both logs are retained.

Additional regression tests exercise multiline data, CRLF/BOM, explicit Content-Type precedence, JSON documents, unknown usage/error-only streams, bounded oversized evidence, read-only real recording replays, exact public liability admission even after parsing failure, refusal one micro-dollar below liability, 188 real local loopback dispatches with the 189th refused, failed fsync refusing network, incomplete crash recovery, and allocation reuse refusal. These are protocol/accounting controls, not model quality results.

## Implementation limits and evidence semantics

- R1 allows exactly the final-M2 provider dictionary containing only a literal boolean `allow_fallbacks:false`. `0`, true, null, empty objects, order/only/sort/max_price and unknown provider extensions remain rejected. Existing model/output/context/server-tool negative controls remain green.
- R2 chooses SSE using normalized response Content-Type, with a legacy data-first fallback only when MIME is absent. The complete response remains buffered, bounded at 16 MiB (+ one overflow-detection byte). The parser honors SSE framing, ignores comment/event/id/retry/unknown fields, joins multiline data, and incrementally updates observed usage instead of building a full JSON-record list. It is evidence extraction, not native streaming/replay-completion authority.
- Before JSON/SSE interpretation, exact response bytes are stored in a mode-0600, fsynced, per-dispatch `.response.private.bin`; traces retain bounded decoded text. `provider_response_ref` links the journal. On overflow only the first 16 MiB are retained, `provider_response_truncated=true`, and `provider_response_sha256` hashes the bounded bytes read including the overflow sentinel byte, not an unseen full body. A valid SSE provider error remains the provider's original HTTP/body and sets `error=provider_error`; a malformed event returns 502 but does not refund its reservation or erase earlier usage.
- R3 leaves the separate 12-local/$0.01 reservation outside B. $9.99/188 is a maximum, not a fresh allocation. Parent must reconcile earlier usage and issue an independently reviewed smaller subset when needed. Reference strings are metadata, not cryptographic approval. The allocation journal remains exclusive-create/no-resume with reservations fsynced before connection. Cross-process allocation identity and power-loss directory-entry durability remain outside this repair's qualification.

## Executed verification

Run from the isolated worktree:

```sh
docker run --rm --pull=never --network=none \
  --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work \
  recursant-v4-dev:local bash -lc \
  'cmake -S . -B build/runner-fixes -DCMAKE_BUILD_TYPE=Debug && cmake --build build/runner-fixes -j2'

M3_DOCKER_TEST=1 \
M3_ROUTER_BINARY="$PWD/build/runner-fixes/recursant" \
M3_REPLAY_WIRE_DIR=/home/aj/projects/recursant-v4/.hermes/runtime/m3-live \
python3 -m unittest bench.evaluation.test_evaluation \
  bench.evaluation.test_runner_regressions \
  bench.evaluation.test_stream_regressions tests.test_accounting -v

docker run --rm --pull=never --network=none \
  --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work \
  recursant-v4-dev:local ctest --test-dir build/runner-fixes --output-on-failure
```

- `tests-final.log`: **45 tests, all passed, zero skips**. This includes both actual pinned-Hermes Docker tests, the original C lifecycle test, new real-C/nonfixture public-admission loopback, all new budget/SSE tests, both authorized recording replays and existing accounting tests. `tests-full.log` preserves the earlier 44-test pass before the delimiter regression was added.
- `ctest.log`: **17/17 CTest targets passed**, including the existing gateway, interpreter, observer, compliance, transport, admission, reference and accounting suites. C/core and observer source was unchanged.
- `build.log`: clean successful local build from this frozen base. Binary SHA-256: `1a523cd903e3f273f002c6210b63f1ca45928d65376829819e722ca89d4a3af7`.
- Existing dev image ID: `sha256:2b5edaf312e5fff935ce0dfe8ae251bd6629393742a9bf236e7b4455b49f70f7`.

Read-only authorized recording hashes, checked before and after replay (raw recordings NOT committed):

- `gpt-4.1-wire.sse`: `01ef7d422121fc7f116a60002ad5c066569ba76623d5e3b83e5053347c237d8a`
- `gpt-4.1-mini-wire.sse`: `7a4df822b2d145232f016c7d9251e92d731f896383d42c7fefe584c60fe62589`

Both contain actual previously captured usage tails (11 prompt / 2 completion, reasoning/cache 0; costs $0.000038 and $0.0000076 respectively). Replaying these bytes incurs no provider inference. Comment/event-prefixed mutations are explicitly synthetic protocol cases. Nonfixture tests exercise production admission/journaling, but their loopback dispatch records do not establish new live inference or economic evidence.

Pre-commit added-code security scan found no hardcoded secrets, shell injection, eval/exec, pickle or interpolated SQL patterns. Optional ruff/mypy are not installed; none were installed. Source/document whitespace checks pass. The repository-wide whitespace check flags trailing spaces emitted by unittest on six lines of retained RED logs; these raw logs were deliberately not rewritten. Original fixture evidence, core and observer match `45c1de4` exactly.

**Pending:** parent independent re-review of the committed repairs, merged native gateway qualification, actual filled/reviewed allocation and all other pending items in the original report. This implementation self-check is not an independent approval and does not change `release_gate=false`.
