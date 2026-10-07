.PHONY: help lint fix typecheck test dlq-replay
.DEFAULT_GOAL := help

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-11s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

lint: ## Run ruff check, no changes made
	poetry run ruff check .

fix: ## Run ruff check --fix, then ruff format
	poetry run ruff check --fix .
	poetry run ruff format .

typecheck: ## Run pyright (strict for src and migrations)
	poetry run pyright

test: ## Run all tests (DB/broker tests skip without DATABASE_URL / RABBITMQ_URL)
	poetry run python -m unittest discover

dlq-replay: ## Move payments.new.dlq messages back to payments.new (compose stack must be running)
	docker compose exec consumer python -m payments_processing.presentation.cli.replay_dlq
