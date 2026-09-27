# Holdout v1 runner accounting note

The live dispatch ledger at `.hermes/runtime/m3-live/holdout-v1.json` records actual returned assistant content, finish reason, usage, elapsed time, and dispatch status separately. Its inline `evaluation` field incorrectly passes the content string to `score_response`, which expects a response object. Those interim schema/label totals are therefore invalid runner output, not model failures.

After dispatch completes, score an explicitly labelled projection of the recorded content, finish reason, and usage into the evaluator's input schema; retain the original ledger unchanged. No additional inference or altered labels are needed. Do not mistake that projection for an original complete raw wire response; reasoning text was not retained.
