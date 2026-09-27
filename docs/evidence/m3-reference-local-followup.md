# Live local interpretation: larger output budget and structured condition

This supplements, rather than replaces, `m3-reference-gx10-first.md` and its original results. User approved a larger output budget and subsequently explicitly approved **180 seconds for all future calls**. Local latency alone is not an acceptance failure; readiness must be measured against actual asynchronous routing opportunities.

## Preserved conditions

| Condition | Requests dispatched | Result |
|---|---:|---|
| Original prompt, 1,024 output tokens, 60s | 6 | 2 strict-schema/label matches; 3 length-limited; 1 fenced JSON and label disagreement |
| Original prompt, 4,096 output tokens, old 60s deadline | 2 | First completed with nonconforming formatting; second hit client timeout; stopped rather than overlapping an uncertain request |
| Same prompt, optional JSON schema, 4,096 tokens, approved 180s | 4 | All four strict-schema valid; all four phase/next-action expectations matched; two full-label matches |

Total dispatched across the preserved ledgers: **12**. The request allowance is consumed; further live inference needs the requested expanded budget. No public calls, installations, serving changes or reasoning-setting overrides occurred.

The structured condition deliberately reused the **first four previously failing cases**. It is a targeted diagnostic, not held-out accuracy or a fair latency comparison. Generation settings were not seeded, and this condition changes both timeout and output constraints relative to the initial baseline. No original score or fixture label was changed.

## Structured-condition measured outcomes

| Case | Seconds | Strict JSON | Phase and next action | All expected labels |
|---|---:|---|---|---|
| Negated success | 35.41 | pass | match | fail: progress advancing vs expected blocked |
| Changed plan | 66.36 | pass | match | match |
| Injection in tool result | 23.20 | pass | match | fail: progress advancing vs expected blocked |
| Format after verification | 20.25 | pass | match | match |

Mean observed elapsed time: **36.30 seconds**. The changed-plan case exceeded the previous 60-second client deadline and finished within the new one. Time includes any queuing; no claim of isolated generation latency or production readiness coverage is made. Returned reasoning text was omitted from saved evidence; reported usage remains available with reasoning inclusion unverified.

## Meaning for implementation

- Use explicit opt-in `response_format: json_schema` alongside strict local response validation. The endpoint advertises this field, and all four sampled outputs satisfied the local schema. Do not infer universal enforcement, correctness of evidence references, or semantic truth from syntactic conformance.
- Default benchmark output allowance is now **4,096 tokens**. No model/harness reasoning control changed. Expected answers remain excluded from both messages and schema.
- A failed test does not by itself distinguish *blocked* from *advancing while diagnosing*. Preserve current scores; define an independently reviewed rubric before using this field to qualify models or tune on new held-out cases. Until then it must not authorize downshift.
- Async interpretation may finish later. Keep baseline/pin until a fresh, exactly scoped validated result is available; never stall the routing lane for these measured durations.
- This demonstrates a useful semantic signal under a better specified output contract, not M3 completion, quality preservation on full tasks, or dollar savings.

## Artifacts and TDD

- `m3-reference-gx10-first.json`, `m3-reference-gx10-4096.json`, `m3-reference-gx10-structured.json`: actual preserved records, request hashes, elapsed times, finish reasons and strict evaluations.
- `bench/trajectory_reference.py`: default4096 and optional structured request generation; response scoring unchanged.
- Observed RED when test expected4096 but implementation supplied1024; GREEN after changing default.
- Observed RED for unsupported `structured=True`; GREEN after adding schema construction. All **13** focused tests pass.
- Independent reviewer `m3-selector-reference-review.json` approved the exact reference-helper/test hashes and confirmed no expected-label leak or reasoning/scoring change.
