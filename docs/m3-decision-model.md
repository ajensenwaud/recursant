# Small decision models in the router: assessment (2026-10-05)

Anders: the router is fully mechanistic; the ONNX classifier work produced nothing; is there a
small, free, fast model (Strands Decider class) that makes the routing genuinely intelligent,
with an investor narrative behind it?

Short answer: yes, and the router already has the socket for it. What failed was *predicting
from question text which questions a cheap model gets wrong*. That signal is not in the text
(encoder AUC 0.56-0.58; `m3-encoder-classifier.md`). What a decision model is for is reading the
*agent's state* and answering closed questions about it with a calibrated confidence. One such
model (Jev, hosted) has already been measured live in the judge slot: signals -25%, signals +
decision model -41%, at the frozen quality bar (`m3-final-comparison-d.md`, 30 jobs, gpt-4.1
era). The open-source equivalent now exists, runs on our own GPU, and can be trained on our own
routing outcomes. That last part is the moat.

## 1. What a decision model is (plain terms)

An LLM writes text. A decision model cannot: its text head is removed and replaced by a tiny
"pointer head" that scores a fixed set of options you give it, in one forward pass, no
generation. It returns the choice and a calibrated confidence ("at confidence 0.9 it is right
about 95% of the time"). It is general purpose: the question and options are in the request,
not trained in. Three question types: yes/no, choose one of N, rate on a scale.

Candidates:

| | Strands Decider 2B (AWS, 1 Oct 2026) | Jev (TypeSafe, hosted) | OpenAI's announced equivalent |
|---|---|---|---|
| Weights | Apache-2.0, open, 1.9B (Qwen3.5-2B torso + LoRA r16 + 1M-param head) | closed, API only | closed, API only |
| Where it runs | our GPU (gx10), a Mac, or CPU | their cloud | their cloud |
| Latency / question | 115 ms median on an RTX 3090; many questions on one state are nearly free (state encoded once) | 292 ms median measured by us via OpenRouter | unknown |
| Cost | electricity | US$0.00004 per decision measured | unknown |
| Compliance | state never leaves the estate | public egress: only when M2 already permits public placement | same problem |
| Trainable on our data | yes: full recipe published, 11 h on one RTX 3090 | no | no |
| Accuracy | JevBench 0.723, easy tier 100%, calibration ECE 0.052 | similar class (Decider briefly topped the size board) | unknown |
| API | `POST /v1/systemone` {state, questions} | `/decisions` {state, questions} | unknown |

The router's judge (`core/src/context/judge.c`) already builds the {state, questions} request in
this format (`next_step` choice, `difficulty` score), has a circuit breaker, a timeout, and the
compliance rule that a restricted session's state never goes to a public judge. Pointing it at a
local Decider is a URL change plus a compatibility check (Strands says Jev API compatibility
"is not verified"; JevBench's typesafe adapter runs against it unmodified, so the shape matches).

## 2. What the evidence says it can and cannot do today (zero-shot)

From `m3-judge-offline.md` (751 recorded agent steps through Jev) and today's data:

| Question | Zero-shot signal | Verdict |
|---|---|---|
| What kind of step comes next (mechanical vs writes code)? | AUC 0.64 with good wording, 0.51 with bad | weak; wording matters |
| Will the cheap model's next step fail? | AUC 0.45-0.52 | none. It cannot see the future from the transcript |
| Did the last tool call actually fail? | not measured yet; in Decider's "easy" tier | the right first target (below) |
| Is this a routine step? (live, gpt-4.1 era) | signals -25% -> signals+Jev -41%, pass 25 -> 21 of 30, inside the frozen bar | real saving, with a quality wobble that needs the confidence threshold |

Why the ONNX encoder failed and this does not: the encoder embedded the *question text* and asked
"will model X get this wrong". A decision model reads the *state of the agent* (task, last tool
calls, last results) and answers questions whose answer is in that state.

## 3. Where the money is for a decision model (measured, today's runs)

1. **False failures hold steps on the frontier model.** The signals treat the words
   `error|traceback|failed|exception` in an unstructured tool result as a failure. In today's
   mix/sub arms, 27 of 57 "failed" newest results (47%) were word matches on *source code the
   agent had just read* (`raise ValueError`, `assertRaises(ValueError)`). They kept 13 steps on
   Sonnet, US$0.149 of ~US$3.3 (about 4.5% of spend). On the earlier multi-agent pack it was
   about half of 234 held steps. A yes/no question "did this tool call fail?" is exactly a
   decision model's easy tier, and the label is free (the structured results tell the truth).
2. **The 46% of calls that stay on the frontier by rule.** First step of each session, every
   step after a failure, and the three-result safety window. Some are trivial retries with
   corrected arguments. A calibrated "is this a mechanical retry?" at confidence >= 0.9 could
   move a share of them; below the threshold nothing changes. This is what produced the -41%
   on gpt-4.1. Needs re-measuring on current models with the threshold frozen in advance.
3. **Agent-state questions nobody asks today**: is the agent looping; has the subagent met its
   goal; is this the final answer; is the agent exploring, implementing or verifying. All
   closed questions over the request stream. The phase rule was tried as a fixed rule and did
   not pay; as a *learned, confidence-gated* decision it is untested.

What a decision model will not do: shrink what the harness sends (tool schemas 66-81% of
bytes), or stop the cheap model taking 50% more steps. Those stay with caching, effort and
model choice, all shipped.

## 4. The part that is actually new: training on our own outcomes

Every routed step already leaves a decision record (`route_decision`, `decision_id`, the
replayable request, the provider response, the next tool result, the job outcome). That is
labelled training data the customer generates for free:

- step served by the cheap model -> next tool result clean or failed (today: luna 12%
  failed vs Sonnet 0%);
- step held on the frontier -> what it did (a 2-line argument fix or a redesign);
- session -> job passed or not.

Strands Decider's recipe is open: build corpus, LoRA-train, calibrate, evaluate, with
preregistered predictions per run. Recursant's "self-improvement engine" (AGENTS.md component
4) becomes concrete: a nightly LoRA on the customer's own decision log, shadow-scored against
the signals, promoted only if the replay says it is better at the frozen quality bar. Nobody
in the field has that: LiteLLM routes by rules, vLLM Semantic Router by a frozen text
classifier, Strands' own `ClassifierStrategy` by an extra LLM call per invocation, and none of
them sit below a compliance engine.

Investor framing, in one line: "Deterministic compliance you can audit, free savings from the
request stream you already send, and a 2B decision model that learns your agents from their
own outcomes, on your hardware, and knows when it does not know."

Measured claims only. The honest state today: -29% to -41% is measured; "learns from
outcomes" is a design with a published recipe and our labelled data, not yet a measured gain.

## 5. Risks

- Data volume: a few thousand labelled steps (1,701 shadow pairs, 751 multi-agent steps,
  ~450 steps from today's Sonnet/luna runs). Enough for LoRA on narrow questions; not for
  "predict any failure".
- gx10 is a GB10 (aarch64, CUDA 13) and Decider's torso uses Gated DeltaNet layers that want
  `flash-linear-attention` kernels. Serving on CPU works (slower: ~1 s on long states).
  Training needs a CUDA host; whether the pinned stack runs on GB10 is unverified.
- State window 3-4k tokens: the judge already clips the state to the task plus recent tool
  activity; that stays.
- Latency: 100-300 ms per decision against the router's 1 ms. Acceptable per agent step
  (steps are 3-30 s), synchronous with the existing breaker, never on pinned or private-only
  sessions, never above compliance.
- Quality wobble seen with Jev (25 -> 21 passes). The confidence threshold is the control and
  must be fixed before any run, not tuned on it.

## 6. Plan (each step gated on the previous one)

1. **Zero-cost replay (1 day).** Serve Decider v19 locally (needs: pip install in an isolated
   venv or container on gx10 or this host, ~4.5 GB torso download; both need Anders' approval).
   Replay the ~1,500 recorded steps through the existing judge request shape with three
   questions: did the last call fail (label: structured result); is the next step mechanical
   (label: what the agent did next); is this a repeat loop (label: identical call seen). Report
   AUC and calibration against the zero-shot Jev baselines (0.64 / 0.50).

   **Result (2026-10-05, Decider v19 bf16 on gx11, 751 Hermes steps from ma2, 0 errors):**

   | Question (label) | Decider zero-shot | Notes |
   |---|---|---|
   | Last call failed (structured envelope) | AUC 0.88 all steps; 0.77 where the text marker fired | p<0.3 frees 10 of 136 false failures, 0 of 168 real lost; p<0.5 frees 91 but loses 53 real |
   | Next step routine vs code | AUC 0.47 (Jev v2 0.60 on the same steps) | never reaches P(routine) >= 0.8: selects nothing |
   | Repeat loop | AUC 0.43 | no signal; almost all p in [0.2, 0.4) |

   Latency median 22.0 s, p90 30.0 s per state (median 1,415 tokens): the replay ran on gx11's
   CPU (image `recursant-decider:cpu`), not a GPU, so this is our setup, not the model's
   published 115 ms; GPU serving is needed before any live use
   (the judge slot has ~10 ms before the harness sends its next request). Reading: zero-shot it
   reads tool outcomes well (near the 0.9 bar) and has no usable signal on the two routing
   questions; Jev is better zero-shot on "routine". Step 2 (fine-tune on our labels) is the
   actual test of the thesis; zero-shot Decider does not go in the judge slot.
2. **Fine-tune on our labels (GPU day, free).** LoRA on the recorded steps, held out by task.
   Bar, fixed in advance: "did the last call fail" AUC >= 0.9 (it is an easy question);
   "mechanical next step" >= 0.75; calibration ECE <= 0.1.
3. **Live run (~US$8-10, needs approval).** Same 32 jobs as G-mix: signals-only vs signals +
   local Decider gating (a) false failures and (b) confidence >= 0.9 routine steps. Quality bar
   as before. Ship on by default only if it passes.
4. **Productise the loop.** Decision log -> nightly LoRA -> calibrate -> shadow -> promote on
   replay. This is the demo for investors: the router's numbers improving week on week on the
   customer's own traffic, with the audit trail Strands uses for its own research.

Not recommended: more text-only classifiers (encoder, bag of words, TF-IDF) for "will the cheap
model get this wrong". Three rounds have shown the answer is not in the text.
