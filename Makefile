.PHONY: help dev prod down logs test test-backend test-frontend lint format migrate migration shell seed

help:
	@echo "Available commands:"
	@echo "  make dev            - Start development environment"
	@echo "  make prod           - Start production environment"
	@echo "  make down           - Stop all containers"
	@echo "  make logs           - View container logs"
	@echo "  make test           - Run all tests"
	@echo "  make test-backend   - Run backend tests"
	@echo "  make test-frontend  - Run frontend tests"
	@echo "  make lint           - Run linters"
	@echo "  make format         - Format code"
	@echo "  make migrate        - Run database migrations"
	@echo "  make migration      - Create new migration (usage: make migration m='message')"
	@echo "  make shell          - Open shell in API container"
	@echo "  make seed           - Generate seed data"

dev:
	docker compose -f docker-compose.dev.yml up --build

prod:
	docker compose up --build -d

down:
	docker compose down
	docker compose -f docker-compose.dev.yml down

logs:
	docker compose logs -f

test: test-backend test-frontend

test-backend:
	cd backend && pytest -v --cov=app tests/

test-frontend:
	cd frontend && npm test

lint:
	cd backend && ruff check app tests
	cd frontend && npm run lint

format:
	cd backend && ruff format app tests && ruff check --fix app tests

migrate:
	cd backend && alembic upgrade head

migration:
	cd backend && alembic revision --autogenerate -m "$(m)"

shell:
	docker compose exec api /bin/bash

seed:
	cd backend && python -m scripts.seed_events
