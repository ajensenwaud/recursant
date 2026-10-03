# Privacy pipeline: rules, address rules, a gated name model and filters (2026-10-03)

Phase 1 follow-up of `docs/proposals/ml-guided-routing.md` (option B, Anders 2026-10-03).
Offline, zero spend. Models on gx11 CPU, one container at a time, capped at 8 cores / 3 GB;
GLM stayed up throughout. Code: `bench/privacy/{addresses,filters,holdout,holdout_synth,pipeline,predict}.py`,
`bench/privacy/run_spans.sh`. Data and predictions in `.hermes/runtime/privacy` (not committed).

## What changed since `m2-privacy-models.md`

1. **Speed was most likely mismeasured.** Under `--cpus=8`, torch starts one thread per host
   core (20). With threads set to the quota: Piiranha 1,450 -> 638 ms per 1,000 chars,
   bert-base-NER 600 -> 355.
2. **int8 is not worth it on gx11.** Dynamic int8: bert-base-NER no faster (380 vs 355 ms) at
   equal accuracy; Piiranha 495 ms but name recall fell from 71% to 20%. Dropped.
3. **Addresses by rule** (`addresses.py`): a number, one to three words and a street type, or a
   word, a state and a postcode. No model needed for addresses.
4. **A gate** (`filters.gate`): the name model reads only lines with two capitalised words
   together or a capitalised word after a cue (Dear, Hi, holder, "name": ...), plus one line
   either side. About 5% of real agent text passes (4.9% of characters, 6.2% of texts).
5. **Filters** (`filters.merge`, `filters.drop`): join sub-word pieces, then drop pieces of a
   longer word ("Tu" from Tuple), camelCase identifiers ("LiamParser"; "MacDonald" kept), and
   anything with code punctuation or glued to code.

Gate, filters and address rules were designed on the original test set only.

## Held-out sets (not used for design)

- **synth-holdout** (`holdout_synth.py`): 260 items, written before the filters, with new names
  and new address shapes (unit/level, lowercase, NZ), new contexts (git authors, signatures,
  JSON records), plus 15 hard negatives (tech names, places, `Martin Fowler`).
- **holdout real**: 174 recorded conversations from runs the test set did not sample
  (final-d, pilot-1..3, jev-check, lh1b, ma1-main2, ma1-localcost): 2,316 requests, 1,278
  unique new texts. Scored per conversation: one flag keeps a conversation private.

## Results (model reading gated lines only; time is measured)

| Pipeline | Design: names | Design: FA real text | Held-out: names | Held-out: hard negatives | Held-out real: conversations wrongly private | PII conversations caught | Model time per request p50 / p99 / max |
|---|---|---|---|---|---|---|---|
| Rules + address rules (no model) | 0% | 0% | 0% | 0% | 0/158 | 15/16 | 0 |
| + Presidio, filters, gate | 93.7% | 0.1% | 94.5% | 2/15 | **1/158 (0.6%)** | 15/16 | **0 / 11 / 177 ms** |
| + bert-base-NER, filters, gate | 99.0% | 0.1% | 94.5% | 1/15 | **0/158** | 15/16 | 0 / 234 / 1,816 ms |
| + Piiranha, filters, gate | 70.3% | 0% | 74.0% | 1/15 | 0/158 | 15/16 | 0 / 401 / 2,945 ms |
| Rules + address rules, Presidio on whole text, no filters or gate (phase 1 shape) | 94.2% | 15.8% | 94.5% | 5/15 | 39/158 (24.7%) | 16/16 | 5 / 116 / 268 ms |

- The real PII conversations are caught by the email rule already (the planted rows carry
  emails), so the evidence for names comes from the synthetic sets.
- The one PII conversation not caught never contained the planted data (the agent did not
  read it), so 15 of 15 conversations that did were caught. The phase 1 shape's 16/16 counts
  a false alarm in that conversation.
- Most requests need no model call: p50 and p90 are 0 ms because nothing passes the gate.
- Address rules on held-out addresses: 64/80. All 16 misses are lowercase addresses
  ("37 wombat lane, byron bay nsw 2481").
- Date of birth on held-out: 0/40. The rule knows only dd/mm/yyyy; held-out used
  `dob=1960-11-21` and "Born on 25 March 1957". In every case the name was caught, so the
  item was flagged anyway.
- Presidio's one false conversation: "MM" in `'HH:MM' format` read as a person.

## Conclusions

1. The target (<2% of conversations wrongly private) is met on held-out conversations by the
   gated pipeline with either Presidio (0.6%) or bert-base-NER (0%), with about 94% name
   recall on new held-out examples.
2. Presidio is the practical choice: 11 ms at p99 on CPU, 20x faster than bert-base-NER at the
   tail, with the same held-out name recall. bert-base-NER is more accurate on the design set
   (99% vs 94%) and could replace it later if names are missed in practice.
3. Gate first, model second: the gate is what makes CPU models affordable per step, and it
   removes most false alarms. No GPU is needed.

## Found on held-out data, not fixed (fixing them would spend the held-out sets)

- Address rules: accept lowercase street types and states.
- Date of birth: ISO dates and long-form dates next to dob/born keywords.
- Names: an all-capitals token ("MM") is not a name.
Fix these with a fresh held-out set to confirm.

## Next (needs Anders's go-ahead, phase 4)

- Address rules in C (`compliance.identifiers` kind `au_address`), same shape as the identifier
  recognisers.
- Presidio + gate + filters as a local sidecar the router calls on new text only, with the
  result cached per conversation, off by default. Outage = private (Anders, 2026-10-02).
