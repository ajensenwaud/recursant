.PHONY: help install run dev test test-unit test-integration lint docker-build docker-up docker-down docker-logs docker-exec seed-security seed-evaluation seed-agents wipe-agents db-init db-migrate db-upgrade db-downgrade shell k8s-test k8s-test-file

help:
	@echo "Available commands:"
	@echo "  make install          - Install Python dependencies"
	@echo "  make run              - Run the Flask application"
	@echo "  make dev              - Run in development mode with auto-reload"
	@echo "  make test             - Run all tests"
	@echo "  make test-unit        - Run unit tests only (excludes integration)"
	@echo "  make test-integration - Run integration tests (requires docker compose up)"
	@echo "  make lint             - Run linting"
	@echo "  make docker-build     - Build Docker image"
	@echo "  make docker-up        - Start Docker containers"
	@echo "  make docker-down      - Stop Docker containers"
	@echo "  make docker-logs      - Tail Docker container logs"
	@echo "  make docker-exec      - Open shell in API container"
	@echo "  make seed-admin       - Seed admin user and default groups"
	@echo "  make seed-security    - Seed built-in security test cases"
	@echo "  make seed-evaluation  - Seed evaluation suites"
	@echo "  make seed-agents      - Seed 10 sample agents via the API"
	@echo "  make seed-all         - Seed all data (admin + security + evaluation)"
	@echo "  make wipe-agents      - Delete all agents and related data from the DB"
	@echo "  make db-init          - Initialize database migrations"
	@echo "  make db-migrate       - Generate new migration"
	@echo "  make db-upgrade       - Apply migrations"
	@echo "  make k8s-test         - Run all tests in the K8s registry pod"
	@echo "  make k8s-test-file FILE=tests/test_foo.py - Run a specific test file in K8s"

install:
	pip install -r requirements.txt

run:
	python run.py

dev:
	FLASK_ENV=development flask run --reload

test:
	docker compose run --rm api python -m pytest tests/ -v

test-unit:
	docker compose run --rm api python -m pytest tests/ -v --ignore=tests/integration/

test-integration:
	docker compose run --rm api python -m pytest tests/integration/ -v -m integration

lint:
	flake8 app/ --max-line-length=100
	black --check app/

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-exec:
	docker compose exec api sh

seed-security:
	docker compose run --rm api python scripts/seed_security_tests.py

seed-evaluation:
	docker compose run --rm api python scripts/seed_evaluation_suites.py

seed-admin:
	docker compose run --rm api python scripts/seed_admin_user.py

seed-agents:
	docker compose exec api python scripts/seed_agents.py --api-url http://localhost:5000

seed-all: seed-admin seed-security seed-evaluation

wipe-agents:
	docker compose exec api python scripts/wipe_agents.py --yes

docker-migrate:
	docker compose run --rm api flask db upgrade

db-init:
	flask db init

db-migrate:
	flask db migrate -m "$(msg)"

db-upgrade:
	flask db upgrade

db-downgrade:
	flask db downgrade

shell:
	flask shell

# ---------------------------------------------------------------
# Kubernetes test targets
# ---------------------------------------------------------------
# Run registry tests inside the K8s registry pod.
# Copies local source + test files into the pod, creates the test DB
# if needed, runs pytest, then cleans up.

K8S_NS ?= recursant
K8S_REGISTRY_POD = $(shell kubectl get pods -n $(K8S_NS) -l app=recursant-registry -o jsonpath='{.items[0].metadata.name}')
K8S_DB_POD = $(shell kubectl get pods -n $(K8S_NS) -l app=recursant-db -o jsonpath='{.items[0].metadata.name}')
K8S_TEST_DB_URL = postgresql://registry:registry@recursant-db:5432/registry_test

# Sync local code to the registry pod
k8s-sync:
	@echo "Syncing source to pod $(K8S_REGISTRY_POD)..."
	@kubectl cp -n $(K8S_NS) app/ $(K8S_REGISTRY_POD):/app/app/ 2>/dev/null
	@kubectl cp -n $(K8S_NS) tests/ $(K8S_REGISTRY_POD):/app/tests/ 2>/dev/null
	@echo "Sync complete."

# Ensure the test database exists
k8s-test-db:
	@kubectl exec -n $(K8S_NS) $(K8S_DB_POD) -- psql -U registry -tc \
		"SELECT 1 FROM pg_database WHERE datname='registry_test'" | grep -q 1 || \
		kubectl exec -n $(K8S_NS) $(K8S_DB_POD) -- psql -U registry -c "CREATE DATABASE registry_test"

# Run all registry tests in K8s
k8s-test: k8s-sync k8s-test-db
	kubectl exec -n $(K8S_NS) $(K8S_REGISTRY_POD) -- \
		env TEST_DATABASE_URL=$(K8S_TEST_DB_URL) \
		python -m pytest tests/ -v --tb=short $(ARGS)

# Run a specific test file, e.g.: make k8s-test-file FILE=tests/test_adversarial.py
k8s-test-file: k8s-sync k8s-test-db
	kubectl exec -n $(K8S_NS) $(K8S_REGISTRY_POD) -- \
		env TEST_DATABASE_URL=$(K8S_TEST_DB_URL) \
		python -m pytest $(FILE) -v --tb=short $(ARGS)
