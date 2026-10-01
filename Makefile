.PHONY: setup infra infra-down db sync api web dev test lint rogue rogue-down

# Follow the active Docker context, since Docker Desktop, Colima, and OrbStack use different sockets.
export DOCKER_HOST ?= $(shell docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null)
export TF_VAR_docker_host = $(DOCKER_HOST)

setup:  ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && pnpm install

infra:  ## Start Postgres and the fake Acme servers
	cd infra && terraform init -input=false >/dev/null && terraform apply -auto-approve -input=false

infra-down:  ## Remove every container Terraform created
	cd infra && terraform destroy -auto-approve -input=false

db:  ## Create tables, views, and the read-only role
	cd backend && uv run python -m app.cli init-db

sync:  ## Pull assets from every source into Postgres
	cd backend && uv run python -m app.cli sync

api:
	cd backend && uv run uvicorn app.main:app --port 8010 --reload

web:
	cd frontend && pnpm dev

dev:  ## Run the API and the web app together
	$(MAKE) -j2 api web

test:
	cd backend && uv run pytest -q
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm lint && pnpm typecheck

rogue:  ## Demo: start a server nobody registered
	docker run -d --name acme-rogue-01 --hostname rogue-01 --label acme.managed=true \
		--label acme.owner=mallory --label acme.env=prod alpine:3.22 sleep infinity

rogue-down:
	docker rm -f acme-rogue-01 2>/dev/null || true
