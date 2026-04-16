IMAGE := digitalenvironments/hawki-toolkit-file-converter:local

TEMPORAL_HOST       ?= 127.0.0.1:7233
TEMPORAL_NAMESPACE  ?= default
TEMPORAL_TASK_QUEUE ?= file-converter

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build the Docker image
	docker build -t $(IMAGE) .

.PHONY: up
up: build ## Build and run the production container (requires .env with F_API_KEY)
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	if [ -z "$${F_API_KEY:-}" ]; then \
		echo "F_API_KEY not set. Provide it in .env or export it before running." >&2; \
		exit 1; \
	fi; \
	docker run --rm -p 8001:80 -e "F_API_KEY=$${F_API_KEY}" $(IMAGE)

.PHONY: ci-test
ci-test: ## Run CI tests via docker-compose.ci.yml
	docker compose -f docker-compose.ci.yml up --build --abort-on-container-exit
	docker compose -f docker-compose.ci.yml down --remove-orphans

.PHONY: lint
lint: ## Run ruff linter
	uv run ruff check --fix .
	uv run ruff format .

.PHONY: down
down: ## Stop and remove containers
	docker compose -f docker-compose.ci.yml down --remove-orphans 2>/dev/null || true
	docker rm -f $$(docker ps -q --filter "ancestor=$(IMAGE)") 2>/dev/null || true

.PHONY: temporal
temporal: ## Start Temporal dev server (gRPC on 7233, UI on 8233)
	TEMPORAL_NAMESPACE=$(TEMPORAL_NAMESPACE) \
	TEMPORAL_TASK_QUEUE=$(TEMPORAL_TASK_QUEUE) \
	uv run python dev_server.py

.PHONY: worker
worker: ## Run the Temporal worker locally (polls the dev server)
	TEMPORAL_HOST=$(TEMPORAL_HOST) \
	TEMPORAL_NAMESPACE=$(TEMPORAL_NAMESPACE) \
	TEMPORAL_TASK_QUEUE=$(TEMPORAL_TASK_QUEUE) \
	uv run python task.py

.PHONY: dev
dev: ## Run the FastAPI dev server locally (talks to the dev server)
	TEMPORAL_HOST=$(TEMPORAL_HOST) \
	TEMPORAL_NAMESPACE=$(TEMPORAL_NAMESPACE) \
	TEMPORAL_TASK_QUEUE=$(TEMPORAL_TASK_QUEUE) \
	uv run dev
