# Phase 5 offline check: local encoders as difficulty classifiers (2026-10-04)

Question: our word-based question classifier predicts poorly which MMLU-Pro questions need a
worked answer (AUC 0.62 5-fold, 0.64 leave-one-subject-out; docs/evidence/m3-reasoning-switch.md).
vLLM Semantic Router uses small local encoders for this. Do they do better?

## Setup

- Same 980 questions and labels as the reasoning-switch evaluation. Label 1 when GLM answers
  correctly with brief working and wrongly with the letter only (210 of 980 questions differ
  between the modes; 171 of those are this case).
- Encoders, downloaded with permission (Apache-2.0 or MIT), run on gx11 CPU (8 threads,
  PyTorch fp32, batches of 16) in the recursant-privacy-eval container, offline:
  - BAAI/bge-small-en-v1.5 (33M parameters, CLS pooling);
  - vllm-sr/Vela-1.0-Encoder-307M-Embedding (vLLM Semantic Router's own embedding model,
    mean pooling);
  - Qwen/Qwen3-Embedding-0.6B (last-token pooling).
- Head: L2 logistic regression on the normalized embedding. Out-of-fold scores, 5-fold
  (seeded) and leave-one-subject-out (the subject is never seen in training).
  Script: `bench/prompt/embed_eval.py`; policy tables: `bench/prompt/reasoning_switch.py --scores`.

## Results

| Classifier | AUC 5-fold | AUC leave-one-subject-out | CPU time per question |
|---|---|---|---|
| Router's word features (context.prompt) | 0.624 | 0.635 | 0.004 ms |
| bge-small-en-v1.5 | 0.740 | 0.719 | 62 ms |
| Vela-1.0-Encoder-307M-Embedding | 0.710 | 0.697 | 264 ms |
| Qwen3-Embedding-0.6B | 0.719 | 0.714 | 1,248 ms |

The smallest encoder is the best and by far the cheapest. Policy with bge-small, scored on
subjects it never saw in training (leave-one-subject-out):

| Policy | Accuracy | Output tokens | Mean / median latency | Answers with working |
|---|---|---|---|---|
| always letter only | 66.6% | 5 | 1.7 s / 1.5 s | 0% |
| always brief working | 80.1% | 311 | 14.5 s / 6.5 s | 100% |
| bge-small, p >= 0.05 | 80.3% | 260 | 12.4 s / 5.0 s | 79% |
| bge-small, p >= 0.10 | 79.2% | 205 | 9.9 s / 2.6 s | 56% |
| bge-small, p >= 0.20 | 75.4% | 138 | 7.0 s / 1.8 s | 34% |
| word features, p >= 0.05 | 73.4% (5-fold) | 105 | 5.8 s / 1.8 s | 33% |
| hindsight oracle | 84.1% | 64 | 4.2 s / 1.6 s | 17% |

At p >= 0.10, bge-small keeps accuracy within 0.9 points of always working, with 34% fewer
output tokens, 32% lower mean latency and a 60% lower median. At the same accuracy cost the
word features cannot do that. This is the shape of vLLM Semantic Router's result: spend
reasoning only where the classifier says it helps.

## What this does and does not show

- A small local encoder predicts "this question needs working" well enough to save a third
  of the tokens at under 1 point of accuracy, on subjects it never saw.
- "Letter only" and "brief working" are prompt styles. GLM's hidden thinking adds nothing
  over brief working (m3-reasoning-switch.md), so there is no GLM thinking switch to drive
  with it.
- In the router the score has to drive a routing action, for example:
  - cheap model vs capable model on a fresh question (`simple_prompt`);
  - reasoning effort for a public reasoning model.
  Each needs labels for that model pair. Today's current pair (for example gpt-6-luna vs a
  frontier model) has not been measured.
- Costs: 62 ms of CPU per fresh question in PyTorch. An int8 ONNX Runtime build should be
  well below that, but it is not measured yet. Never on tool-result turns.

## Proposed integration (not built yet)

- Optional build dependency: ONNX Runtime 1.23 (Ubuntu 26.04 `libonnxruntime-dev`), CMake
  option off by default, so the default binary stays self-contained.
- bge-small in ONNX (published in the model repo), with a C WordPiece tokenizer checked
  against the Hugging Face tokenizer on every evaluation question.
- The embedding feeds the existing context.prompt logistic regression as extra features, so
  the decision path, classes, qualification and tests stay the same.
- Weights are trained per model pair by bench/prompt from graded answers.
