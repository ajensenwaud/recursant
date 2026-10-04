# Token levers: where the money goes and what the router can do about it (2026-10-04)

Anders: review the codebase for further levers to reduce the customer's token spend; the ML
classifiers did not pay, and the router is "a mechanistic classifier, not agent-aware". This note
measures where the tokens go in recorded agent traffic, ranks the levers, and reports the live
test of the biggest unexploited one. Paid: US$4.92 (G-mix).

## 1. Where the money goes

100 recorded agent jobs from 2026-10-04 (Claude Sonnet 5.5 through Recursant, Hermes fb67154;
`fa-main` short pack, `fa-lh` long-horizon) plus the older gpt-4.1 runs (`final-e2`).
Script: `~/.hermes/cache/scratch/token_anatomy.py`, `dollar_split.py` (list prices).

Request bytes, mean per request (long-horizon / short / gpt-4.1):

| Part | Long-horizon | Short | gpt-4.1 runs |
|---|---|---|---|
| Tool schemas (25 tools) | 66% | 81% | 71% |
| System prompt | 9% | 9% | 15% |
| Tool-call arguments in history | 12% | 6% | 9% |
| Tool results in history | 11% (9% older than the newest turn) | 2% | 3% |
| User task | 1.5% | 1.5% | 1.3% |

Dollars (long-horizon, list prices): uncached input 26%, cached input 16%, visible output 33%,
hidden reasoning 24%. Of the 25 tools offered, 4-5 were ever called. write_file arguments are 57%
of all tool-call bytes in history (the agent's code, billed as output at the highest rate).

The number of steps is the multiplier: on the same six long tasks, Sonnet at xhigh effort made
89 tool calls, at low effort 18, with the same pass rate. Every step re-reads the whole context.

## 2. Levers, ranked by measured potential

| Lever | Measured | Who pulls it |
|---|---|---|
| Cheap current model for routine steps (signals + gpt-6-luna) | **-29% at equal quality, live** (section 3) | router; shipped config |
| Prompt caching for Claude (OpenRouter cache breakpoint, 0a141eb) | long-horizon jobs would cost 2.4x without it; 81-97% of input cached | router (Hermes custom-provider sends no markers) |
| Reasoning effort low on Claude (`context.reasoning: "steps"`) | -12-24% of cost, 5x fewer steps than xhigh, same passes on 32 jobs | router; shipped config |
| Tool schemas | 66-81% of bytes; after caching about 15% of a routine step plus the first-step cache write | harness setting; the router can only report it |
| Old tool results in history | about 2% of cost once cached | not worth building |
| Failed and repeated steps | 0-10% of tool calls failed; repeats rare | little to recover |
| Phase rule (keep the frontier for the step after a read) | **no saving, live** (section 3) | dropped |

## 3. Live test: G-mix (32 jobs, US$4.92)

Three arms through the same router (0a141eb + the phase rule), Claude Sonnet 5.5 at effort low
on every step with the cache breakpoint, Hermes fb67154, short pack (10 tasks x 2) and
long-horizon pack (6 tasks x 2). Quality bar fixed before the run: an arm is no worse if it
passes at least the Sonnet arm's count minus one.

- **sonnet**: Sonnet only.
- **mix**: Sonnet plus openai/gpt-6-luna (US$0.1/0.5 per Mtok, 20x cheaper) qualified for
  `tool_followup_ok` and `final_answer`: the signals as shipped since September.
- **phase**: mix plus `context.phase: "on"`.

| Arm | Jobs passed | Hidden tests | US$ | Model calls | Calls on luna |
|---|---|---|---|---|---|
| sonnet | 27/32 | 153/162 | 1.800 | 105 | 0 |
| **mix** | **28/32** | 154/162 | **1.273 (-29%)** | 157 | 85 |
| phase | 27/32 | 155/162 | 1.781 (-1%) | 147 | 62 |

By pack: short, mix US$0.406 vs sonnet US$0.739 (-45%), 18/20 each; long-horizon, mix
US$0.868 vs US$1.061 (-18%), 10/12 vs 9/12. Pass differences are one job either way (ledger-feature,
shop-bugfix, roman), noise at this size.

Reading it:

- The 20x price gap is the lever. 54% of the mix arm's calls went to luna and it was no worse.
  The replay estimate before the run was -29% to -44%; live came in at -29% overall because
  **the cheap model takes more steps** (157 calls vs 105), and each step re-reads the context.
  That is the first measured cost of a cheap model inside an agent loop: not wrong answers, more
  of them.
- The phase rule saved nothing. Keeping Sonnet for the step after a read moved 23 steps back to
  Sonnet and the agent then took as many steps as before. The offline check (section 4) had
  already shown the labels could not support it; the live run confirms. Left in the code, off,
  as a documented negative.
- Caching held across model switches: Sonnet's prefix stayed warm while luna served steps in
  between (cached share 82-95% in every arm).

## 4. Offline check of the phase idea (zero spend)

`bench/efficiency/phase.py` on the 1,701 recorded counterfactual pairs (the cheap model's next
move vs gpt-4.1's on the same step): agreement is highest after a failure (83%, both rerun the
command) and lowest while exploring (55%, they pick different files). That label measures how
predictable the next move is, not whether the cheap model is adequate, so it cannot validate a
phase rule. Only matched job outcomes can, which is why the rule went into the live run.

## 5. On "agent-aware"

Fair. The signals read one fact: did the last tool result fail. The stream also carries the
phase (what tool was just used), whether this is a subagent, whether the agent is looping, and
what the step will produce. We tested the phase part today and it did not pay. What did pay, both
times it was measured (September on gpt-4.1/mini, today on Sonnet/luna), is the plain rule
"after a clean tool result, a cheap model can take the next step", plus caching and effort.
The remaining agent-aware candidates with evidence behind them: subagent sessions to the cheap
model (class exists, never configured), and telling the operator which tools are never used.

## 6. Shipped (this commit)

- `config/recursant.quickstart.json` and `config/recursant.agent.example.json`: current models
  (Claude Sonnet 5.5 baseline, gpt-6-luna economy, Claude Opus 5.5 recovery), list prices,
  `context.reasoning: "steps"` with low/low for the Claude candidates, luna qualified for
  routine steps and single questions. The GPU-first example keeps GLM for routine steps.
- `context.phase` (off by default; measured no saving).
- Drivers: `bench/evaluation/mix_agent.py`, `effort_report.py`.
