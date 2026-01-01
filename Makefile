# Project Makefile - Convenience commands for development
# Run `make help` to see available commands

.PHONY: help install lint format typecheck check fix clean pre-commit

# Default target
.DEFAULT_GOAL := help

# Colors for terminal output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

##@ General

help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\n${CYAN}Usage:${RESET}\n  make ${GREEN}<target>${RESET}\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  ${GREEN}%-15s${RESET} %s\n", $$1, $$2 } /^##@/ { printf "\n${YELLOW}%s${RESET}\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Setup

install: ## Install all dependencies (backend + frontend)
	@echo "Installing backend dependencies..."
	cd backend && uv sync --all-groups
	@echo "Installing frontend dependencies..."
	cd frontend && pnpm install
	@echo "Installing pre-commit hooks..."
	uv tool run pre-commit install
	uv tool run pre-commit install --hook-type commit-msg
	@echo "✅ All dependencies installed!"

install-backend: ## Install backend dependencies only
	cd backend && uv sync --all-groups

install-frontend: ## Install frontend dependencies only
	cd frontend && pnpm install

install-hooks: ## Install git hooks (pre-commit)
	@echo "Installing pre-commit hooks..."
	uv tool run pre-commit install
	uv tool run pre-commit install --hook-type commit-msg
	@echo "✅ pre-commit hooks installed"

##@ Linting & Formatting

lint: lint-backend lint-frontend ## Lint all code

lint-backend: ## Lint Python code with ruff
	cd backend && uv run ruff check .

lint-frontend: ## Lint frontend code with ESLint
	cd frontend && pnpm run lint

format: format-backend format-frontend ## Format all code

format-backend: ## Format Python code with ruff
	cd backend && uv run ruff format .

format-frontend: ## Format frontend code with Prettier
	cd frontend && pnpm run format

fix: fix-backend fix-frontend ## Auto-fix all linting issues

fix-backend: ## Auto-fix Python linting issues
	cd backend && uv run ruff check --fix .
	cd backend && uv run ruff format .

fix-frontend: ## Auto-fix frontend linting issues
	cd frontend && pnpm run lint:fix
	cd frontend && pnpm run format

##@ Type Checking

typecheck: typecheck-backend typecheck-frontend ## Type check all code

typecheck-backend: ## Type check Python with mypy
	cd backend && uv run mypy

typecheck-frontend: ## Type check frontend with vue-tsc
	cd frontend && pnpm run typecheck

##@ Quality Checks

check: check-backend check-frontend ## Run all checks (lint + typecheck)

check-backend: lint-backend typecheck-backend ## Run backend checks

check-frontend: ## Run frontend checks
	cd frontend && pnpm run check

pre-commit: ## Run pre-commit on all files
	uv tool run pre-commit run --all-files

pre-commit-update: ## Update pre-commit hooks to latest versions
	uv tool run pre-commit autoupdate

##@ Testing

test: test-backend test-frontend ## Run all tests (backend + frontend unit)

test-all: test-backend test-frontend test-e2e ## Run all tests including E2E

test-backend: ## Run Python tests
	cd backend && uv run pytest

test-backend-cov: ## Run Python tests with coverage
	cd backend && uv run pytest --cov=airbeeps --cov-report=html --cov-report=term

test-frontend: ## Run frontend unit tests
	cd frontend && pnpm test:unit

test-frontend-cov: ## Run frontend tests with coverage
	cd frontend && pnpm test:unit --coverage

test-e2e: ## Run E2E tests (Playwright)
	cd frontend && pnpm test:e2e

test-e2e-ui: ## Run E2E tests with UI (for debugging)
	cd frontend && pnpm exec playwright test --ui

##@ Development

dev: ## Start development servers (backend + frontend)
	@echo "Starting backend..."
	cd backend && uv run airbeeps dev &
	@echo "Starting frontend..."
	cd frontend && pnpm dev

dev-backend: ## Start backend development server
	cd backend && uv run airbeeps dev

dev-frontend: ## Start frontend development server
	cd frontend && pnpm dev

##@ Build

build: build-backend build-frontend ## Build all

build-backend: ## Build backend wheel
	cd backend && uv build

build-frontend: ## Build frontend for production
	cd frontend && pnpm build

##@ Cleanup

clean: ## Clean all build artifacts and caches
	@echo "Cleaning Python caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	rm -rf backend/dist backend/*.egg-info
	@echo "Cleaning frontend caches..."
	rm -rf frontend/.nuxt frontend/.output frontend/dist
	@echo "✅ Cleaned!"

clean-all: clean ## Clean everything including dependencies
	rm -rf backend/.venv
	rm -rf frontend/node_modules
	@echo "✅ All cleaned including dependencies!"
