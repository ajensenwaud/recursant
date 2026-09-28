# Native Hermes request profile: operator-qualified requirements

Status: implemented on branch `m3-native-profile` (from `aceb40d`). Scripted
loopback providers only. This is not model-quality, savings or live-acceptance
evidence.

## Problem

Real pinned Hermes (`d0288be5`) sends every main request as `stream:true`,
`stream_options:{include_usage:true}`, `reasoning_effort:"medium"`, with 19
function tools whose parameters are nested JSON Schema (`items`, `anyOf`,
`enum`, `default`, ...). The tools serialize to about 36.6 KB. `tool_choice`
and `parallel_tool_calls` are absent. The gateway used to treat each of these
features as an unsupported option and set a permanent scope pin, so routed arms
could never leave the baseline (pilot review B1).

## Contract

The router forwards the request body verbatim. Only `model` changes, plus the
existing adapter egress control. Nothing is stripped, normalized or rewritten.
Portability is therefore a property of the **destination**, and the operator
declares it per candidate:

```json
"capabilities": {
  "tool_history": true, "function_tools": true, "parallel_tools": true,
  "stream_tools": true,
  "nested_tool_schemas": true,
  "reasoning_effort": ["low", "medium", "high"]
}
```

- `stream_tools` (bool): the destination accepts `stream:true` with `tools` and
  streams `tool_calls` deltas that the existing observer/assembler
  (`response_observer.c`, `stream_tools.c`) can capture.
- `nested_tool_schemas` (bool): the destination accepts function `parameters`
  beyond the legacy flat primitive subset, or tool sets beyond 32 tools or 16 KiB.
- `reasoning_effort` (array of 1..8 unique printable tokens, each <=64 bytes):
  the exact spellings the destination accepts. They are matched byte for byte and
  never interpreted.
- Validation is strict. Wrong types, empty or duplicate lists, and unknown keys
  all reject the configuration. An absent key means unsupported, so existing
  configurations behave exactly as before.

**Operator attestation label.** These declarations are attestations by the
operator about the destination's API. The gateway does not probe them, and
declaring them grants no quality qualification. `qualified_tasks`,
`quality_evidence`, price and M2 still govern placement.

### Request parsing (`request_options` / `tool_definitions`)

| Request feature | Before | Now |
|---|---|---|
| `stream:true` + `tools` | pin | requirement `STREAM_TOOLS` |
| `reasoning_effort` (printable token, <=64 bytes) | pin | requirement: every non-baseline owner/destination lists the exact token |
| nested `parameters`, >32 tools or >16 KiB | pin | requirement `NESTED_SCHEMAS` |
| unknown top-level key (e.g. `reasoning`, `future`) | pin | pin (unchanged) |
| malformed values (non-token effort, `strict`, non-object parameters, bad names, duplicate names) | pin | pin (unchanged) |

Hard bounds, all of which pin when exceeded:
- at most 64 tools;
- compact serialized tools of at most 65,536 bytes;
- each `parameters` value must be an object of depth <=24 (root = 0);
- at most 16,384 schema nodes across all tools.

Outer tool/function keys stay strict: only `type/function` and
`name/description/parameters`. Names must be unique printable tokens of at most
64 bytes, and descriptions at most 4,096 bytes. Named `tool_choice` validation
is unchanged.

### Sticky per-scope contract

The first request of a scope records a deep copy of its projection: `tools`,
`tool_choice`, `parallel_tool_calls`, `reasoning_effort` and, for profile
scopes, `stream_options`. A scope becomes a profile scope when the scope or the
current request carries any native feature (streamed tools, nested or large
tools, or `reasoning_effort`). In a profile scope, any later request whose
projection differs pins the scope permanently: a changed, added or removed
field, including going back to the original. Legacy narrow scopes (flat
nonstream tools, no effort) keep their pre-existing behaviour. Changing into a
profile shape mid-scope is itself a difference and pins.

### Owner and destination

Requirements accumulate in `s->requirements`, alongside the tool-boundary bits.
A non-baseline candidate is permitted only if it declares every requirement bit
and lists the scope's exact effort token. The baseline is exempt, as before: it
stays usable as the pinned or undeclared owner. Existing rules still hold:
- explicit aliases cannot move an owner of a requirement-bearing scope;
- a private-only (M2) scope cannot silently retarget a public owner (403 before
  egress);
- exact tool-boundary replay, qualification, cost/cache penalty, S4 signals and
  final M2 are unchanged.

### Pilot-relevant config (full-task-evaluation `live.example.json`)

Add the same `capabilities` object to both the `baseline`
(`openai/gpt-4.1`) and `economy` (`openai/gpt-4.1-mini`) candidates, labelled as
operator attestation. `config/recursant.context.fixture.example.json` in this
repository shows the shape. That file lives in another worktree and is not
edited here.

## Residual risks

- Declarations are unverified operator claims. A wrong `stream_tools` claim
  surfaces as a destination error or as an uncapturable stream, and either one
  pins.
- Exact tool-boundary replay still caps history at 32 KiB and 128 messages
  (`RC_TOOL_MAX_BYTES`). Real Hermes history grows about 1 KB per tool step
  (5.4 KB to 8.3 KB over 4 turns), so long sessions will eventually pin at that
  bound. This is a separate follow-up.
- Nested schema content is treated as inert data, not validated JSON Schema. A
  destination may interpret it differently from the baseline.
