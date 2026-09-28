# Compliance content-scanning switch (temporary)

`compliance.content_scanning` (boolean, default `true`). Setting it to `false` is a
**temporary operator switch** requested by Anders on 2026-09-29. The regex/text
heuristics (PII patterns, URL and `data:` markers, nested-JSON text) are too strict for
agent traffic: harness system prompts routinely contain URLs. A judgement model
(e.g. Jev) is meant to replace them later; the switch itself should not simply be
removed.

With the switch off:
- Regex patterns and text heuristics are skipped.
- Structural uninspectability still forces private placement: unknown request or
  message fields, non-text content parts such as images/files, and unknown provider
  controls.
- `public_allowed: false` still forces private placement.
- Provider-adapter decoration and the final exact-payload re-check still run.
- Startup logs `compliance_content_scanning=disabled WARNING ...`, and each decision
  logs `compliance_reason=unscanned`, so evidence never reports these requests as `clean`.

**It removes PII protection.** Use it only with synthetic or public data (the M3
benchmark), never with real customer data.

Tests: `tests/integration/test_compliance.py` `test_content_scanning_switch` and
`test_content_scanning_switch_is_strict_boolean`.
