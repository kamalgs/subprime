.PHONY: help frontend-install frontend frontend-dev frontend-test \
        backend-test docker deploy-local clean

help:
	@echo "Build targets:"
	@echo "  frontend-install  Install npm deps (run once)"
	@echo "  frontend          Build React app → product/apps/web/static/dist/"
	@echo "  frontend-dev      Vite dev server on :5173 (proxies /api to :8091)"
	@echo "  frontend-test     Run vitest"
	@echo "  backend-test      Run pytest"
	@echo "  docker            Build finadvisor:local Docker image (needs frontend first)"
	@echo "  deploy-local      frontend → docker → nomad redeploy"
	@echo "  clean             Remove frontend build output"

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
