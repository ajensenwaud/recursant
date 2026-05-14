.PHONY: help test test-unit test-integration test-smoke test-unit-mesh test-unit-registry test-integration-mesh test-integration-registry test-integration-k8s docker-up docker-down docker-build docker-clean docker-logs install seed-all lint db-migrate db-upgrade mortgage-up mortgage-up-fast mortgage-down mortgage-logs mortgage-ps mortgage-test k8s-up k8s-down k8s-build k8s-load k8s-install k8s-all k8s-smoke-test k8s-status k8s-logs k8s-port-forward k8s-test k8s-test-governance k8s-test-compliance k8s-test-features k8s-test-registry k8s-test-a2a k8s-test-isolation k8s-test-llm k8s-test-banking k8s-test-lifecycle k8s-test-governance-enforcement k8s-test-guardrail-integration k8s-test-openclaw openclaw-setup openclaw-gateway openclaw-smoke multi-cluster-up multi-cluster-down multi-cluster-test multi-cluster-status

help:
	@echo "Available commands:"
	@echo ""
	@echo "  Tests:"
	@echo "    make test                - Run all tests (unit + integration)"
	@echo "    make test-unit           - Run all unit tests (mesh + registry + mortgage)"
	@echo "    make test-integration    - Run all integration tests (mesh + registry + k8s)"
	@echo "    make test-unit-mesh      - Run mesh + mortgage unit tests (local)"
	@echo "    make test-unit-registry  - Run registry unit tests (in K8s pod)"
	@echo "    make test-integration-mesh     - Run mesh integration tests (local venv)"
	@echo "    make test-integration-registry - Run registry integration tests (in K8s pod)"
	@echo "    make test-integration-k8s     - Run all K8s integration tests (requires k8s-all)"
	@echo "    make test-smoke          - Run mesh smoke tests (requires docker-up)"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-up           - Start the platform (builds if needed)"
	@echo "    make docker-down         - Stop and remove all containers"
	@echo "    make docker-build        - Build/rebuild all images from scratch"
	@echo "    make docker-clean        - Stop, remove containers AND volumes (fresh DB)"
	@echo "    make docker-logs         - Tail all container logs"
	@echo ""
	@echo "  Mortgage Demo:"
	@echo "    make mortgage-up         - Build and start the mortgage demo (full governance pipeline)"
	@echo "    make mortgage-up-fast    - Build and start (skip governance — direct DB activation)"
	@echo "    make mortgage-down       - Stop the mortgage demo"
	@echo "    make mortgage-test       - Run mortgage end-to-end test (requires mortgage-up)"
	@echo "    make mortgage-logs       - Tail mortgage agent and sidecar logs"
	@echo "    make mortgage-ps         - Show mortgage container status"
	@echo ""
	@echo "  Kubernetes (kind):"
	@echo "    make k8s-all             - Full deploy: cluster + build + deploy + smoke test"
	@echo "    make k8s-up              - Create kind cluster"
	@echo "    make k8s-down            - Delete kind cluster"
	@echo "    make k8s-build           - Build all Docker images"
	@echo "    make k8s-load            - Load images into kind"
	@echo "    make k8s-install         - Helm install (with mortgage demo)"
	@echo "    make k8s-smoke-test      - Run K8s smoke tests"
	@echo "    make k8s-test            - Run ALL K8s integration tests"
	@echo "    make k8s-test-governance - Run tool governance tests (in-cluster)"
	@echo "    make k8s-test-compliance - Run CrewAI compliance tests (in-cluster, with LLM)"
	@echo "    make k8s-test-features  - Run K8s feature tests (audit, HA, NetworkPolicy)"
	@echo "    make k8s-test-registry  - Run registry E2E tests (evaluation + security scan)"
	@echo "    make k8s-test-a2a       - Run A2A roundtrip tests (in-cluster)"
	@echo "    make k8s-test-llm       - Run LLM roundtrip tests (in-cluster, needs API key)"
	@echo "    make k8s-test-isolation  - Run agent isolation tests (in-cluster)"
	@echo "    make k8s-test-banking   - Run mortgage banking tests (in-cluster)"
	@echo "    make k8s-test-lifecycle - Run registry lifecycle tests (from host)"
	@echo "    make k8s-test-governance-enforcement - Run governance enforcement tests (from host)"
	@echo "    make k8s-test-guardrail-integration - Run guardrail API integration tests (from host)"
	@echo "    make k8s-test-openclaw  - Run OpenClaw API integration tests (in-cluster)"
	@echo "    make k8s-status          - Show pods and services"
	@echo "    make k8s-logs            - Tail registry and webhook logs"
	@echo "    make k8s-port-forward    - Forward registry (5000), frontend (3000), mortgage (3001)"
	@echo ""
	@echo "  OpenClaw integration:"
	@echo "    make openclaw-setup     - Provision a local OpenClaw with the recursant plugin"
	@echo "    make openclaw-gateway   - Start the OpenClaw gateway with API keys from \$$ENV_FILE"
	@echo "    make openclaw-smoke     - End-to-end smoke test: send a chat, verify audit row"
	@echo ""
	@echo "  Multi-cluster (active-active HA):"
	@echo "    make multi-cluster-up    - Create 2 kind clusters, build, deploy to both"
	@echo "    make multi-cluster-down  - Tear down both clusters"
	@echo "    make multi-cluster-test  - Run cross-cluster HA tests"
	@echo "    make multi-cluster-status - Show status of both clusters"
	@echo ""
	@echo "  Other:"
	@echo "    make install             - Install dependencies (mesh venv + registry pip)"
	@echo "    make seed-all            - Run all seed scripts in registry container"
	@echo "    make lint                - Run linting across both projects"
	@echo "    make db-migrate msg=...  - Generate a new DB migration"
	@echo "    make db-upgrade          - Apply DB migrations"

