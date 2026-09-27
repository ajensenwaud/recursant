# M2 live smoke — gx10 private arm restored — 2026-09-27

## What was approved and installed
User approved: `sudo apt-get install -y libmicrohttpd-dev libcurl4-openssl-dev libjansson-dev libpcre2-dev pkg-config`
Result: libmicrohttpd-dev 1.0.1-2, libcurl4-openssl-dev 8.18.0-1ubuntu2.7, libjansson-dev, libpcre2-dev 10.46-1build1 — all set up cleanly.

## Build (dev preset)
Reconfigured; CMake now finds all four deps (microhttpd 1.0.1, curl 8.18.0, jansson 2.14, pcre2 10.46).
Targets that were previously skipped now build: `recursant` (router binary), `recursant-tracer`,
`test_admission`, integration test binaries. Build completed 100%, no warnings surfaced in tail.

## Tests
`ctest --preset dev`: **9/9 pass** (44.97s total), including the two previously-skipped suites:
- `compliance_integration` (19.33s)
- `router_integration` (23.50s)

## Live end-to-end smoke (config = example config verbatim, port 8080)
gx10 was healthy again (fresh vLLM model entry; direct probe answered in ~1s, so last session's
120s timeout was upstream serving availability, reproducibly not the router).

| Arm | Request | Routed to | Result |
|---|---|---|---|
| models | GET /v1/models | — | aliases `local`, `cloud` listed |
| private | chat via alias `local` | gx10 GLM-5.3-Flash-EXL3 | 200, content `ready`, usage 19p/56c |
| compliance/PII | chat via alias `cloud`, body contains `ACCOUNT-98765` | **rerouted private** (GLM) | 200, answered with account id quoted back |
| public | chat via alias `cloud`, clean body | OpenRouter liquid/lfm-2.5-2.6b:free | 200 in 1.07s, content `OK`, usage 12p/30c, cost 0 |

Router stdout per-request compliance log (verbatim):
```
compliance_reason=clean endpoint=private
compliance_reason=pattern endpoint=private
compliance_reason=clean endpoint=public
compliance_reason=pattern endpoint=private
```
Deterministic M2 enforcement verified against both live endpoints: pattern hits never reach the
public provider; clean requests route normally.

## Root cause of the earlier "invalid runtime configuration" mystery
The desktop session exports `RECURSANT_API_KEY` **set-but-empty**; the loader requires any declared
`api_key_env` to resolve to a non-empty value, so `validate`/`serve` failed even with both keys
present. Launch with a clean env (script sources `.env` then exports a real `RECURSANT_API_KEY`).
The example config's public+auth sections are mandatory (public.api_key_env required when the
`public` section exists; auth.api_key_env always required).

## Deploy-path note
The committed container binary links libmicrohttpd, which exists in the container image but only
now on the host too — host dev builds and Docker deploy path both work.

## Landed in this commit
- 3 test-harness robustness fixes (fd leak via `communicate()`, temp-config unlink on all paths,
  connection-reset tolerance in untrusted-TLS fixture, HTTPError context-manager form)
- this evidence file
