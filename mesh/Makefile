.PHONY: help install test test-unit test-integration test-llm test-smoke test-step1 test-step2 test-step3 test-step4 test-step5 test-step6 test-step7 test-step8 test-step9 test-step10 test-step11 lint

VENV := .venv/bin
PYTEST := $(VENV)/pytest

help:
	@echo "Available commands:"
	@echo "  make install           - Create venv and install dependencies"
	@echo "  make test              - Run all tests"
	@echo "  make test-unit         - Run unit tests only"
	@echo "  make test-integration  - Run integration tests (including LLM)"
	@echo "  make test-llm          - Run LLM integration tests only"
	@echo "  make test-step1        - Step 1: Project scaffolding & config"
	@echo "  make test-step2        - Step 2: Agent Card loading & serving"
	@echo "  make test-step3        - Step 3: Interceptor pipeline"
	@echo "  make test-step4        - Step 4: A2A server (inbound)"
	@echo "  make test-step5        - Step 5: A2A client (outbound)"
	@echo "  make test-step6        - Step 6: Registry control plane & sidecar client"
	@echo "  make test-step7        - Step 7: RecursantA2AClient (LangGraph integration)"
	@echo "  make test-step8        - Step 8: mTLS certificate generation"
	@echo "  make test-step9        - Step 9: Example LangGraph agents"
	@echo "  make test-step10       - Step 10: Docker Compose setup"
	@echo "  make test-step11       - Step 11: Integration tests"
	@echo "  make test-smoke        - Smoke tests (requires Docker Compose)"
	@echo "  make lint              - Run linting"
	@echo ""
	@echo "  Docker commands have moved to the parent directory (../Makefile)"

install:
	python3 -m venv .venv
	$(VENV)/pip install -e ".[dev]"

test:
	$(PYTEST) tests/ -v

test-unit:
	$(PYTEST) tests/unit/ -v

test-integration:
	$(PYTEST) tests/integration/ -v -m ""

test-llm:
	$(PYTEST) tests/integration/test_llm_roundtrip.py -v

test-step1:
	$(PYTEST) tests/unit/test_config.py -v

test-step2:
	$(PYTEST) tests/unit/test_agent_card.py -v

test-step3:
	$(PYTEST) tests/unit/test_interceptors.py -v

test-step4:
	$(PYTEST) tests/unit/test_server.py -v

test-step5:
	$(PYTEST) tests/unit/test_client.py -v

test-step6:
	$(PYTEST) tests/unit/test_registry_client.py -v

test-step7:
	$(PYTEST) tests/unit/test_a2a_client.py -v

test-step8:
	$(PYTEST) tests/unit/test_certs.py -v

test-step9:
	$(PYTEST) tests/unit/test_example_agents.py -v

test-step10:
	$(PYTEST) tests/unit/test_docker_compose.py -v

test-step11:
	$(PYTEST) tests/integration/ -v

test-smoke:
	$(PYTEST) tests/smoke/ -v

lint:
	$(VENV)/python -m py_compile runtime/sidecar/config.py
	$(VENV)/python -m py_compile runtime/sidecar/agent_card.py
	$(VENV)/python -m py_compile runtime/common/models.py