# =============================================================================
# Tests
# =============================================================================

test: test-unit test-integration

# --- Unit tests ---

test-unit: test-unit-mesh test-unit-registry

test-unit-mesh:
	cd mesh && .venv/bin/pytest tests/unit/ -v
	mesh/.venv/bin/pytest demo/mortgage/tests/ -v --ignore=demo/mortgage/tests/test_crewai_compliance.py

test-unit-registry:
	$(eval POD := $(shell kubectl get pod -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-registry -o jsonpath='{.items[0].metadata.name}'))
	kubectl exec -n $(K8S_NAMESPACE) $(POD) -c registry -- \
	  env TEST_DATABASE_URL=postgresql://registry:registry@$(K8S_RELEASE)-db:5432/registry_test \
	  python -m pytest tests/ -v --ignore=tests/integration/

# --- Integration tests ---

test-integration: test-integration-mesh test-integration-registry test-integration-k8s

test-integration-mesh:
	cd mesh && .venv/bin/pytest tests/integration/ -v

test-integration-registry:
	$(eval POD := $(shell kubectl get pod -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-registry -o jsonpath='{.items[0].metadata.name}'))
	kubectl exec -n $(K8S_NAMESPACE) $(POD) -c registry -- \
	  env TEST_DATABASE_URL=postgresql://registry:registry@$(K8S_RELEASE)-db:5432/registry_test \
	  python -m pytest tests/integration/ -v -m integration

test-integration-k8s:
	bash k8s/scripts/run-integration-tests.sh all

# --- Smoke tests (requires Docker Compose stack running) ---

test-smoke:
	cd mesh && .venv/bin/pytest tests/smoke/ -v

# =============================================================================
# Docker
# =============================================================================

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build

docker-clean:
	docker compose down -v

docker-logs:
	docker compose logs -f

# =============================================================================
# Other
# =============================================================================

install:
	cd mesh && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

seed-all:
	docker compose exec registry python scripts/seed_admin_user.py
	docker compose exec registry python scripts/seed_security_tests.py
	docker compose exec registry python scripts/seed_evaluation_suites.py

lint:
	cd mesh && .venv/bin/python -m py_compile runtime/sidecar/config.py && \
	  .venv/bin/python -m py_compile runtime/sidecar/agent_card.py && \
	  .venv/bin/python -m py_compile runtime/common/models.py

db-migrate:
	docker compose exec registry flask db migrate -m "$(msg)"

db-upgrade:
	docker compose exec registry flask db upgrade

# =============================================================================
# Mortgage Demo
# =============================================================================

