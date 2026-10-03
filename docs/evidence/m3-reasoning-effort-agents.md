# Reasoning effort: hard questions and agent workflows (2026-10-04)

Follow-up to docs/evidence/m3-reasoning-effort.md, which tested only two OpenAI models on
general-knowledge questions. Anders: test Claude, hard maths and science, and agent workflows.
Paid US$21.59 in total (F-hard US$9.72, F-agent US$11.87; docs/evidence/m3-live-budget-allocation.md).

## 1. Hard questions

416 questions (`bench/prompt/build_hard.py`): AIME 2024+2025 (60), MATH-500 level 4-5 with
integer answers (156), MMLU-Pro maths/physics/chemistry/engineering not used before (200).
Claude 5.5 on OpenRouter cannot switch reasoning off ("Reasoning is mandatory"), so its arms
are effort low and xhigh. GLM: thinking off and on, on a random 120 of the questions (thinking
on takes minutes per AIME problem).

| Model | Set | Less thinking | More thinking | Only more right / only less right | Cost or time |
|---|---|---|---|---|---|
| Claude Sonnet 5.5 | AIME (60) | 100% | 100% | 0 / 0 | US$0.46 vs US$0.77 |
| | MATH-500 L4-5 (156) | 100% | 100% | 0 / 0 | US$0.46 vs US$0.67 |
| | MMLU-Pro STEM (200) | 89.0% | 91.5% | 10 / 5 | US$0.72 vs US$1.16 |
| Claude Opus 5.5 | AIME + MATH (216) | 99.5% | 100% | 1 / 0 | US$2.02 vs US$2.94 |
| GLM-5.3 Flash (own GPU) | AIME (16) | 50.0% | 81.2% | 6 / 1 | median 37 s vs 147 s |
| | MATH-500 L4-5 (47) | 80.9% | 95.7% | 7 / 0 | median 17 s vs 34 s |
| | MMLU-Pro STEM (57) | 86.0% | 80.7% | 1 / 4 | median 14 s vs 37 s |

- Current Claude models solve these public maths sets almost perfectly at low effort. Some of
  this is probably contamination (AIME 2024/2025 and MATH-500 predate the models). More
  effort costs 45-58% more and adds nothing measurable. The MMLU-Pro STEM gap (10 vs 5) is
  within noise.
- GLM is the case vLLM Semantic Router describes: thinking helps a lot on free-form maths
  (+31 points on AIME, +15 on MATH) and hurts on multiple choice (-5). A rule by question type
  (think when there are no answer options) scores 89.2% on the 120, against 86.7% always on
  and 79.2% always off, with a median wait of 22 s against 40 s always on.
- The local encoder could not learn that rule from 14 examples (AUC 0.53 on unseen subjects).
  The switch exists in the data, but the training labels here are too few to learn it.

## 2. Agent workflows

Hermes fb67154, Claude Sonnet 5.5 for every step, through Recursant 0a141eb with
`context.reasoning: "steps"` (new): every step gets an effort from the router. Three arms,
identical except the router's effort table:

- **low**: every step low;
- **xhigh**: every step xhigh;
- **switch**: routine steps low (the signals saw a successful tool result, or the final answer);
  first step, steps after a failure and unclassified steps xhigh.

The router added OpenRouter's automatic prompt-cache breakpoint for Claude in every arm
(81-97% of input tokens served from cache). Limits identical in every arm: max 16,000 output
tokens per step including thinking; short pack 8 turns and 600 s; long-horizon pack 80 turns
and 1,500 s. Quality bar fixed before the run: an arm is "no worse" if it passes at least the
xhigh arm's count minus one.

| Pack | Arm | Jobs passed | Hidden tests | US$ | Reasoning tokens |
|---|---|---|---|---|---|
| Short (10 tasks x 2) | low | 18/20 | 94/100 | 0.71 | 940 |
| | switch | 18/20 | 94/100 | 1.14 | 15,579 |
| | xhigh | 19/20 | 97/100 | 2.40 | 32,462 |
| Long-horizon (6 tasks x 2) | low | 10/12 | 60/62 | 1.08 | 4,557 |
| | switch | 11/12 | 61/62 | 2.10 | 37,384 |
| | xhigh | 10/12 | 60/62 | 4.25 | 121,950 |
| **All 32 jobs** | **low** | **28/32** | | **1.79** | |
| | **switch** | **29/32** | | **3.24** | |
| | **xhigh** | **29/32** | | **6.66** | |

- Every arm meets the quality bar. The pass differences are one job either way: roman (short
  pack) passed once, only on xhigh; ledger-feature (long-horizon) passed once, only on switch.
- Low effort costs 27% of xhigh, and the router's switch 49%, for the same quality. Low is also
  the fastest: 614 s of model time over all 32 jobs, against 1,278 s for switch and 2,960 s for xhigh.
- On these tasks the per-step switch does not beat simply running low. Its extra spend is the
  xhigh first step (planning) and the steps after failures.

## What was built for this (0a141eb)

- `context.reasoning: "steps"`: effort per agent step from the signals, replacing the
  harness's effort field (the operator hands effort to the router). Off by default.
- OpenRouter adapter: automatic prompt-cache breakpoint for Anthropic models on continuing
  conversations (tools offered or history); 10x cheaper input on the next step.
- Response observer: Claude's native finish reasons and reasoning_details, so a Claude session
  is not pinned after its first reply (with `reasoning_text: "drop"`).
- Runner: Claude rates and reviewed output bound; `bench/evaluation/effort_agent.py`,
  `effort_lh.py`, `effort_report.py`; questions `bench/prompt/build_hard.py`.

## Decision and why the other routers have the switch

- The switch pays where thinking helps some kinds of question and not others, and costs a lot:
  local open models such as GLM (and vLLM-SR's Qwen3-30B) on maths. That is where vLLM-SR's
  published result comes from.
- It does not pay on current Claude models, which already decide for themselves how much to
  think: their low effort is as good as xhigh here, on hard maths and on agent jobs.
- For Claude agents, the cheapest safe setting is effort low on every step (27% of xhigh's
  cost, same results on 32 jobs). `context.reasoning: "steps"` with low/low does that whatever
  the harness sends.
- For GLM, the next step would be the question-type rule as a deterministic signal (no answer
  options and maths notation: think), tested on agent maths steps. Not built.
