# Phase 2: per-question reasoning switch on the local GLM (2026-10-03)

Question: vLLM Semantic Router's published result ("When to Reason", arXiv 2510.08731) is +10.2
points on MMLU-Pro with -48.5% tokens, from switching reasoning on only for questions that
need it (one model, Qwen3-30B-A3B). Does a per-question switch help our local model?

## Setup

- 980 MMLU-Pro test questions: 70 from each of the 14 subjects, seeded sample
  (`bench/prompt/build_mmlupro.py`).
- GLM-5.3-Flash (EXL3) on gx10, temperature 0, 4 concurrent requests (the server's parallel
  slots). Unbilled.
- Three modes on the same questions:
  - direct: thinking off, answer with the letter only (max 64 tokens);
  - brief: thinking off, "think briefly if you need to", visible working, then the answer
    (max 4096);
  - thinking: thinking on (hidden reasoning), same prompt as brief (max 16384; 600 s client
    timeout).
- Timeouts and errors count as wrong: the user got no answer.
- Analysis: `bench/prompt/reasoning_switch.py`. The learned switch is the router's
  context.prompt classifier (bag of words plus shape features), 5-fold and
  leave-one-subject-out.

## Results

| Mode | Accuracy | Output tokens (mean) | Latency mean / median |
|---|---|---|---|
| direct | 66.6% | 5 | 1.7 s / 1.5 s |
| brief (thinking off) | 80.1% | 311 | 14.5 s / 6.5 s |
| thinking on | 78.8% | 2,470 | 85.0 s / 20.1 s |

- Thinking on vs brief: 57 questions only thinking got right, 70 only brief got right. That
  is symmetric, so there is nothing for a switch to learn (AUC 0.52).
  - Thinking also ran away: 113 answers hit the 16k-token cap and 23 timed out.
  - Brief is at least as accurate, with 8x fewer tokens and 3x lower median latency. This
    supports keeping GLM's thinking off.
- Direct vs brief: 171 only brief got right, 39 only direct got right. This is a real,
  asymmetric gap, the same kind the paper exploits.
  - Per subject: worked answers add 24-34 points in maths, physics, chemistry, business and
    engineering, and 0-3 points in history, law, psychology and philosophy. The paper also
    found knowledge subjects don't need reasoning.
  - The perfect-hindsight switch would reach 84.1% at 64 tokens.
- The learned switch captures little of that gap: AUC 0.62 (5-fold), 0.64
  (leave-one-subject-out).

| Policy (direct vs brief) | Accuracy | Tokens | Mean latency | Worked |
|---|---|---|---|---|
| always direct | 66.6% | 5 | 1.7 s | 0% |
| always brief | 80.1% | 311 | 14.5 s | 100% |
| hindsight oracle | 84.1% | 64 | 4.2 s | 17% |
| learned switch, p >= 0.05 | 73.4% | 105 | 5.8 s | 33% |
| learned switch, p >= 0.20 | 70.3% | 66 | 4.1 s | 18% |
| by true subject (5-fold) | 79.6% | 260 | 12.4 s | 83% |

The by-subject row uses the benchmark's subject labels, which a router does not have. It
shows the upper end a domain classifier could reach.

## Decision

- Keep GLM's hidden thinking off (the current default). On these questions it costs 8x the
  tokens for no accuracy.
- No reasoning switch ships. Between thinking and brief working there is nothing to learn.
  Between direct and worked answers there is a large gap, but word features only weakly
  predict it: switching saves two thirds of the tokens at a cost of 7 points of accuracy.
- What could capture that gap is a stronger question classifier (a small local encoder,
  plan Phase 5) or a confidence cascade (answer directly first, redo with working when the
  letter's probability is low). Both are untested. The second needs logprobs from the
  serving stack.

## Limits

- One answer per question per mode at temperature 0, so some of the 57 vs 70 may be
  sampling noise.
- Multiple-choice questions only. "Direct" and "brief" are prompt styles; a router can only
  choose between them by changing the system prompt, which Recursant does not do today.
- The paper compared its router with direct vLLM modes averaging 48.3%. Our brief mode is a
  much stronger baseline than that.
