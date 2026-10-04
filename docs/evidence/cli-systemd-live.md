# Installed-service test: systemd unit + real agent workloads (2026-10-05)

Recursant installed with its own CLI on clawdy (Ubuntu 26.04, 4 cores, 7 GB) and driven by the
pinned Hermes agent (fb67154) through the installed service, not through a router the harness
starts. Driver: `.hermes/runtime/systemd-live/drive_service.py` (standard sandbox, network none,
bridge socket only; requests forwarded to `http://127.0.0.1:8080/v1` with the client key).
Results: `.hermes/runtime/systemd-live/run-{1,2}/` (ignored).

## Setup, all through the CLI

`install -m 0600 config/recursant.quickstart.json /etc/recursant/config.json`, then
`recursant configure --system --add-provider local --url http://gx10:8888/v1
--private-default local:GLM-5.3-Flash-EXL3 --alias local=local:GLM-5.3-Flash-EXL3`, keys piped to
`configure --system --set-key` (OPENROUTER_API_KEY, RECURSANT_API_KEY, RECURSANT_SOURCE_KEY),
`recursant install --system`, `recursant start`.

- Unit: DynamicUser (process user `recursant`), config as `LoadCredential`, secrets via
  `EnvironmentFile` (root 0600, read by systemd), journal identifier `recursant`.
  `systemd-analyze security`: 4.2 (OK).
- Direct probes: `local` -> GLM; `economy` -> gpt-6-luna; `economy` with a valid TFN ->
  GLM (`compliance_reason=pattern endpoint=private`).

## Workloads (model `auto`, signals routing, request-stream sessions)

| Task | Pass | Requests | Models | Public US$ |
|---|---|---|---|---|
| ledger-v1 | yes | 3 | Sonnet 1, luna 2 | 0.058 |
| intervals-v1 | yes | 3 | Sonnet 1, luna 2 | 0.056 |
| dag-v1 | yes | 2 | Sonnet 1, luna 1 | 0.059 |
| statkit-delegate (subagents) | yes | 19 | Sonnet 6, luna 13 | 0.167 |
| auditkit-pii-delegate (run 2) | yes | 24 | GLM 18, Sonnet 4, luna 2 | 0.128 |
| custkit-pii-delegate (run 2) | yes | 25 | GLM 20, Sonnet 3, luna 2 | 0.134 |

6/6 after the fix below; public spend US$0.65 including the failed first attempt (US$0.049).
Personal data: 38 of 49 requests in the two PII tasks carried it (task pack's own detector over
the recorded request bodies); all 38 were served by the private GLM, 0 public.
Router decision time (X-Recursant-Routing-Us, n=77): p50 4.2 ms, p95 11.9 ms, max 13.5 ms.

## Defect found and fixed

First run: auditkit-pii-delegate failed with HTTP 403 on its second request. Compliance
correctly made the request private, but an `auto` session can only continue on a context
candidate, and the shipped quickstart had no private one, so the router refused (fail
closed) rather than redirect. Fixes: quickstart gains a compliance-only `local` candidate
(qualified for no cost class, price 0); `recursant check` warns when context and compliance are
on but no candidate is private. Re-run: both PII tasks pass.

Not covered: concurrency/load, long-horizon pack, other public gateways in the catalogue.
