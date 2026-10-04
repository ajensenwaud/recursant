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

## 6. Why the cheap model takes more steps (follow-up, zero spend)

Scratch `~/.hermes/cache/scratch/step_tax.py` on the G-mix sonnet and mix arms, paired by
task and repeat (32 pairs): sonnet 105 steps, mix 157.

- The luna steps themselves cost almost nothing: US$0.000-0.011 per job, 54% of the mix
  arm's calls. Every job where the mix arm was dearer than Sonnet-only was dearer because
  **Sonnet came back for more steps**, not because luna was expensive.
- luna's tool results fail 12% of the time (8 of 64) against 0 of 55 for Sonnet in the same
  arm; each failure escalates the next step to Sonnet, as designed, and Sonnet's repair is a
  fresh (uncached, long-output) call.
- luna replies with text-only turns and re-reads more often; it finishes in smaller pieces.
- The 3-result failure window held 7 steps on Sonnet after Sonnet had already repaired
  cleanly: US$0.068 of the mix arm's US$1.273 (5%), luna would have cost US$0.018. Small,
  and the window is a safety rule (one failure, one repair, one check) worth keeping.

So the step tax is a property of the cheap model (more failures, smaller pieces), and the
router already does the right thing with it (escalate on failure). Not a routing bug to fix.

## 7. Subagents on the cheap model: H-sub (US$3.46)

Pack `bench/multiagent`, the three plain delegate tasks (parent delegates three independent
modules to subagents, then integrates and tests), 2 repeats, Sonnet 5.5 at effort low with the
cache breakpoint, Hermes fb67154, sessions from the request stream, no plugin. Driver
`bench/evaluation/sub_agent.py`. Quality bar frozen before the run: no worse iff passes are
at least the Sonnet arm's minus one.

| Arm | Jobs | Hidden tests | US$ (5 matched jobs) | Model calls | On luna | Subagents recognised |
|---|---|---|---|---|---|---|
| sonnet (every session on Sonnet) | 5/5 | 65/65 | 1.181 | 51 | 0 | 15 of 15 |
| mix (routine steps on luna) | 5/5 | 65/65 | 1.005 (-15%) | 71 | 38 | 15 of 15 |
| **sub** (mix + subagents start on luna) | **5/5** | 65/65 | **0.717 (-39%)** | 99 | 63 | 15 of 15 |

The sonnet arm's sixth job never ran: the arm's equal share of the cap (US$1.40) was exhausted
after five jobs, and the meter refused the dispatch. Over all six, mix and sub passed 6/6.

- Every subagent was recognised from the request stream alone (the child's first user message
  equals the parent's `delegate_task` goal). No harness integration.
- Putting the whole first turn of a subagent on luna more than doubles the saving of plain
  routine-step routing on these tasks (-39% vs -15%) at the same quality. A subagent's first
  turn is where it reads the goal and writes its module: the step the parent-only signals
  would have kept on Sonnet.
- Limits: 3 synthetic tasks, small independent modules, 5 matched jobs, one harness. The
  earlier gpt-4.1 run on this pack passed 1-5 of 10; on current models every arm passes, so
  this is the first time the quality comparison is meaningful.

Shipped: `delegated_start` added to the economy candidate's `qualified_tasks` and
`sessions: "request"` in both shipped configs (a passing run; Anders may veto).

## 8. Shipped (this commit)

- `config/recursant.quickstart.json` and `config/recursant.agent.example.json`: current models
  (Claude Sonnet 5.5 baseline, gpt-6-luna economy, Claude Opus 5.5 recovery), list prices,
  `context.reasoning: "steps"` with low/low for the Claude candidates, luna qualified for
  routine steps and single questions. The GPU-first example keeps GLM for routine steps.
- `context.phase` (off by default; measured no saving).
- Drivers: `bench/evaluation/mix_agent.py`, `effort_report.py`.
- `context.tool_report` (off by default): which offered tools the agents actually call,
  one log line per 50 tooled requests. Names only. In the 32 G-mix jobs the harness
  offered 25 tools and called 5.
