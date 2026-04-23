.PHONY: help frontend-install frontend frontend-dev frontend-test \
        backend-test docker deploy-local clean hooks-install \
        test test-fast smoke-api smoke-ui mutate mutate-report

help:
	@echo "Build targets:"
	@echo "  frontend-install  Install npm deps (run once)"
	@echo "  frontend          Build React app → product/apps/web/static/dist/"
	@echo "  frontend-dev      Vite dev server on :5173 (proxies /api to :8091)"
	@echo "  frontend-test     Run vitest"
	@echo "  backend-test      Run pytest (default suite)"
	@echo "  test              Alias for backend-test"
	@echo "  test-fast         Run the unit-only subset used by the pre-commit hook"
	@echo "  hooks-install     Install git pre-commit + pre-push hooks"
	@echo "  mutate            Run mutation testing on plan_report + observability"
	@echo "  mutate-report     Show the last mutmut results"
	@echo "  docker            Build finadvisor:local Docker image (needs frontend first)"
	@echo "  deploy-local      frontend → docker → nomad redeploy"
	@echo "  clean             Remove frontend build output"

# -----------------------------------------------------------------------------
# Test / quality gates
# -----------------------------------------------------------------------------

test: backend-test

test-fast:
	uv run --directory product pytest -q \
	    tests/test_api_v2_format.py \
	    tests/test_plan_report.py \
	    tests/test_observability.py \
	    tests/test_core

# API-level deploy gate: exercises strategy + plan flows in-process with
# stubbed LLM calls. Fast (<15s), no network. Run before `make docker`.
smoke-api:
	uv run --directory product pytest -q tests/test_api_v2.py

# UI deploy gate: drives the real React SPA with headless Chromium and
# stubbed LLM calls. Catches strategy/plan UI regressions that the JSON
# tests can't see. Needs `make frontend` + Playwright chromium.
smoke-ui:
	@if [ ! -f "$(DIST_DIR)/index.html" ]; then \
	  echo "ERROR: SPA build missing — run 'make frontend' first"; exit 1; \
	fi
	uv run --directory product pytest -q -m browser tests/test_frontend_e2e.py

hooks-install:
	uv run pre-commit install
	uv run pre-commit install -t pre-push
	@echo "✓ pre-commit + pre-push hooks installed"

# Mutation testing — configuration in pyproject.toml [tool.mutmut].
# Scoped to modules with strong unit coverage; widening produces noise.
mutate:
	@echo "→ mutation testing (config in pyproject.toml [tool.mutmut])"
	@echo "→ this may take several minutes"
	uv run mutmut run || true
	@$(MAKE) --no-print-directory mutate-report

mutate-report:
	@uv run mutmut results

# -----------------------------------------------------------------------------
# Frontend
# -----------------------------------------------------------------------------

FRONTEND_DIR := product/apps/web/frontend
DIST_DIR     := product/apps/web/static/dist

frontend-install:
	cd $(FRONTEND_DIR) && npm ci

frontend:
	cd $(FRONTEND_DIR) && npm run build
	@echo "→ built to $(DIST_DIR)"

frontend-dev:
	cd $(FRONTEND_DIR) && npm run dev

frontend-test:
	cd $(FRONTEND_DIR) && npm run test

# -----------------------------------------------------------------------------
# Backend
# -----------------------------------------------------------------------------

backend-test:
	uv run pytest -q

# -----------------------------------------------------------------------------
# Docker + deploy
# -----------------------------------------------------------------------------

docker:
	@if [ ! -d "$(DIST_DIR)" ]; then \
	  echo "ERROR: $(DIST_DIR) not found — run 'make frontend' first"; exit 1; \
	fi
	sudo docker build -t finadvisor:local -f product/Dockerfile .

deploy-local: frontend docker
	cd ~/projects/nomad/jobs && terraform taint nomad_job.finadvisor && terraform apply -auto-approve

clean:
	rm -rf $(DIST_DIR)
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules/.vite
