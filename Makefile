# Deploys the committed HEAD to the VPS that serves app.hubgentic.ai.
# Server layout (one-time setup, see README): code in /opt/hubgentic/app,
# systemd unit `hubgentic`, Caddy reverse proxy, SQLite in /var/lib/hubgentic.

DEPLOY_HOST ?= cerebrus
APP_URL     ?= https://app.hubgentic.ai
APP_DIR     := /opt/hubgentic/app
UV_ENV      := UV_PYTHON_INSTALL_DIR=/opt/hubgentic/python UV_CACHE_DIR=/opt/hubgentic/.uvcache

.PHONY: test deploy status logs

test:
	uv run pytest -q

# Ships only what is committed; refuses to run with uncommitted changes so the
# server always matches a revision you can name.
deploy: test
	@git diff --quiet HEAD -- || { echo "Uncommitted changes — commit or stash before deploying."; exit 1; }
	@rev=$$(git rev-parse --short HEAD); echo "→ deploying $$rev to $(DEPLOY_HOST)"; \
	git archive --format=tar HEAD | ssh $(DEPLOY_HOST) "set -e; \
		stage=\$$(mktemp -d); trap 'rm -rf \$$stage' EXIT; \
		tar -x -C \$$stage; echo $$rev > \$$stage/REVISION; \
		chmod 755 \$$stage; \
		rsync -a --delete --exclude /.venv \$$stage/ $(APP_DIR)/; \
		cd $(APP_DIR) && $(UV_ENV) uv sync --frozen --no-dev -q; \
		sudo systemctl restart hubgentic; \
		for i in 1 2 3 4 5 6 7 8 9 10; do curl -sf 127.0.0.1:8010/healthz >/dev/null && break; sleep 1; done; \
		curl -sf 127.0.0.1:8010/healthz >/dev/null || { sudo journalctl -u hubgentic -n 30 --no-pager; exit 1; }"
	@curl -sf $(APP_URL)/healthz >/dev/null && echo "✓ $(APP_URL) is up on $$(git rev-parse --short HEAD)" \
		|| { echo "✗ $(APP_URL)/healthz failed"; exit 1; }

status:
	@ssh $(DEPLOY_HOST) "echo deployed: \$$(cat $(APP_DIR)/REVISION 2>/dev/null || echo unknown); systemctl is-active hubgentic"
	@echo "local HEAD: $$(git rev-parse --short HEAD)"

logs:
	ssh $(DEPLOY_HOST) "sudo journalctl -u hubgentic -n 100 --no-pager"

# ── marketing site (www.hubgentic.ai) ──────────────────────────────────
SITE_DIR := /var/www/hubgentic-site

.PHONY: site site-dev deploy-site

site:
	uv run python site/build.py

site-dev:
	uv run python site/serve.py

# Like `deploy`, only ships committed copy so the live site matches a revision.
deploy-site: site
	@git diff --quiet HEAD -- site || { echo "Uncommitted changes in site/ — commit before deploying."; exit 1; }
	rsync -rlz --delete site/dist/ $(DEPLOY_HOST):$(SITE_DIR)/
	@curl -sf https://www.hubgentic.ai/ | grep -q "/assets/site.css?v=" \
		&& echo "✓ https://www.hubgentic.ai is serving this build ($$(git rev-parse --short HEAD))" \
		|| echo "Uploaded to $(DEPLOY_HOST):$(SITE_DIR); www.hubgentic.ai is not serving it yet (DNS or Caddy)."
