# Single-query and first-turn routing: prompt classifier (2026-10-03)

Question: Recursant routes agent tool loops from the request stream, but a fresh question
(chat, a single API call, an agent's opening instruction) carries no tool results to read, so
today it always goes to the baseline. LiteLLM-style and vLLM Semantic Router-style routers
classify the question instead. Does a question classifier pick the right model, and what
should the router do with single queries?

## What was built

- `context.prompt` (C, `core/src/context/prompt.c`): logistic regression over the newest
  user message only (bag of words plus eight shape features), 4.4 us per question measured
  on the 1,450 questions below, no egress. At `p >= simple_min` the turn gets a new class,
  `simple_prompt`, served only by candidates qualified for it. Tool-result turns are never
  scored; tool-offering requests only with `agent_turns: true`. Below compliance and
  continuity like every other adviser. Spec: `docs/m3-request-sessions.md`.
- Tests: `tests/unit/test_prompt.c`, `tests/integration/test_gateway_prompt.py` (9 tests:
  chat with and without harness headers, hard question stays on the baseline, unqualified
  candidates never used, tool results never scored, final M2 wins, multi-turn chat scored per
  question, strict config). Full suite 44/44 under AddressSanitizer/UBSan.
- C and Python score identically: `bench/prompt/parity.py`, 1,460 texts including Unicode,
  long tokens and >64 KiB input, max difference 5e-13.
- Pipeline: `bench/prompt/build_single.py` (questions), `ask.py` (answers, capped spend),
  `grade.py` (multiple choice and numbers by answer line; code by running the tests in a
  network-less container), `train.py` (5-fold and leave-one-benchmark-out policy evaluation),
  `openings.py` (agent opening instructions).

## Data

1,450 questions drawn (seeded) from benchmark sets already cached on gx10: MMLU 400, GSM8K
250, ARC-Challenge 150, MBPP 150, ARC-Easy 100, HumanEval 100, HellaSwag 100, WinoGrande 100,
TruthfulQA 100. Each asked once, temperature 0, to gpt-4.1 and gpt-4.1-mini (OpenRouter,
billed) and GLM-5.3-Flash on gx10 (thinking off). The answer-format instruction is a system
message, so the classifier sees only the question as a user would type it.

Spend: gpt-4.1 US$1.373, gpt-4.1-mini US$0.320, probe US$0.001; GLM unbilled.

## Results

| Model | Correct | Cost of all 1,450 | Median latency |
|---|---|---|---|
| gpt-4.1 (baseline) | 89.8% | US$1.373 | 1.2 s |
| gpt-4.1-mini | 88.8% | US$0.320 (23%) | 1.5 s |
| GLM-5.3-Flash, own GPU | 90.2% | US$0 (unpriced GPU) | 5.5 s |

By benchmark the three are within a few points everywhere; gpt-4.1 leads on HellaSwag and
WinoGrande (+3 to +5 points), GLM leads on MBPP (+4) and TruthfulQA (+3).

The disagreements are nearly symmetric, which is why no classifier can exploit them:

| Pair | First right, second wrong | Second right, first wrong |
|---|---|---|
| mini vs gpt-4.1 | 38 | 52 |
| GLM vs gpt-4.1 | 58 | 52 |

Classifier (label: the cheaper model is right, or gpt-4.1 is wrong too):

| Economy model | AUC, 5-fold | AUC, leave-one-benchmark-out |
|---|---|---|
| gpt-4.1-mini | 0.498 | 0.493 |
| GLM-5.3-Flash | 0.452 | 0.480 |

0.5 is a coin flip. Wording does not predict which questions the cheaper model gets wrong.
At every threshold the classifier policy is within 0.2 points of "send every question to the
cheaper model", and costs more. The perfect-hindsight oracle would reach 92.4% (mini) or
93.8% (GLM), so there is headroom, but it is not visible in the question.

Agent opening instructions (266 recorded counterfactual pairs, 19 tasks): mini makes the same
first move as gpt-4.1 in 81% of them, about the same as on later steps (78%). A classifier on
the instruction reaches leave-one-task-out AUC 0.891, but almost all of it comes from three
tasks with one example each and a different prompt template (shape features alone: 0.614).
That is template leakage from one synthetic task generator, not evidence; `agent_turns`
stays off.

## Decision

- Single queries and chat: route every fresh question to the cheapest qualified model, with
  no classifier. On these benchmarks that costs 23% of gpt-4.1 with mini (-1.0 point, not
  significant: McNemar on 38 vs 52, p about 0.14) and nothing with the own GPU (+0.4 points),
  at about 4x the median latency. Configure it as a constant score:
  `"prompt": {"weights": {"bias": 5}, "vocab": {}, "simple_min": 0.5}` and qualify the
  economy and/or local candidate for `simple_prompt`.
- The trained classifier is not shipped: it adds cost and no accuracy here. The mechanism
  stays for operators whose model pair has a real capability gap (for example a small local
  model against a frontier model on hard reasoning), where wording may predict failure; the
  pipeline retrains on their own graded questions.
- First turn of agent tasks: unchanged (baseline) until a live test on tasks from more than
  one generator shows the classifier helps.

## Limits

- Benchmark questions with known answers, mostly short; real chat traffic is longer, more
  open-ended and has no single right answer. Hard reasoning (competition maths, long-context
  analysis) is not in the set, and that is where frontier models pull ahead.
- One answer per question per model at temperature 0; GLM answers came from two serving
  builds (gx10 was redeployed by another session mid-run; same weights). GLM latency mixes
  both builds and different load.
- Exact-match response caching (the other half of "their approach") was not built: across
  4,210 recorded agent requests there was 1 request without tools and 0 repeats of it, so
  there is no evidence it would pay on this traffic, and a cached answer to a request whose
  previous answer was rejected would loop the agent.
