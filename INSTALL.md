# Installation Guide

Recursant deploys to a local [Kind](https://kind.sigs.k8s.io/) Kubernetes cluster. All commands use `make` targets defined in the project Makefile.

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| [Docker](https://docs.docker.com/get-docker/) | 20.10+ |
| [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) | 0.20+ |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | 1.27+ |
| [Helm](https://helm.sh/docs/intro/install/) | 3.x |
| Python | 3.11+ |
| Node.js | 18+ |

## Environment setup

Copy the sample env file and fill in your values:

```bash
cp .env.sample .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key (if using `anthropic` provider) |
| `OPENAI_API_KEY` | OpenAI API key (if using `openai` provider) |
| `GOOGLE_API_KEY` | Google API key (if using `google` provider) |
| `MESH_API_KEY` | Shared secret for sidecar-to-registry auth (default: `mesh-dev-key`) |
| `ADMIN_USERNAME` | Registry admin username (default: `admin`) |
| `ADMIN_PASSWORD` | Registry admin password — change from default |
| `LLM_PROVIDER` | LLM backend: `anthropic`, `openai`, or `google` |
| `EVAL_JUDGE_PROVIDER` | Provider for the evaluation judge LLM |
| `TEST_AGENT_PROVIDER` | Provider for the test agent LLM |

See `.env.sample` for the full list including model overrides and evaluation settings.

## Quick start

A single command creates the cluster, builds all images, deploys everything, and runs a smoke test:

```bash
make k8s-all
```

This runs: `k8s-down` (cleanup) → `k8s-up` (cluster) → `k8s-build` (images) → `k8s-load` (into Kind) → `k8s-install` (Helm) → `k8s-smoke-test`.

## Step-by-step deployment

### 1. Create the Kind cluster

```bash
make k8s-up
```

Creates a Kind cluster named `recursant` with:
- [Calico](https://www.tigera.io/project-calico/) CNI (required for NetworkPolicy enforcement — Kind's default kindnet does not support it)
- NodePort mappings for external access

### 2. Build Docker images

```bash
make k8s-build
```

Builds all 14 images: registry API, frontend, test agent, sidecar, agents A & B, webhook, gateway, and the mortgage demo components (customer/kyc-credit/core-banking/compliance agents, mortgage frontend, stub APIs, MCP servers).

### 3. Load images into Kind

```bash
make k8s-load
```

### 4. Deploy with Helm

```bash
make k8s-install
```

Runs `helm upgrade --install` with the base values and the mortgage demo overlay. Secrets (API keys, admin password, mesh key) are injected from your `.env` file.

## Accessing services

Once deployed, services are available on these localhost ports:

| Service | URL |
|---------|-----|
| Registry Frontend | http://localhost:8030 |
| Registry API | http://localhost:8050 |
| Mortgage Demo Frontend | http://localhost:8031 |

These map through Kind's `extraPortMappings` (host port → NodePort → service).

If the ports are not reachable, you may need to open them in your firewall:

```bash
sudo iptables -I DOCKER-USER -p tcp --dport 8030 -j ACCEPT
sudo iptables -I DOCKER-USER -p tcp --dport 8050 -j ACCEPT
sudo iptables -I DOCKER-USER -p tcp --dport 8031 -j ACCEPT
```

These rules are cleared on reboot or Docker restart and must be re-added.

Alternatively, use `make k8s-port-forward` to forward the registry API (5000), frontend (3000), and mortgage frontend (3001) to localhost.

## Running tests

Run the smoke test to verify the deployment:

```bash
make k8s-smoke-test
```

Run all integration tests:

```bash
make k8s-test
```

Individual test suites:

| Target | What it tests |
|--------|--------------|
| `make k8s-test-a2a` | A2A roundtrip communication between agents |
| `make k8s-test-governance` | Tool governance enforcement |
| `make k8s-test-governance-enforcement` | Governance enforcement (from host) |
| `make k8s-test-compliance` | CrewAI compliance checks (requires LLM API key) |
| `make k8s-test-features` | K8s-specific features: audit, HA, NetworkPolicy |
| `make k8s-test-registry` | Registry E2E: evaluation + security scanning |
| `make k8s-test-lifecycle` | Registry agent lifecycle (from host) |
| `make k8s-test-llm` | LLM roundtrip tests (requires LLM API key) |
| `make k8s-test-isolation` | Agent network isolation |
| `make k8s-test-banking` | Mortgage demo banking workflow |

Tests marked "requires LLM API key" will fail without a valid key configured in `.env`.

## Useful commands

```bash
make k8s-status        # Show pod and service status
make k8s-logs          # Tail registry and webhook logs
make k8s-port-forward  # Forward registry, frontend, and mortgage ports
```

## Teardown

```bash
make k8s-down
```

Deletes the Kind cluster and all resources.

## Rebuilding a single component

To rebuild and redeploy a single image without tearing down the cluster:

```bash
# 1. Rebuild the image
docker build -t recursant-registry registry/

# 2. Load into Kind
kind load docker-image recursant-registry --name recursant

# 3. Restart the deployment
kubectl rollout restart deployment/recursant-registry -n recursant
```

Replace `recursant-registry` and the build context with the component you're updating. Image names and build contexts are listed in the Makefile's `k8s-build` target.

## Multi-cluster deployment

For cross-cluster HA testing with two Kind clusters:

```bash
make multi-cluster-up      # Create both clusters, build, deploy
make multi-cluster-test    # Run cross-cluster HA tests
make multi-cluster-status  # Show status of both clusters
make multi-cluster-down    # Tear down both clusters
```
