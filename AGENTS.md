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
- Integration to agent harnesses via A2A protocol and OpenTelemetry (or equivalent) for obtaining agent decision traces
- One config file, single binary
- Easy to set up and use (sane defaults)
- C for the core routing engine and harness/agent integration for zero overhead
- Next.js for the application the application layer
- Routing observability via web sockets to the application layer
- Postgres for configuration and any persistence
- Support Docker as well as bare-metal deployment (development and testing is on a Docker container)

## Core components to build
1. Core inference router: the model router itself (across hybrid workloads)
2. Compliance engine: rules engine for things like PII classification and enforcement
3. Context engine: context layer for integrating to agents and harnesses via A2A or similar
4. Self-improvment engine (optional): SLM or Jev-like agentic layer that assesses past routing decisions and optimises the context engine

Layer 2. is fully deterministic and can override any decisions made by layer 3 or 4. We need full compliance of workloads (think APRA CPS230).

## Build sequence and scope
- M1: Core inference router including hybrid routing. Definition of done: Can route across public and private workloads
- M2: Compliance engine (supports regexes and pattern matching for now). Definition of done: Can filter out requests with PII and ship them to private inference
- M3: Context engine: Intelligent, context-aware, and semantic routing decisions through live telemetry (agent decision traces) from agents and harnesses as per the product capabilities above. Definition of done: Routes to the cheapest model per turn and saves $s compared to what the harness itself would have done without compromising quality. This also applies to when public infrastructure models are used.
- M4: To be scoped out later

## Environments
Use http://gx10:8888/v1 for local inference (it runs GLM v5.3 Flash)
Use Open Router for public inference. Key located in .env. Do not commit that file to Git.
