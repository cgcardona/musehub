.PHONY: help test test-fast test-cov typecheck seed seed-local seed-prs seed-narratives docker-up docker-down docker-logs

PYTHON  ?= python
PYTEST  ?= pytest
MYPY    ?= mypy
DOCKER  ?= docker compose

help:           ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

# Local Postgres exposed by docker-compose on a non-default port (5433)
# to avoid clashing with any locally-installed Postgres instance.
# Set DATABASE_URL in your shell or .env to override.
LOCAL_PG_URL ?= postgresql+asyncpg://musehub:musehub@localhost:5434/musehub

# ── Testing ──────────────────────────────────────────────────────────────────

test:           ## Run full test suite inside Docker (no local deps required)
	$(DOCKER) exec musehub pytest tests/ -q --tb=short

test-fast:      ## Run tests without coverage inside Docker (faster feedback)
	$(DOCKER) exec musehub pytest tests/ -q --tb=short -p no:cov

test-cov:       ## Run tests with coverage inside Docker
	$(DOCKER) exec musehub pytest tests/ -q --tb=short --cov=musehub --cov-report=term-missing

test-single:    ## Run a single test file inside Docker: make test-single FILE=tests/test_musehub_repos.py
	$(DOCKER) exec musehub pytest $(FILE) -v --tb=short

test-k:         ## Run tests matching a keyword inside Docker: make test-k K=harmony
	$(DOCKER) exec musehub pytest -k "$(K)" -v --tb=short

# Local targets (require Docker Postgres reachable on :5434 from host)
test-local:     ## Run full test suite locally against Docker Postgres
	DATABASE_URL=$(LOCAL_PG_URL) $(PYTEST) -n auto --cov=musehub --cov-report=term-missing --tb=short -q

# ── Type checking ─────────────────────────────────────────────────────────────

typecheck:      ## Run mypy static type check over musehub/
	$(MYPY) musehub/ --ignore-missing-imports

# ── Database ──────────────────────────────────────────────────────────────────

seed:           ## Run all three seed scripts against the running Docker DB
	$(DOCKER) exec musehub python /app/scripts/seed_musehub.py --force
	$(DOCKER) exec musehub python /app/scripts/seed_pull_requests.py --force
	$(DOCKER) exec musehub python /app/scripts/seed_narratives.py --force

seed-prs:       ## Re-seed pull requests only (requires seed_musehub to have run first)
	$(DOCKER) exec musehub python /app/scripts/seed_pull_requests.py --force

seed-narratives: ## Re-seed narrative scenarios only (requires seed_musehub to have run first)
	$(DOCKER) exec musehub python /app/scripts/seed_narratives.py --force

seed-local:     ## Run all seed scripts locally (requires DATABASE_URL env var)
	$(PYTHON) scripts/seed_musehub.py --force
	$(PYTHON) scripts/seed_pull_requests.py --force
	$(PYTHON) scripts/seed_narratives.py --force

migrate:        ## Apply Alembic migrations in Docker
	$(DOCKER) exec musehub alembic upgrade head

migrate-local:  ## Apply Alembic migrations locally (requires DATABASE_URL env var)
	alembic upgrade head

# ── Docker ────────────────────────────────────────────────────────────────────

docker-up:      ## Start all Docker services
	$(DOCKER) up -d

docker-down:    ## Stop and remove containers (keeps volumes)
	$(DOCKER) down

docker-rebuild: ## Rebuild images and restart
	$(DOCKER) up -d --build

docker-nuke:    ## Tear down containers AND volumes (wipes DB)
	$(DOCKER) down -v

docker-logs:    ## Tail app logs
	$(DOCKER) logs -f musehub

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:          ## Remove __pycache__, .pyc, coverage artefacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name '*.pyc' -delete 2>/dev/null; true
	rm -rf .coverage coverage.xml htmlcov .pytest_cache
