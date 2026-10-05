# Context
Recursant is a harness- and agent-native intelligent routing infratructure for controlling AI csot across on-premise and public model providers (e.g. OpenRouter). 

Engineers want lower AI cost, predictable bills, and practical controls. Current model routers are not aware of the workload above them, e.g., an agentic workload or a particular model harness, and therefore make decisions that break workflows. Our thesis is that making the router harness/agent-native and -aware, it can make better routing decisions. 

## Core product capabilities
1. Intelligent hybrid routing: place work on the most economical suitable, permitted destination, including the customer's own on-premise infrastrcuture
2. Speed: vLLM is slow and has many layers. This product is built for speed and low latency.
3. Built for AI engineers: It is built for fine-tuning by agents
4. Harness/agent-aware: cache-aware, per-step routing (e.g. session state, token counts, KV-cache warmth, reward prediction), dynamic selection (e.g. dynamically allocating simple steps to cheap models, complex steps to frontier models), agent-as-a-router (including using Jev or similar low-cost models that introduces self-improvement into the model)
5. Compliance: enforce identity, data, provider and location restrictions throughout execution - for instance, data with PII may never leave the estate to a public cloud provider

## Architecture direction

- AI-native interface (CLI)
- Built to be blazingly fast
- Signals-first (decided 2026-09-29; evidence `docs/evidence/m3-multiagent.md`): the default routing decisions come from the request stream the router already sees (messages, tool calls, tool results, usage). No harness integration is required to save money, and signals remain the fallback when any other context source is missing or late.
- Integration to agent harnesses via A2A protocol and OpenTelemetry (or equivalent) for agent decision traces is an advisory layer, to be proven on long-horizon workflows (plans, subagents, slow tools, context compaction). On short tasks it arrived too late to matter (Hermes sent the next request ~10 ms after a tool result), and on multi-agent tasks subagent hints added nothing over what the request stream already showed.
- One config file, single binary
- Easy to set up and use (sane defaults)
- C for the core routing engine and harness/agent integration for zero overhead
- Next.js for the application the application layer
- Routing observability via web sockets to the application layer
- Postgres for configuration and any persistence
- Support Docker as well as bare-metal deployment (development and testing is on a Docker container)
- Observability: Agent obervability traces / telemetry (chain-of-thought) are compiled and aggregated using OpenTelemetry through Grafana. 

## Core components to build
1. Core inference router: the model router itself (across hybrid workloads)
2. Compliance engine: rules engine for things like PII classification and enforcement
3. Context engine: makes the router agent/harness-aware. Layered, in precedence order below compliance:
   a. Continuity: tool-boundary replay, sticky request contract, pins, prompt-cache switching cost.
   b. Signals (default decision-maker): deterministic C rules over the request's tool results (clean steps downshift, executed failures escalate, harness rejections are neither).
   c. Judge (disabled 2026-10-05): a synchronous low-cost decision model (Jev, Strands Decider) for turns signals leave unclassified. Measured: no reliable saving over signals (docs/m3-decision-model.md). Default builds refuse `context.judge`; the code stays for research builds (`-DRECURSANT_JUDGE=ON`).
   d. Telemetry and interpretation (advisory, to be proven on long-horizon workflows): OpenTelemetry or harness adapters and async interpretation of plans, subagents, tool durations and compaction. Never overrides a–c.
4. Self-improvment engine (optional): SLM or Jev-like agentic layer that assesses past routing decisions and optimises the context engine

Layer 2. is fully deterministic and can override any decisions made by layer 3 or 4. We need full compliance of workloads (think APRA CPS230).

### Context engine deep-dive
- The context engine retrieves ths full intent and context from the agents and harnesses that use the gateway, through direct connectivity to the agent and through OTel telemetry
- The router should maintain a full picture of what the agent is doing and uses that picture to use the right model. For instance, if the agent is mid-turn/mid-workflow, we shouldn't suddenly route to a different model as that would route to a new model and impact context window and caching 
- Before building the context engine you need to research how it is actually going to work and come up with an architecture that I can review

# Recursant CLI / daemon design

## Principles
- Engineer and agent friendly CLI
- Consistent, principle of least surprise
- Design: 'recursant <command as verb> <--switches>'
- Use systemd as daemonisation facility
- Write to systemd log 

## Core commands
- `install` - install recursant as a daemon into systemd
- `uninstall` - uninstall recursant from systemd and remove it
- `start` - start the recursant daemon
- `stop` - stop the recursant daemon
- `restart` - restart the daemon, e.g. after a configuration change
- `check` - check that configuration is sane prior to restarting
- `status` - write out the status of the daemon including service endpoint, number of requests processed, etc.
- `configure` - `hermes model`-like interface to configure the core router including private inference endpoints, OpenRouter (including API keys), and other decisions currently in the configuration file. Old config files are backed up with a date.
  - Model configuration
  - Endpoint setup (add one or more public or private endpoints)
  - Pattern configuration for PII etc. beyond defaults
  - Network interface setup (localhost only, tailnet, any other endpoint, e.g. 0.0.0.0) and port

# Routing and networking requirements
- Router should support an arbitrary amount of public and private endpoints
- Public endpoints should support more than just OpenRouter, we need to expand to other public routing providers (have a look at Hermes for a full list)
- Recursant should automatically recognise Tailscale tailnets 

# Implementation plan

## Build sequence and scope
- M1: Core inference router including hybrid routing. Definition of done: Can route across public and private workloads
- M2: Compliance engine (supports regexes and pattern matching for now). Definition of done: Can filter out requests with PII and ship them to private inference
- M3: Context engine: Intelligent, context-aware per-turn routing decisions from the agent's request stream (signals-first, optional judge), with live telemetry (agent decision traces) as an advisory layer to be proven on long-horizon workflows, as per the product capabilities above. Definition of done: Routes to the cheapest model per turn and saves $s compared to what the harness itself would have done without compromising quality. This also applies to when public infrastructure models are used.
- M4: To be scoped out later

## Environments
Use http://gx10:8888/v1 for local inference (it runs GLM v5.3 Flash)
Use Open Router for public inference. Key located in .env. Do not commit that file to Git.
