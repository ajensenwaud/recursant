# Proposal: machine-learning help for routing decisions (2026-10-02)

Status: for Anders's review. Nothing here is built yet.

Update 2026-10-03: phases 0-3 done offline. Privacy: `docs/evidence/m2-au-identifiers.md`,
`m2-privacy-models.md`, `m2-privacy-pipeline.md` (gated Presidio pipeline: 0.6% of held-out
conversations wrongly private, ~94% held-out name recall, 11 ms p99). Efficiency:
`docs/evidence/m3-efficiency-model.md` (1,701 pairs, AUC 0.75 on unseen tasks). Phase 4 for the efficiency
model was built and checked live (`docs/evidence/m3-efficiency-live.md`): no saving, left off.
Phase 4 for the privacy pipeline awaits a go-ahead.

## The idea in one paragraph

Today every routing decision is made by fixed rules: pattern matching finds private data,
and simple rules read the agent's tool results to decide when a cheap model is good
enough. Rules are fast, predictable and auditable, but they miss things. Pattern matching
cannot recognise a person's name or a street address. The cheap-model rules are blunt: they
know a step went well, but not whether the *next* step is easy. This proposal adds two small
machine-learning models that help in those two places, plus a way to improve them over time
from the router's own traffic. The rules stay in charge; the models only advise, within
limits set below.

## Part 1: a privacy model (finds personal data the patterns miss)

**What it does.** Reads each new piece of text in a conversation (the user's messages and
the tool results) and flags personal data: names, addresses, phone numbers, dates of birth,
tax file and Medicare numbers, bank details, and so on.

**What it is allowed to do.** It can only make routing *stricter*. If it finds personal data,
the conversation moves to the private model (gx10) for good, exactly as a pattern match does
today. If it finds nothing, the existing patterns still apply. It can never send anything to
a public provider that the patterns would have kept private. Compliance stays deterministic
in the sense that matters: a "private" result is final and auditable (we log which kind of
data was found, never the data).

**Where it runs.** On gx10, next to GLM, as a small service the router calls. Personal data
never leaves our own hardware to be checked. Small models of this kind take roughly 10 to
50 ms per message on a GPU.

**The hard trade-off: speed versus safety when the model is slow or down.** Two choices:

| Choice | What happens if the model doesn't answer in time | Effect |
|---|---|---|
| A. Safe | Treat the message as private | Never leaks; an outage sends everything to GLM (slow, but correct) |
| B. Fast | Fall back to the patterns only | Never slows down; during an outage, names and addresses can reach public providers |

Recommendation: **A**, with one refinement. Each piece of text is checked once and the
result is remembered for the conversation, so only new text is ever waiting on the model.

**The other risk: false alarms.** Agents read a lot of source code, and code is full of
things that look like names (`class Alice`, `def parse_address`). Every false alarm sends a
conversation to the slower private model for good, which costs time and loses the savings.
So the model is judged on two numbers, not one:
- how much real personal data it catches that the patterns miss, and
- how often it wrongly flags ordinary agent work (target: under 2% of conversations).

**Candidates to test** (all free, open models; exact versions to confirm when downloading):
Microsoft Presidio (spaCy-based, widely used), GLiNER PII models (can be told which kinds
of data to look for), DeBERTa/ModernBERT models fine-tuned for PII (for example the one vLLM
Semantic Router uses), and GLM itself asked to label text, as a slower but strong
comparison.

## Part 2: an efficiency model (predicts when the cheap model is good enough)

**What it does.** For each step of an agent's work, estimates the chance that the cheap model
would do the same thing the expensive model would do. If that chance is high, use the cheap
model; if low, keep the expensive one.

**What we already know** (from our own recorded runs, `docs/evidence/`):
- The cheap model (gpt-4.1-mini) made the same move as gpt-4.1 on about 68% of steps where
  our rules sent work back to gpt-4.1, but only 36% when the step was fixing code after a
  failure. So the step type matters a lot.
- The Jev judge (a general-purpose decision model) could only weakly tell easy steps from
  hard ones (score 0.64, where 0.5 is a coin flip and 1.0 is perfect) and could not predict
  failures at all (about 0.5).
- So a general model asked general questions is not enough. A model trained on *our own*
  agents' steps is the better bet.

**What it learns from.** Pairs of "what the expensive model did" and "what the cheap model
would have done" on the same step. We have about 200 such pairs already. The shadow feature
built today (it quietly sends a sample of real steps to a second model and records both
answers) produces more of them, at a cost we control, for example 5% of steps capped at
US$3.

**What kind of model.** Start small and simple: a model over facts the router already
extracts (what the last tool returned, how many failures in a row, what kind of tool,
how long the conversation is, whether it is a sub-agent). Models like this answer in
microseconds and can be built into the router itself. Only if that is not good enough do
we try a small language model (for example a ~0.5B model fine-tuned on our pairs, running on
gx10).

**What it is allowed to do.** It sits below privacy and continuity, where the judge sits
today. It can:
- stop a downshift the rules would have made, if it predicts the cheap model will get it
  wrong (protects quality), and
- allow a downshift on steps the rules leave undecided, if it is confident (adds savings).

It can never override privacy, and never move a conversation the router has locked to a
model.

**When it is good enough to switch on.** Before any live use it must, on recorded runs it
was not trained on, score at least 0.75 (versus 0.64 for Jev), and show that it would have
saved money without making jobs fail. We then run it live alongside the current rules, in
the same way as earlier benchmark runs.

## Part 3: getting better over time (the "self-improvement" loop)

1. **Collect.** Shadow sampling and normal traffic record decisions and outcomes, with the
   decision id that links them. The data stays on our own machines.
2. **Retrain.** Offline, on gx10, on a schedule (say weekly).
3. **Check.** The new model must beat the current one on recent recorded runs it has not
   seen. If it doesn't, it isn't used.
4. **Approve.** A person approves each new model before the router loads it. No automatic
   changes to anything that affects privacy.

## Plan and costs

| Phase | What | Time | Spend | Your decision needed |
|---|---|---|---|---|
| 0 | Build test sets from our recordings: personal-data examples (from the two PII tasks plus synthetic Australian examples: TFN, Medicare, BSB, addresses) and the efficiency pairs | 1 to 2 days | none | none |
| 1 | Download 3 to 4 privacy models to gx10 and score them on catch rate, false alarms and speed | 1 to 2 days | none (local) | OK to download models and run a test service on gx10 |
| 2 | Train the simple efficiency model on existing pairs; replay on recorded runs | 2 days | none | none |
| 3 | Collect more pairs with shadow sampling | 1 week of runs | about US$3 | budget |
| 4 | Build the winners into the router (off by default), then one live comparison run | 2 to 3 days | about US$2 | go-ahead after seeing phase 1 to 3 results |

## Questions for Anders

1. Privacy model outage behaviour: choice A (safe, everything private) or B (fast,
   patterns only)? Recommendation A.
2. OK to download open models to gx10 and run a small classifier service there?
3. Which kinds of personal data matter most to the customers you have in mind (for example
   Australian identifiers under APRA CPS 230 / CPS 234)? This decides the test set.
