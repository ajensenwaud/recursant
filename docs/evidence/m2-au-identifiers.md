# Australian personal identifiers in the compliance engine (2026-10-02)

Phase 0 of `docs/proposals/ml-guided-routing.md`. Anders, 2026-10-02: identifiers, tax file
numbers, emails and Medicare numbers matter most; privacy-model outages fail private.

`compliance.identifiers` (absent = unchanged) adds deterministic recognisers. A match keeps
the request private exactly like a pattern rule:
- check digits: `au_tfn` (ATO mod 11), `au_medicare` (mod 10), `au_abn` (mod 89),
  `payment_card` (Luhn and a real card shape), each as one digit run or in its printed
  layout (TFN 3-3-3, Medicare 4-5-1, ABN 2-3-3-3, card 4-4-4-4 or 4-6-5), with no letter or
  digit on either side (`core/src/compliance/identifiers.c`);
- formats with a keyword: `au_phone`, `au_bank_account` (BSB), `passport`,
  `drivers_licence`, `date_of_birth` (extra built-in patterns).

## Offline test set (`bench/privacy`, data in `.hermes/runtime/privacy`, not committed)

2,142 items: 600 synthetic Australian personal-data texts in agent-shaped form (CSV rows,
JSON tool results, logs, chat, test fixtures), planted data from the two PII benchmark
tasks, 1,023 texts of real recorded agent traffic, and 420 decoys (hashes, UUIDs,
13-digit timestamps, 9- and 10-digit numbers that fail the checks, ports, version dates).

| Detector | Recall (any personal data) | Names/addresses/DOB only | False alarms: real agent text | False alarms: decoys |
|---|---|---|---|---|
| Today (built-in email rule) | 22.3% | 0% | 0% | 0% |
| `compliance.identifiers` (all) | 86.3% | 25% (DOB) | 0% | 0% |

The C scanner and the Python reference agree on all 2,142 items at item level: 210/210
check-digit items found, 0 false alarms on 1,486 items without personal data. Two defects
found on the way and fixed: a space-separated pair of identifiers was joined into one
number; `ls -l` columns (`1000 124 4096`) could join into a check-valid 11-digit number.

Caveat: synthetic identifiers were generated with valid check digits, so their recall is
expected; the evidence that matters is the false-alarm rate on real agent text. Names and
street addresses (no fixed format) are left to the privacy model (phase 1).

## Tests

`tests/unit/test_identifiers.c` (published examples: TFN 123 456 782, ABN 51 824 753 556),
`tests/integration/test_compliance_identifiers.py` (each kind keeps the request private;
lookalikes stay public; only configured kinds; inside a tool result's escaped JSON;
strict config).
