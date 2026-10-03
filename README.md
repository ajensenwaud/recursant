# Recursant

**The agent-aware model router. Cheapest suitable model for every step, on-prem or public, with private data kept on your own hardware.**

Recursant sits between your AI agents and your models. It reads each request as the agent sends it, works out what kind of step it is, and sends it to the cheapest model that can do that step and is allowed to see the data. It is one small C binary with one config file, and it speaks the OpenAI API, so nothing in your agent changes.

On our live agent benchmarks it cut public token spend by **25% to 66%** with no loss of quality, and sent **no** requests containing personal data to a public provider, against 31 for the same agent calling the API directly.

```sh
curl -fsSL https://raw.githubusercontent.com/ajensenwaud/recursant/main/install.sh | bash
```

---

## The problem

**Agent bills are growing faster than anyone planned.** An agent doesn't make one model call per task. It makes dozens or hundreds: read a file, run the tests, read the error, patch, run again, hand work to a subagent. Each call resends the whole conversation, and most teams send every one of them to a frontier model. Most of those steps are routine. You are paying frontier prices to run `ls`.

**Today's routers can't see the workflow.** They classify the latest user message and pick a model for the conversation. Inside an agent's tool loop that fails one of two ways: either the router locks the model for the whole loop and saves nothing, or it switches blindly mid-task and breaks the agent's context and prompt cache. Neither knows that a step just failed, that a subagent was started, or that the agent is stuck in a loop.

**On-prem and public models live in separate worlds.** Many organisations now own GPUs and also pay for public APIs. There is no single control point that treats both as one pool and places each request by cost, capacity and permission, so teams hard-wire one or the other.

**Compliance doesn't scale to agents.** Rules such as APRA CPS 230 and CPS 234, the Privacy Act and GDPR require that personal and sensitive data stays where it is allowed to be. An agent that reads a customer file and pastes it into its next prompt has just moved that data. Nobody can review every step by hand.

## The solution

Recursant is one OpenAI-compatible endpoint in front of all your models, public and on-prem, that decides every step:

- **Which model.** Routine steps (a clean tool result, a final answer) go to an economy model; steps after repeated failures go to a stronger one; the rest stay on your baseline. Decided per step, not per conversation. Plain questions (chat, single API calls) go to the cheapest model you qualify for them.
- **Where.** On-prem and public providers sit in one pool. Requests are placed by price, measured token use, prompt-cache warmth, capacity and health.
- **Whether it's allowed.** A deterministic compliance engine checks the exact outgoing request before it leaves. Anything containing personal data goes to your private model, and the conversation stays there. Compliance overrides every other decision.
- **Without integration.** Sessions, tool loops and subagents are recognised from the request stream alone. No SDK, no plugin, no harness changes. Point the agent's base URL at Recursant and set the model to `auto`.

## Measured results

Live benchmarks: the Hermes agent on synthetic development tasks, gpt-4.1 as the baseline and gpt-4.1-mini as the economy model on OpenRouter, with hidden tests deciding pass or fail. All costs are provider-billed.

**Single-agent coding tasks** (10 tasks x 3 repeats, [evidence](docs/evidence/m3-final-comparison-d.md))

| | Jobs passed | Public spend | Change |
|---|---|---|---|
| Agent calling gpt-4.1 directly | 20/30 | US$1.80 | |
| Recursant (request signals) | 25/30 | US$1.34 | **-25%** |
| Recursant (signals + low-cost decision model) | 21/30 | US$1.06 | **-41%** |

**Multi-agent tasks with subagents and personal data** (5 tasks x 2 repeats, compliance on, an on-prem model as the private destination, [evidence](docs/evidence/m3-multiagent.md))

| | Jobs passed | Hidden tests passed | Public spend | Personal-data requests sent to a public provider |
|---|---|---|---|---|
| Agent calling gpt-4.1 directly | 2/10 | 73% | US$4.70 | 31 |
| Recursant | 5/10 | 82% | US$1.58 (**-66%**) | **0** |

**Single questions** (1,450 benchmark questions: MMLU, GSM8K, ARC, HumanEval, MBPP and others, [evidence](docs/evidence/m3-prompt-classifier.md))

| Model answering | Correct | Spend |
|---|---|---|
| gpt-4.1 | 89.8% | US$1.37 |
| gpt-4.1-mini | 88.8% | US$0.32 (**-77%**) |
| GLM-5.3-Flash on your own GPU | 90.2% | **US$0** in tokens (about 4x slower) |

