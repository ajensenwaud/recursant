# Reasoning effort on public reasoning models (2026-10-04)

Question: vLLM Semantic Router's one published gain is switching reasoning on or off per
request. Our local encoder predicts "this question needs working" well on GLM (AUC 0.74 on
unseen subjects, docs/evidence/m3-encoder-classifier.md). Does that carry over to the
reasoning-effort setting of current public models, and does the router need a per-question
effort switch?

## Setup

- The same 980 MMLU-Pro questions (70 per subject), brief-working prompt, temperature 0,
  max 16,384 output tokens, OpenRouter `reasoning.effort`. `bench/prompt/ask.py --effort`.
- gpt-6-luna at effort none and high; gpt-6.1-sol at low and high (sol rejects "none").
  The earlier runs without an effort setting are the provider default.
- Paid US$3.65 (docs/evidence/m3-live-budget-allocation.md, F-effort). 0 errors.
- Switch analysis: `bench/prompt/effort_switch.py` (label: high right and low wrong;
  out-of-fold scores from the router's own encoder embeddings; every policy compared with
  a random choice of the same share of questions, averaged over 200 draws).

## Results

| Model and effort | Correct | Cost for 980 | Output tokens per answer | Median / p90 wait |
|---|---|---|---|---|
| GLM-5.3 Flash, own GPU (thinking off) | 80.1% | US$0 | 311 | 6.5 s / - |
| gpt-6-luna, none | 77.1% | US$0.044 | 48 | 1.4 s / 2.1 s |
| gpt-6-luna, default | 84.6% | US$0.149 | 261 | 3.2 s / 8.0 s |
| gpt-6-luna, high | 85.4% | US$0.205 | 375 | 3.3 s / 10.2 s |
| gpt-6.1-sol, low | 88.7% | US$1.366 | 97 | 3.0 s / 6.3 s |
| gpt-6.1-sol, default | 88.3% | US$1.525 | 113 | 3.3 s / 7.0 s |
| gpt-6.1-sol, high | 88.6% | US$2.027 | 164 | 4.2 s / 14.1 s |

Paired, per question:

- gpt-6.1-sol low vs high: only high right 9, only low right 10. Noise. Effort makes no
  difference to the frontier model on these questions; low is 33% cheaper than high, 10%
  cheaper than the default, and faster.
- gpt-6-luna none vs high: only high right 112, only none right 31. A real gap of 8.3
  points, largest in engineering (+23), law (+17), physics (+14), economics (+13) and maths
  (+10); none in health and history.

## Can the encoder pick which luna questions need high effort?

Not well. AUC 0.61 (5-fold) and 0.57 on unseen subjects. On unseen subjects:

| Share sent to high effort | Encoder picks | Random picks |
|---|---|---|
| 20% | 80.0% correct, 39% of always-high cost | 78.8%, 37% |
| 30% | 81.2%, 49% | 79.6%, 45% |
| 50% | 82.9%, 65% | 81.3%, 61% |

About 1.5 points better than random at the same share, still 2.5 points below always-high,
which costs US$0.0002 per question. For the same check on GLM (letter-only vs brief
working) the encoder at 50% gives 78.7% against 73.3% for random, so the signal exists where
the gap follows the subject and the shape of the question. Luna's remaining reasoning gain
does not.

## Decision

- No per-question effort switch. On current models it does not pay: the frontier model gains
  nothing from effort, and for the cheap model the classifier is barely better than random
  while always-high costs fractions of a cent.
- What the data does support is a fixed effort per model, set by the operator:
  - gpt-6.1-sol: low (same accuracy, 10% cheaper than default, 33% cheaper than high);
  - gpt-6-luna: the default or high, never none (none loses 7.5 to 8.3 points).
  Measured on single questions only. Agent steps are not measured, and harnesses such as
  Hermes send their own `reasoning_effort`, which the router never overrides.
- The encoder stays in the router, off by default (7f60ad9).
