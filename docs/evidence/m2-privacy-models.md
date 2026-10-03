# Privacy models on gx11: names and addresses (2026-10-03)

Phase 1 of `docs/proposals/ml-guided-routing.md`. Four open models run on gx11 CPU in a
container capped at 3 GB / 8 cores (GLM leaves about 4 GB free), over the same 2,142-item
test set as `docs/evidence/m2-au-identifiers.md`. GLM stayed up throughout.
Runner: `bench/privacy/predict.py`, `bench/privacy/Dockerfile`; predictions in
`.hermes/runtime/privacy/preds/` (not committed).

| Detector | Recall | Names/addresses/DOB only | False alarms: real agent text | Decoys | Names | Addresses | CPU time per 1,000 chars |
|---|---|---|---|---|---|---|---|
| Today (email rule) | 22% | 0% | 0% | 0% | 0% | 0% | - |
| Rules (`compliance.identifiers`) | 86% | 25% | 0% | 0% | 0% | 0% | microseconds |
| Presidio + rules | 97% | 86% | **16%** | 6% | 94% | 0% | 24 ms |
| bert-base-NER + rules | 95% | 75% | 1.4% | 4% | **99%** | 0% | 600 ms |
| Piiranha + rules | 97% | 85% | **0.8%** | 8% | 71% | **100%** | 1,450 ms |
| GLiNER-PII + rules | 95% | 75% | 3.5% | 7% | 66% | 100% | 2,200 ms |

Reading the false alarms on real agent text by hand: they are real errors, not hidden
personal data (one exception: "Alice" in a table an agent made up). Piiranha reads file
paths (`/workspace/auditkit/...`) as street addresses and UUIDs as account numbers;
bert-base-NER reads words in source code as names; Presidio flags many code identifiers.

## Conclusions

Correction (2026-10-03, `m2-privacy-pipeline.md`): the CPU times above are most likely
inflated. Under `--cpus=8` torch starts 20 threads (one per host core); with 8 threads Piiranha
takes 638 ms and bert-base-NER 355 ms per 1,000 chars. The follow-up gates the model to about
5% of agent text.

1. Rules plus one model reach about 95 to 97% recall. The model's job is names and street
   addresses; the rules already handle identifiers with check digits.
2. Presidio is fast but raises too many false alarms on agent work (each one moves a
   conversation to the slower private model for good).
3. The accurate models are too slow on CPU for every agent step: a typical new tool
   result is 2,000 to 4,000 characters, so 1 to 6 seconds of checking per step.
4. Next: (a) cheap post-filters for the known false alarms (a path is not an address, a
   UUID is not an account number, code identifiers are not names); (b) measure the same
   models quantised (int8, ONNX) on CPU and on a small share of the GB10 GPU; (c) check only
   new text in each request and remember the result per conversation.
