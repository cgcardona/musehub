.PHONY: help test test-fast test-cov typecheck seed docker-up docker-down docker-logs

PYTHON  ?= python
PYTEST  ?= pytest
MYPY    ?= mypy
DOCKER  ?= docker compose

help:           ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

# ── Testing ──────────────────────────────────────────────────────────────────

test:           ## Run full parallel test suite with coverage
	$(PYTEST) -n auto --cov=musehub --cov-report=term-missing --tb=short -q

test-fast:      ## Run tests without coverage (faster feedback loop)
	$(PYTEST) -n auto --tb=short -q

test-cov:       ## Run tests and open HTML coverage report
	$(PYTEST) -n auto --cov=musehub --cov-report=html --tb=short -q
	open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || true

test-single:    ## Run a single test file: make test-single FILE=tests/test_musehub_repos.py
	$(PYTEST) $(FILE) -v --tb=short

test-k:         ## Run tests matching a keyword: make test-k K=harmony
	$(PYTEST) -k "$(K)" -v --tb=short

# ── Type checking ─────────────────────────────────────────────────────────────

typecheck:      ## Run mypy static type check over musehub/
	$(MYPY) musehub/ --ignore-missing-imports

# ── Database ──────────────────────────────────────────────────────────────────

seed:           ## Run seed script against the running Docker DB
	$(DOCKER) exec musehub python /app/scripts/seed_musehub.py --force

seed-local:     ## Run seed script locally (requires DATABASE_URL env var)
	$(PYTHON) scripts/seed_musehub.py --force

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