## Mortgage demo runs on kind. Every `mortgage-up` fully tears down the cluster
## so the registry DB starts empty — the post-install mortgage-seed job is then
## the only thing that registers agents, giving a clean mortgage-only state.
##
## Implementation notes:
##   - Cold image pulls (postgres/kafka/weaviate) frequently exceed helm's
##     900s --wait, so the first install is allowed to fail (-helm). After
##     all pods are Ready we issue a second helm upgrade --reuse-values to
##     re-trigger the post-install hooks (mortgage-seed + mortgage-pipeline).
##   - The sidecar-injection webhook can race with the first batch of pods,
##     so we restart every mortgage agent deployment after the hooks run to
##     guarantee sidecars are present and the mesh registers all agents.
## Mortgage demo helm flags. .env feeds in API keys / admin creds and
## (optionally) MORTGAGE_LLM_PROVIDER / MORTGAGE_LLM_MODEL overrides. The
## demo's LLM_MODEL must be vision-capable; LLM_MODEL from .env (used by the
## eval framework) is intentionally NOT propagated to avoid e.g.
## `openrouter/auto` accidentally selecting a text-only model.
HELM_MORTGAGE_FLAGS = -f $(K8S_CHART)/values-mortgage.yaml \
	$(if $(ADMIN_PASSWORD),--set secrets.adminPassword=$(ADMIN_PASSWORD)) \
	$(if $(ADMIN_USERNAME),--set secrets.adminUsername=$(ADMIN_USERNAME)) \
	$(if $(JWT_SECRET_KEY),--set secrets.jwtSecretKey=$(JWT_SECRET_KEY)) \
	$(if $(SECRET_KEY),--set secrets.secretKey=$(SECRET_KEY)) \
	$(if $(MESH_API_KEY),--set secrets.meshApiKey=$(MESH_API_KEY)) \
	$(if $(ANTHROPIC_API_KEY),--set secrets.anthropicApiKey=$(ANTHROPIC_API_KEY)) \
	$(if $(OPENAI_API_KEY),--set secrets.openaiApiKey=$(OPENAI_API_KEY)) \
	$(if $(GOOGLE_API_KEY),--set secrets.googleApiKey=$(GOOGLE_API_KEY)) \
	$(if $(OPENROUTER_API_KEY),--set secrets.openrouterApiKey=$(OPENROUTER_API_KEY)) \
	$(if $(MORTGAGE_LLM_PROVIDER),--set mortgage.llmProvider=$(MORTGAGE_LLM_PROVIDER)) \
	$(if $(MORTGAGE_LLM_MODEL),--set mortgage.llmModel=$(MORTGAGE_LLM_MODEL))

mortgage-up: k8s-down k8s-up k8s-build k8s-load
	@echo ""
	@echo "Installing mortgage demo chart (clean DB, mortgage agents only)..."
	$(eval include .env)
	-helm upgrade --install $(K8S_RELEASE) $(K8S_CHART) $(HELM_MORTGAGE_FLAGS) \
		--namespace $(K8S_NAMESPACE) --create-namespace \
		--wait --timeout 1800s
	@echo ""
	@echo "Waiting for all pods to reach Ready state..."
	@kubectl wait --for=condition=Ready pods --field-selector=status.phase=Running --all -n $(K8S_NAMESPACE) --timeout=900s 2>/dev/null || true
	@echo ""
	@echo "Re-running helm upgrade to ensure post-install hooks executed..."
	helm upgrade --install $(K8S_RELEASE) $(K8S_CHART) $(HELM_MORTGAGE_FLAGS) \
		--namespace $(K8S_NAMESPACE) --reuse-values \
		--wait --timeout 1200s
	@echo ""
	@echo "Restarting mortgage agent pods to guarantee sidecar injection..."
	@for app in agents-customer agents-kyc-credit agents-core-banking agents-compliance n8n-kyc; do \
		kubectl rollout restart -n $(K8S_NAMESPACE) deployment/$(K8S_RELEASE)-$$app 2>/dev/null || true; \
	done
	@for app in agents-customer agents-kyc-credit agents-core-banking agents-compliance n8n-kyc; do \
		kubectl rollout status -n $(K8S_NAMESPACE) deployment/$(K8S_RELEASE)-$$app --timeout=300s 2>/dev/null || true; \
	done
	@echo ""
	@echo "Mortgage demo is ready:"
	@echo "  Chat UI:      http://localhost:8031"
	@echo "  Registry UI:  http://localhost:8030"
	@echo "  Registry API: http://localhost:8050"