A question classifier, the approach other routers use, could not tell which questions the cheaper model would get wrong (AUC 0.5, a coin flip), so Recursant sends every fresh question to the cheapest qualified model. The classifier is still there for model pairs with a real capability gap.

**What to expect.** On agent workloads where an economy model exists that can handle routine steps, expect public token spend to fall by roughly a quarter to two thirds at equal quality. Savings rise with longer tool loops, multi-agent work and on-prem capacity, which costs nothing per token. These are development benchmarks with one agent, one model pair and synthetic tasks; every number above links to its evidence, including the limits. We publish what didn't work too: a learned efficiency model that looked good offline [saved nothing live](docs/evidence/m3-efficiency-live.md) and ships switched off.

## How it works

```
 agents (any OpenAI-compatible client, model "auto")
    |
    v
+--------------------------------- recursant -----------------------------------+
|  1. Compliance   deterministic and final: identifiers with check digits      |
|                  (TFN, Medicare, ABN, cards), emails, phones, your patterns, |
|                  structural checks. Personal data -> private model, pinned.  |
|  2. Continuity   session recognised from the request stream; tool-call       |
|                  replay checked; a session that can't move safely is pinned; |
|                  switching cost includes losing a warm prompt cache.         |
|  3. Signals      the tool results in this request: clean step -> economy,    |
|                  two failures in a row -> stronger model, harness            |
|                  rejections -> neutral, orchestrator reviewing subagent      |
|                  work -> baseline.                                           |
|  4. Judge        optional low-cost decision model for steps the signals      |
|                  leave open (only when compliance already allows public).    |
|     Questions    a fresh question (chat, single call) -> the cheapest model  |
|                  qualified for questions; tool results are never read here.  |
|  5. Selection    cheapest permitted candidate: price x estimated tokens,     |
|                  cached-token discounts, capacity, health, budgets.          |
+-------------------------------------------------------------------------------+
    |                                   |
    v                                   v
 on-prem models (vLLM, Ollama, ...)   public providers (OpenRouter, OpenAI-compatible)
```

Each layer can only narrow what the next one may do. Compliance always wins; continuity beats cost; optional advisers only fill gaps.

Also built in, each off until you switch it on:

- **Budgets.** Per-session spend caps that move work to cheaper models before refusing anything.
- **Health and failover.** Cooldowns for failing providers, and failover before the first byte reaches the client.
- **Context-window fit.** A larger model instead of an error when a conversation outgrows the cheap one.
- **Reasoning effort.** Low effort on routine steps and high on recovery, set in each provider's own field.
- **Housekeeping.** Session titles and compaction summaries go to a cheap model of your choice.
- **Shadow dispatch.** Sends a sample of steps to a second model so you can collect your own evaluation data.
- **Decision headers.** Every response says which model served it and why: `X-Recursant-Model`, `X-Recursant-Decision`, `X-Recursant-Cost-USD`, `X-Recursant-Decision-Id`.

Details: [request sessions and routing](docs/m3-request-sessions.md), [architecture](AGENTS.md).

## Get started

**1. Install** (Linux or macOS). This builds from source, installing the compiler and libraries with your package manager if they're missing, then writes a starter config:

```sh
curl -fsSL https://raw.githubusercontent.com/ajensenwaud/recursant/main/install.sh | bash
```

Options: `RECURSANT_PREFIX` (default `~/.local`), `RECURSANT_REF` (branch or tag), `RECURSANT_NO_DEPS=1` (print the package command instead of running it). Read [the script](install.sh) first if you prefer; it is short.

**2. Set your keys.** Secrets are environment references only and never go in the config file.

```sh
export OPENROUTER_API_KEY=...                      # public models
export RECURSANT_API_KEY=$(openssl rand -hex 24)    # what your agents use to call Recursant
export RECURSANT_SOURCE_KEY=$(openssl rand -hex 24) # optional harness hints (must differ from the API key)
```

**3. Point `local` at your on-prem model** in `~/.config/recursant/config.json` (the default is Ollama on `127.0.0.1:11434`), then run:

```sh
recursant validate ~/.config/recursant/config.json
recursant serve ~/.config/recursant/config.json
```

**4. Point your agent at it.** Use base URL `http://127.0.0.1:8080/v1`, API key `$RECURSANT_API_KEY` and model `auto`:

```sh
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $RECURSANT_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"auto","max_tokens":256,"messages":[{"role":"user","content":"Say hello"}]}' \
  -D - -o /dev/null | grep -i '^x-recursant'
```

It is tested end to end with the Hermes agent; any client that speaks the OpenAI chat-completions API can point at it the same way. Named aliases (`baseline`, `economy`, `strong`, `local`) are still there when you want to choose a model yourself.

