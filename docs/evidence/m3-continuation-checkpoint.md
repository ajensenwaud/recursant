# M3 continuation checkpoint

## Verified integrated code

Main includes reviewed gateway wiring and continuity/shadow fixes through `8e6e076`, in addition to the reviewed selector, ingress-owned attempt ledger and asynchronous private interpreter. Parent rebuilt the combined checkout and ran **17/17 normal** and **17/17 ASan/UBSan** CTest suites, with zero failures or skips. XML: `m3-gateway-integrated-normal.xml` and `m3-gateway-integrated-sanitizer.xml`.

The gateway can ingest authenticated scoped evidence, interpret asynchronously and change actual HTTP destinations in its supported non-streaming text fixture. Final deterministic compliance still applies. Explicit scoped requests cannot bypass ownership, shadow proposals cannot veto normal dispatch, and loss of lifecycle headers for an identifiable registered workflow is rejected. These are real C gateway/loopback-provider tests, **not live-model quality or dollar-savings results**. Automatic mode remains opt-in.

## Local inference settings and observed results

Reference interpretation now uses 4,096 output tokens. The user explicitly approved 180-second inference timeouts. Slow local inference is expected; assess semantic correctness separately from availability before the next routing decision.

The separately labelled schema-controlled condition returned four valid outputs with all four phase/next-action matches. Full original-label matches remain two of four. A changed-plan case took about 66 seconds. Original fixtures, failures and scores remain preserved in `m3-reference-local-followup.md` and the three experiment JSON files. Twelve private requests were dispatched in total, including one recorded timeout; the original allowance is consumed. Further local request allowance and public spend were requested but not granted by an unanswered form.

Independent rubric work and blind adjudication agreed on all five expected fields in twelve fresh diagnostic cases. These cases have **zero model attempts** and do not constitute quality or savings evidence.

## Open engineering gaps—do not call M3 complete

- The supported Hermes HTTP bridge was implemented and its basic unit/real-C loopback tests passed, but independent review found lifecycle-header substitution, duplicate-header occurrence loss and install-failure cleanup defects. It is **not landed**; a fresh fix workstream owns these findings.
- A parent HTTP regression using known inert/null metadata from saved GLM response records found permanent pinning. The bounded compatibility fix is in a separate worktree. This shape-based fixture is not replay of an original complete wire response; saved records omit reasoning.
- The actual pinned-Hermes integration probe emits `stream=true`, tools, stream options and reasoning controls; its tool round trip adds assistant `tool_calls` and tool-result `tool_call_id`. Evidence: `m3-hermes-request-shape-with-stream.log`. Instrumentation was added to the fixture server only; upstream Hermes was unchanged. The current conservative gateway keeps these flows pinned. **Native streaming/tool-flow automatic switching is therefore not proven by the simple text fixture.**
- No matched completed-task quality comparison, useful live asynchronous-context coverage, public-to-public savings or total-task dollar savings has been demonstrated.

No serving-service changes, model downloads, installations, personal Hermes profile/model changes or public inference calls were made for this continuation. Commits are local; nothing was pushed. Remaining work is real, not a paperwork gate.