## Alias for mortgage-up. The k8s chart's pipeline job always runs with
## --skip-governance (see mortgage-pipeline-job.yaml), so there is no separate
## "fast" path on kind — kept as an alias for backward compatibility.
mortgage-up-fast: mortgage-up

mortgage-down: k8s-down

mortgage-logs:
	@echo "=== agents-customer ===" && kubectl logs -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-agents-customer --tail=100 --all-containers=true || true
	@echo "=== agents-kyc-credit ===" && kubectl logs -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-agents-kyc-credit --tail=100 --all-containers=true || true
	@echo "=== agents-core-banking ===" && kubectl logs -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-agents-core-banking --tail=100 --all-containers=true || true

mortgage-ps:
	kubectl get pods -n $(K8S_NAMESPACE) -o wide

mortgage-test:
	@./demo/mortgage/scripts/test_e2e.sh

# =============================================================================
# Kubernetes (kind)
# =============================================================================

K8S_CLUSTER   ?= recursant
K8S_NAMESPACE ?= recursant
K8S_RELEASE   ?= recursant
K8S_CHART     = k8s/charts/recursant

## Full deploy: tear down, create cluster, build all images, deploy, test
k8s-all: k8s-down k8s-up k8s-build k8s-load k8s-install
	@echo ""
	@echo "Waiting for all pods to be Ready (no Terminating)..."
	@while kubectl get pods -n $(K8S_NAMESPACE) --no-headers 2>/dev/null | grep -qvE 'Running|Completed'; do \
		sleep 3; \
	done
	bash k8s/scripts/smoke-test.sh

k8s-up:
	bash k8s/scripts/kind-up.sh

k8s-down:
	kind delete cluster --name $(K8S_CLUSTER) 2>/dev/null || true

k8s-build:
	docker build -t recursant-registry registry/
	docker build -t recursant-frontend registry/frontend/
	docker build -t recursant-test-agent registry/test_agent/
	docker build -t recursant-sidecar -f mesh/docker/Dockerfile.sidecar mesh/
	docker build -t recursant-agent-a --build-arg AGENT_DIR=examples/agent_a -f mesh/docker/Dockerfile.agent mesh/
	docker build -t recursant-agent-b --build-arg AGENT_DIR=examples/agent_b -f mesh/docker/Dockerfile.agent mesh/
	docker build -t recursant-webhook k8s/webhook/
	docker build -t recursant-agents-customer --build-arg AGENT_DIR=demo/mortgage/agents/customer -f demo/mortgage/docker/Dockerfile.agents .
	docker build -t recursant-agents-kyc-credit --build-arg AGENT_DIR=demo/mortgage/agents/kyc_credit -f demo/mortgage/docker/Dockerfile.agents .
	docker build -t recursant-agents-core-banking --build-arg AGENT_DIR=demo/mortgage/agents/core_banking -f demo/mortgage/docker/Dockerfile.agents .
	docker build -t recursant-agents-compliance -f demo/mortgage/docker/Dockerfile.agents-compliance .
	docker build -t recursant-mortgage-frontend demo/mortgage/frontend/
	docker build -t recursant-stub-apis -f demo/mortgage/stubs/Dockerfile demo/mortgage/stubs/
	docker build -t recursant-mcp -f demo/mortgage/docker/Dockerfile.mcp .
	docker build -t recursant-n8n-bridge -f demo/mortgage/docker/Dockerfile.n8n-bridge .

# k8s-load depends on k8s-build so it always loads the freshest images.
# `kind load` only ships what's already in the local docker daemon, so
# without this dep, calling `make k8s-load` directly can silently push
# stale code from a previous build into the cluster.
k8s-load: k8s-build
	kind load docker-image recursant-registry recursant-frontend recursant-test-agent recursant-sidecar recursant-agent-a recursant-agent-b recursant-webhook recursant-agents-customer recursant-agents-kyc-credit recursant-agents-core-banking recursant-agents-compliance recursant-mortgage-frontend recursant-stub-apis recursant-mcp recursant-n8n-bridge --name $(K8S_CLUSTER)

