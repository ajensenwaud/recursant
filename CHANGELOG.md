# Changelog

All notable changes to Recursant are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Open-source release scaffolding: `README.md`, `LICENSE` (MIT),
  `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `AUTHOR.md`
- `scripts/install.sh`, `scripts/teardown.sh`, `scripts/check-prereqs.sh`
- `.github/` issue and PR templates, GitHub Actions CI workflow

### Changed
- `FEATURES.md` rewritten as a feature catalog (was: gap analysis vs Istio)
- Default eval judge model pinned to `anthropic/claude-sonnet-4-5`
  (instead of `openrouter/auto`) — reliable JSON output on safety prompts
- Renamed internal requirements docs: `registry/CLAUDE.md` → `registry/REQUIREMENTS.md`,
  `mesh/CLAUDE.md` → `mesh/REQUIREMENTS.md`

### Removed
- Interim planning and competitive-analysis files
  (`differentiation-questions.md`, `plan-*.md`, `recursant-vs-credoai.csv`,
  `recursant-features.csv`, `features-to-implement.md`)

### Security
- Removed hardcoded admin password fallback in test files; default is now `admin`

---

## [0.1.0] — initial OSS release

First public release. Includes:

- **Control plane**: Flask + React registry with full agent governance
  lifecycle (DRAFT → ACTIVE), security testing, LLM-as-judge evaluation,
  approval workflows, mesh policy management, tool registry, certificate
  authority, EU AI Act compliance module
- **Data plane**: Python sidecar with full interceptor pipeline
  (auth, authz, compliance, PII redaction, pre/post guardrails, audit,
  rate limiting, fault injection, resilience)
- **Observability**: Apache Kafka pipeline with five consumer services;
  topology view, trace view, guardrail effectiveness centre, tool
  observatory, security command centre, cost dashboard
- **A2A protocol** (`a2a-sdk` 1.0.x) over mTLS, JSON-RPC 2.0
- **Tool governance** with sidecar-mediated `/tools/call` and `/egress`
- **Mortgage demo**: hub-and-spoke topology with 6 agents, MCP tools,
  CrewAI compliance agent, n8n KYC workflow
- **LLM provider integrations**: Anthropic, OpenAI, Google, Moonshot, OpenRouter
- **Helm chart** with mortgage demo overlay and multi-cluster active-active HA support
- **Mutating admission webhook** for sidecar injection
- **NetworkPolicy** enforcement (Calico CNI)
- **Python SDK + CLI** (`sdk/`) for agent developers

[Unreleased]: https://github.com/ajensenwaud/recursant/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ajensenwaud/recursant/releases/tag/v0.1.0
