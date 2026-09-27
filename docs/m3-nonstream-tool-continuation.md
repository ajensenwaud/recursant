# Nonstream tool continuation — integration slice, review pending

This is an actual C gateway + Python source-bridge slice, not full M3 or native
Hermes acceptance. It depends on the plain-SSE commit `51edafd` (still in review),
the byte-identical tool-boundary library (still in review), and approved
metadata-only ingestion `75e868f` (cherry-picked here as `ae5c983`). Parent owns
integration and independent review. No live inference or model-quality claim.

## Request qualification

The existing request fields remain supported. `max_tokens` must be integer
1..100000; optional `temperature` is finite numeric 0..2 and `top_p` 0..1.
New portable fields are `tools`, `tool_choice`, `parallel_tool_calls`, only for
nonstream requests. Missing/false `stream` is nonstream; `stream:true` with tools
still pins. Unknown options, including `reasoning_effort: "medium"`, pin rather
than being removed or treated as harmless.

This deliberately narrow function-definition subset requires:

- `tools`: array of 1..32 objects containing exactly `type:"function"` and
  `function`. Serialized definitions together are at most 16384 bytes.
- `function`: required unique printable nonempty `name` up to64 bytes and
  `parameters`; optional string `description` up to4096 bytes. No other keys.
- `parameters`: `type:"object"`, `properties` object, `additionalProperties:false`,
  optional `required`. At most32 properties. Property names are nonempty and
  <=64 bytes. Each property contains `type` from string/integer/number/boolean
  plus optional <=4096-byte description. Required names must exist and be unique.
  Nested objects/arrays, enum, `$ref`, strict, defaults and unknown schema keywords
  are unsupported and pin, not silently ignored.
- `tool_choice`: absent, `auto`, `none`, `required`, or exactly
  `{"type":"function","function":{"name":"<declared name>"}}`.
- `parallel_tool_calls`: absent or boolean. Absence is conservatively treated
  as requiring parallel capability; false limits observed calls to one.

No tool definitions, arguments, IDs, results or request options are normalized,
stripped or repaired. The existing router parses/reserializes JSON and rewrites
model; this is **not** raw request whitespace/key-order byte preservation.
Decoded string bytes (including arguments) remain unchanged. Existing mandatory
M2 provider options are unchanged. Upstream response bytes are forwarded exactly.

## Authority and lifetime

Only successful completed nonstream transport with one index-0 assistant choice
and `finish_reason:"tool_calls"` can capture a boundary. The gateway validates
root/choice keys, typed id/model/object/created/usage and the existing explicit
inert-null envelope fields. This stricter metadata check also covers nonstream
`stop` responses in tool-enabled scopes. Meaningful reasoning/provider opaque
state remains pinning. Tool names must occur in observed request definitions;
`none` cannot yield portable calls, and a named choice must match every call.

The library owns snapshots under the gateway lock. It checks strict portable
messages, <=32768 bytes per input, <=128 messages and <=32 globally distinct call
IDs across history, ID length <=128 bytes, and no already-pending historical
exchange. Capture means observed calls, not tool completion or execution success.

The next request must equal captured prior history + observed assistant + exactly
one contiguous string result per pending ID, with no extra user/assistant entry.
Parallel result order may differ. A valid shorter prefix receives409 without
upstream dispatch, consuming a physical attempt or destroying its boundary.
Malformed/duplicate/foreign IDs, modified history or unsupported state permanently
pin the owner. A later clean response cannot clear that pin. Snapshots are freed
only under lock when dispatch consumes them or the quiesced gateway is destroyed.
After completion and a normal assistant response, exact full historical replay
can continue with appended user messages; tool requirements remain cumulative.

## Candidate gates

Candidate objects optionally contain:

```json
"capabilities": {
  "tool_history": true,
  "function_tools": true,
  "parallel_tools": true
}
```

Only these boolean keys are accepted; absent means unknown, false means unsupported.
`function_tools` qualifies the entire narrow definition/choice contract above.
Tool exchanges additionally require `tool_history`; multiple calls or possible
parallel generation require `parallel_tools`. No implicit true defaults.

The existing baseline remains usable without new declarations; alternatives
need all required known-and-supported bits plus the existing operator quality
identity/task qualification, context capacity, cheaper expected-task cost,
fresh exact same-row interpretation, and M2 permission. These declarations are
not empirical capability or quality verification. Explicit scoped destination
changes in tool-enabled workflows receive403 rather than bypass these gates.
Final M2 still runs; if it would redirect an established tool workflow away from
the selected destination, the slice rejects403 instead of inventing an unqualified
recovery route. Unassociated baseline M1/M2 behavior is unchanged.

## Source tool callbacks

The bridge now exports supported `kind:"tool"` literally; it does not relabel it
as a model response or invent `stream_association`. The gateway requires the
ordinary exact scoped completed physical-row join and an ID actually observed in
its authoritative assistant calls. Duplicate callbacks are409, foreign IDs403;
invalid status/shape/content is400. Existing ambiguity, source loss, scope and
revision/sequence fences remain mandatory. A callback is neither a replay result
nor permission to switch: the actual next request still needs the complete replay.

`status` is exactly one of ok/success/error/blocked/cancelled/unknown. Both `text`
and `text_truncated` absent means metadata-only:202, advance revision, invalidate
older advice, and no interpreter work. Null/empty/partial/truncated/oversized text
is not metadata-only. With content enabled, only nonempty `text.tool_result`
<=1024 UTF-8 bytes and matching `text_truncated.tool_result:false` is admitted.
The private interpreter receives `tool_result` and separate literal `tool_status`
segments, each `source:"executor"`. This is source-hook provenance, not inference
of tool success from its output. M2 scans both segments. Loss/truncation remains
visible; the bridge retains the original loss behavior for unsupported events.

## Exact remaining native blockers

Parent's actual pinned Hermes synthetic request had `stream:true`,
`reasoning_effort:"medium"`, stream options and four tools (messages4265/4595
bytes; request12486/12816 bytes). This slice does not make that traffic portable:

1. Streamed tool deltas need bounded indexed/id/name/argument assembly and a
   completed authoritative tool-call handoff from the SSE observer. Unchanged
   SSE dependency still pins tool deltas.
2. Reasoning effort and meaningful returned reasoning/opaque continuation require
   an explicit request/candidate/state contract. Never drop `medium` to pass.
3. Real tool definitions outside the flat schema subset need explicit qualification.
4. Real pinned-harness hooks/transport timing must be tested end to end. Current
   bridge loopback test calls production Adapter hooks but does not run Hermes.
   Exporter early-arrival/retry/loss behavior is unchanged and can still fail closed.
5. Real model quality, semantic accuracy, dollars and full-task M3 gates remain open.