k8s-install:
	@# Source secrets from .env if it exists
	$(eval include .env)
	helm upgrade --install $(K8S_RELEASE) $(K8S_CHART) \
		-f $(K8S_CHART)/values-mortgage.yaml \
		$(if $(ADMIN_PASSWORD),--set secrets.adminPassword=$(ADMIN_PASSWORD)) \
		$(if $(ADMIN_USERNAME),--set secrets.adminUsername=$(ADMIN_USERNAME)) \
		$(if $(JWT_SECRET_KEY),--set secrets.jwtSecretKey=$(JWT_SECRET_KEY)) \
		$(if $(SECRET_KEY),--set secrets.secretKey=$(SECRET_KEY)) \
		$(if $(MESH_API_KEY),--set secrets.meshApiKey=$(MESH_API_KEY)) \
		$(if $(ANTHROPIC_API_KEY),--set secrets.anthropicApiKey=$(ANTHROPIC_API_KEY)) \
		$(if $(OPENAI_API_KEY),--set secrets.openaiApiKey=$(OPENAI_API_KEY)) \
		$(if $(GOOGLE_API_KEY),--set secrets.googleApiKey=$(GOOGLE_API_KEY)) \
		$(if $(MOONSHOT_API_KEY),--set secrets.moonshotApiKey=$(MOONSHOT_API_KEY)) \
		$(if $(OPENROUTER_API_KEY),--set secrets.openrouterApiKey=$(OPENROUTER_API_KEY)) \
		$(if $(EVAL_JUDGE_PROVIDER),--set secrets.evalJudgeProvider=$(EVAL_JUDGE_PROVIDER)) \
		$(if $(EVAL_JUDGE_MODEL),--set secrets.evalJudgeModel=$(EVAL_JUDGE_MODEL)) \
		--namespace $(K8S_NAMESPACE) --create-namespace \
		--wait --timeout 1200s

k8s-smoke-test:
	bash k8s/scripts/smoke-test.sh

k8s-test:
	bash k8s/scripts/run-integration-tests.sh all

k8s-test-governance:
	bash k8s/scripts/run-integration-tests.sh governance

k8s-test-compliance:
	bash k8s/scripts/run-integration-tests.sh compliance

k8s-test-features:
	bash k8s/scripts/run-integration-tests.sh k8s-features

k8s-test-registry:
	bash k8s/scripts/run-integration-tests.sh registry-e2e

k8s-test-a2a:
	bash k8s/scripts/run-integration-tests.sh a2a

k8s-test-isolation:
	bash k8s/scripts/run-integration-tests.sh isolation

k8s-test-llm:
	bash k8s/scripts/run-integration-tests.sh llm-roundtrip

k8s-test-banking:
	bash k8s/scripts/run-integration-tests.sh banking

k8s-test-lifecycle:
	bash k8s/scripts/run-integration-tests.sh registry-lifecycle

k8s-test-governance-enforcement:
	bash k8s/scripts/run-integration-tests.sh governance-enforcement

k8s-test-guardrail-integration:
	bash k8s/scripts/run-integration-tests.sh guardrail-integration

## OpenClaw integration tests (registry endpoints, in-pod, real HTTP)
k8s-test-openclaw:
	$(eval POD := $(shell kubectl get pod -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-registry -o jsonpath='{.items[0].metadata.name}'))
	kubectl cp registry/tests/integration/test_openclaw.py $(K8S_NAMESPACE)/$(POD):/app/tests/integration/test_openclaw.py -c registry
	kubectl exec -n $(K8S_NAMESPACE) $(POD) -c registry -- \
	  python -m pytest tests/integration/test_openclaw.py -v -m integration

## Provision a local OpenClaw instance with the recursant plugin
openclaw-setup:
	bash integrations/openclaw/scripts/setup-openclaw.sh

## Start the OpenClaw gateway with OPENROUTER_API_KEY in env
openclaw-gateway:
	bash integrations/openclaw/scripts/start-gateway.sh

## End-to-end smoke test: send a message, verify audit row lands
openclaw-smoke:
	bash integrations/openclaw/scripts/smoke-test.sh

k8s-status:
	@echo "=== Pods ==="
	kubectl get pods -n $(K8S_NAMESPACE) -o wide
	@echo ""
	@echo "=== Services ==="
	kubectl get svc -n $(K8S_NAMESPACE)

k8s-logs:
	@echo "=== Registry ===" && kubectl logs -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-registry --tail=50 || true
	@echo "" && echo "=== Webhook ===" && kubectl logs -n $(K8S_NAMESPACE) -l app=$(K8S_RELEASE)-webhook --tail=20 || true