**Docker.**

```sh
docker build -f deploy/Dockerfile.dev -t recursant-v4-dev:local deploy   # build image
docker build -f deploy/Dockerfile -t recursant:local .                    # runtime image, no compiler
docker run --rm --user "$(id -u):$(id -g)" --read-only --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8080:8080 -v "$HOME/.config/recursant/config.json:/etc/recursant/config.json:ro" \
  -e RECURSANT_API_KEY -e OPENROUTER_API_KEY -e RECURSANT_SOURCE_KEY recursant:local
```

## One config file

Everything lives in one strict JSON file. Unknown keys are rejected, and `recursant validate` checks it before you deploy.

| Section | What it controls |
|---|---|
| `providers` | Your model endpoints, each `private` or `public`, with an adapter (`openai-compatible`, `openrouter`) |
| `aliases` | Names your agents can use (`baseline`, `economy`, `strong`, `local`) |
| `compliance` | Identifier recognisers, your own patterns, agent text mode, whether public placement is allowed at all |
| `context` | Routing: candidates with prices and qualifications, signals, sessions, budgets, health, judge, headers |
| `limits` | Body size, connections, timeouts |

Starter: [config/recursant.quickstart.json](config/recursant.quickstart.json). Every option: [config/recursant.agent.example.json](config/recursant.agent.example.json).

## Design principles

- **Fast.** Written in C on libmicrohttpd, libcurl, Jansson and PCRE2. There's no runtime, no garbage collector and no extra network hop on the hot path. Responses stream straight through; routing decisions are local arithmetic over the request you already sent.
- **Efficient.** The default decision-maker is the request itself: tool results, failures and turn structure. No second model call, no telemetry pipeline, no waiting.
- **Self-contained.** One binary of about 240 KB with no database, no sidecar and no phone-home. It runs on a laptop, a GPU box or in a container.
- **One config file.** Strict JSON with secrets by reference. If it validates, it runs. If it doesn't, Recursant refuses to start rather than guess.
- **Unix philosophy.** It does one thing, routing model calls, and does it well. It speaks the protocol everything already speaks, writes one plain log line per decision to stderr, and composes with your proxy, secret manager and observability tools.
- **Safe by default.** Compliance is deterministic and final, a private failure never falls back to public, and every optional feature is off until you switch it on.
- **Evidence over claims.** Every feature is built test-first (normal and AddressSanitizer/UBSan builds) and every saving is measured live, with the losses published next to the wins.

## Security model

- Credentials are environment references, never config values. Logs carry fixed decision categories, never payloads, matches or keys.
- The compliance gate scans decoded strings, object keys, nested JSON and scalars of the exact outgoing request, after every other layer has acted. Matches, uninspectable content and exhausted scan budgets stay private. Invalid policy prevents startup; policy is immutable until restart.
- TLS verification on, no redirects, no automatic retries after an uncertain dispatch, bounded body size, concurrency, deadlines and streaming queue.
- Recursant listens on plain HTTP; keep it on loopback or put authenticated TLS in front of it. `--test-mode` (plain HTTP to providers) is for tests only.
- Regex and identifier rules are a request-egress boundary, not universal PII detection, output DLP or a certification.

## Status

| Milestone | State |
|---|---|
| M1 Hybrid router: on-prem and public behind one endpoint | Done, live-tested |
| M2 Compliance engine: deterministic rules, personal data stays private | Done; Australian identifiers with check digits added |
| M3 Context engine: per-step, agent-aware routing | Done; 25-66% lower spend at equal quality on our benchmarks |
| Privacy model for names and addresses | Evaluated offline: 0.6% of held-out agent conversations wrongly kept private, 11 ms p99 ([evidence](docs/evidence/m2-privacy-pipeline.md)); not yet in the router |
| Management console, Postgres audit trail, OpenTelemetry | Planned |

## Development

```sh
docker build -f deploy/Dockerfile.dev -t recursant-v4-dev:local deploy
docker run --rm -v "$PWD:/work" -w /work recursant-v4-dev:local sh -c \
  'cmake -S . -B /tmp/b && cmake --build /tmp/b -j && cd /tmp/b && ctest --output-on-failure'
```

Add `-DRECURSANT_SANITIZERS=ON` for AddressSanitizer and UBSan. Tests use local scripted providers and make no model calls. Benchmarks are under [bench/](bench) and every result under [docs/evidence/](docs/evidence), starting with the [benchmark contract](docs/benchmark-contract.md).