k8s-port-forward:
	@echo "Starting port forwards (Ctrl+C to stop)..."
	@echo "  Registry:           http://localhost:5000"
	@echo "  Registry Frontend:  http://localhost:3000"
	@echo "  Mortgage Frontend:  http://localhost:3001"
	kubectl port-forward -n $(K8S_NAMESPACE) svc/$(K8S_RELEASE)-registry 5000:5000 &
	kubectl port-forward -n $(K8S_NAMESPACE) svc/$(K8S_RELEASE)-frontend 3000:80 &
	kubectl port-forward -n $(K8S_NAMESPACE) svc/$(K8S_RELEASE)-mortgage-frontend 3001:80 &
	@wait

# =============================================================================
# Multi-cluster active-active HA
# =============================================================================

MC_CLUSTER1 = recursant-1
MC_CLUSTER2 = recursant-2
MC_NS       = recursant
MC_RELEASE  = recursant
MC_CHART    = k8s/charts/recursant

## Create both kind clusters with shared network, build images, deploy to both
multi-cluster-up:
	bash k8s/scripts/kind-multi-cluster.sh
	$(MAKE) k8s-build
	kind load docker-image recursant-registry recursant-frontend recursant-test-agent \
		recursant-sidecar recursant-agent-a recursant-agent-b recursant-webhook \
		--name $(MC_CLUSTER1)
	kind load docker-image recursant-registry recursant-frontend recursant-test-agent \
		recursant-sidecar recursant-agent-a recursant-agent-b recursant-webhook \
		--name $(MC_CLUSTER2)
	@echo "Detecting cluster node IPs ..."
	$(eval C1_IP := $(shell docker inspect $(MC_CLUSTER1)-control-plane -f '{{(index .NetworkSettings.Networks "kind-multi").IPAddress}}' 2>/dev/null))
	$(eval C2_IP := $(shell docker inspect $(MC_CLUSTER2)-control-plane -f '{{(index .NetworkSettings.Networks "kind-multi").IPAddress}}' 2>/dev/null))
	@echo "  Cluster 1 IP: $(C1_IP)"
	@echo "  Cluster 2 IP: $(C2_IP)"
	helm upgrade --install $(MC_RELEASE) $(MC_CHART) \
		-f $(MC_CHART)/values-cluster-1.yaml \
		--set multiCluster.remoteDbHost=$(C2_IP) \
		--set multiCluster.remoteRegistryUrl=http://$(C2_IP):30500 \
		--set db.replication.remoteHost=$(C2_IP) \
		--namespace $(MC_NS) --create-namespace \
		--kube-context kind-$(MC_CLUSTER1) \
		--wait --timeout 1200s
	helm upgrade --install $(MC_RELEASE) $(MC_CHART) \
		-f $(MC_CHART)/values-cluster-2.yaml \
		--set multiCluster.remoteDbHost=$(C1_IP) \
		--set multiCluster.remoteRegistryUrl=http://$(C1_IP):30500 \
		--set db.replication.remoteHost=$(C1_IP) \
		--namespace $(MC_NS) --create-namespace \
		--kube-context kind-$(MC_CLUSTER2) \
		--wait --timeout 1200s
	@echo ""
	@echo "Multi-cluster deployment complete."
	@echo "  Cluster 1: http://localhost:8050  (API)  http://localhost:8030  (frontend)"
	@echo "  Cluster 2: http://localhost:8052  (API)  http://localhost:8032  (frontend)"

## Tear down both clusters
multi-cluster-down:
	bash k8s/scripts/kind-multi-cluster-down.sh

## Run cross-cluster HA integration tests
multi-cluster-test:
	cd mesh && .venv/bin/pytest tests/integration/test_multi_cluster_ha.py -v

## Show status of both clusters
multi-cluster-status:
	@echo "=== Cluster 1 ($(MC_CLUSTER1)) ==="
	kubectl get pods -n $(MC_NS) --context kind-$(MC_CLUSTER1) -o wide 2>/dev/null || echo "  not running"
	@echo ""
	@echo "=== Cluster 2 ($(MC_CLUSTER2)) ==="
	kubectl get pods -n $(MC_NS) --context kind-$(MC_CLUSTER2) -o wide 2>/dev/null || echo "  not running"
