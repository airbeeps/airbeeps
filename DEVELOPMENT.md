# Development Setup

This document describes the development tooling and setup for the AirBeeps project.

## Prerequisites

- **Python 3.13+** with [uv](https://docs.astral.sh/uv/) package manager
- **Node.js 20+** with [pnpm](https://pnpm.io/) package manager
- **Git** for version control

## Quick Start

### Linux / macOS

```bash
# Install all dependencies and hooks
make install

# Or manually:
cd backend && uv sync --all-groups
cd frontend && pnpm install
uv tool install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

### Windows (PowerShell)

```powershell
# Backend dependencies
cd backend
uv sync --all-groups
cd ..

# Frontend dependencies
cd frontend
pnpm install
cd ..

# Install pre-commit hooks
uv tool install pre-commit ruff
pre-commit install
pre-commit install --hook-type commit-msg
```

## Development Tooling

### Python (Backend)

| Tool | Purpose | Configuration |
|------|---------|---------------|
| **Ruff** | Linting + Formatting | `pyproject.toml` (root) |
| **mypy** | Type checking | `pyproject.toml` (root) |
| **pytest** | Testing | `backend/pytest.ini` |

### Frontend (Nuxt/Vue)

| Tool | Purpose | Configuration |
|------|---------|---------------|
| **ESLint** | Linting | `frontend/eslint.config.mjs` |
| **Prettier** | Formatting | `frontend/prettier.config.mjs` |
| **vue-tsc** | Type checking | `frontend/tsconfig.json` |

### Common Commands

#### Using Make (Linux/macOS)

```bash
make lint        # Lint all code
make format      # Format all code
make fix         # Auto-fix linting issues
make typecheck   # Type check everything
make check       # Run all checks
make pre-commit  # Run pre-commit on all files
```

#### Using PowerShell (Windows)

```powershell
# Install dependencies
cd backend; uv sync --all-groups; cd ..
cd frontend; pnpm install; cd ..

# Lint
cd backend; uv run ruff check .; cd ..     # Python
cd frontend; pnpm lint; cd ..              # Frontend

# Format
cd backend; uv run ruff format .; cd ..    # Python
cd frontend; pnpm format; cd ..            # Frontend

# Auto-fix
cd backend; uv run ruff check --fix .; uv run ruff format .; cd ..  # Python
cd frontend; pnpm lint:fix; pnpm format; cd ..   # Frontend

# Type check
cd backend; uv run mypy; cd ..       # Python
cd frontend; pnpm typecheck; cd ..         # Frontend

# Run all frontend checks
cd frontend; pnpm check; cd ..

# Pre-commit (all files)
pre-commit run --all-files
```

## Git Hooks

We use **pre-commit** for Git hooks.

```bash
# Install
uv tool install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# Run manually
pre-commit run --all-files
```

## Editor Setup

### VS Code / Cursor

The project includes `.vscode/settings.json` with recommended settings. Install the recommended extensions from `.vscode/extensions.json`.

**Required Extensions:**
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)
- Volar (Vue.volar)
- ESLint (dbaeumer.vscode-eslint)
- Prettier (esbenp.prettier-vscode)
- EditorConfig (EditorConfig.EditorConfig)

### Other Editors

The `.editorconfig` file provides consistent settings for most editors that support EditorConfig.

## Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` (root) | Ruff, mypy, pytest, coverage config |
| `backend/pyproject.toml` | Python package definition |
| `frontend/eslint.config.mjs` | ESLint flat config |
| `frontend/prettier.config.mjs` | Prettier config |
| `.pre-commit-config.yaml` | Pre-commit hooks |
| `.editorconfig` | Editor settings |
| `.gitattributes` | Git file handling |
| `.typos.toml` | Spell checker config |
| `Makefile` | Convenience commands |

## Database Initialization & Seeding

The project uses a YAML-based seeding system to initialize database with default configurations, providers, models, and assistants.

### Seed File

All default data is defined in **`backend/airbeeps/config/seed.yaml`** which includes:
- **System configs** - UI toggles, feature flags, global settings
- **Providers** - LLM provider configurations (OpenAI, Anthropic, etc.)
- **Models** - Available AI models and their capabilities
- **Assistants** - Default assistant templates
- **Ingestion profiles** - Document processing templates

### Bootstrap Commands

For most development workflows, you only need the `init` command:

```bash
cd backend

# Primary command: Full initialization (migrations + seeding)
# Run this after pulling new code or setting up the project
uv run scripts/bootstrap.py init
```

**Advanced commands** (for specific use cases):

```bash
# Run migrations only (no seeding)
uv run scripts/bootstrap.py migrate

# Seed/reseed from YAML only (no migrations)
# Useful when you've added new configs to seed.yaml
uv run scripts/bootstrap.py config-init

# Seed with custom YAML file
uv run scripts/bootstrap.py seed --file path/to/custom.yaml

# Create a superuser manually
uv run scripts/bootstrap.py superuser --email admin@example.com

# List existing superusers
uv run scripts/bootstrap.py list-superusers

# ⚠️ Reset database (DANGER: drops all data - dev only)
uv run scripts/bootstrap.py reset-db --force
```

### Adding New System Configs

To add a new system configuration (e.g., UI toggles):

1. Add entry to `backend/airbeeps/config/seed.yaml` under `system_configs`:
   ```yaml
   - key: ui_show_my_feature
     value: true
     description: "Show my feature in UI"
     is_public: true    # Frontend can read it
     is_enabled: true
   ```

2. Update frontend types in `frontend/app/types/api.d.ts`:
   ```typescript
   export interface PublicConfig {
     ui_show_my_feature?: boolean;
   }
   ```

3. Run seeding (idempotent, won't duplicate):
   ```bash
   uv run scripts/bootstrap.py config-init
   ```

See `.cursor/rules/adding-ui-toggles-for-chat-controls.mdc` for complete guide on adding UI toggles.

## Testing

This project includes comprehensive testing at multiple levels: backend unit/integration tests, frontend unit tests, and end-to-end tests.

### Environment Variables

All backend settings use the `AIRBEEPS_` prefix. For example:
- `AIRBEEPS_DATABASE_URL` → `settings.DATABASE_URL`
- `AIRBEEPS_TEST_MODE` → `settings.TEST_MODE`
- `AIRBEEPS_SECRET_KEY` → `settings.SECRET_KEY`

### Test Mode (`AIRBEEPS_TEST_MODE`)

The backend supports a **test mode** that replaces all external LLM and embedding API calls with deterministic fake implementations. This ensures:

- Tests never make real API calls (even if API keys are present)
- Responses are deterministic and predictable
- Tests run quickly without network dependencies

**Enable test mode:**
```bash
# Environment variable
export AIRBEEPS_TEST_MODE=1

# Or in .env file
AIRBEEPS_TEST_MODE=1
```

**What test mode does:**
- `create_chat_model()` returns `FakeLiteLLMClient` instead of real LiteLLM client
- `EmbeddingService.get_embedder()` returns `FakeEmbeddings` instead of real embeddings
- Provider utility endpoints (`/test-connection`, `/discover-models`) return mock data
- Fake responses contain `TEST_MODE_RESPONSE:` prefix for easy verification

### Running Tests

#### Backend Tests (pytest)

```bash
cd backend

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=airbeeps --cov-report=html

# Run specific test file
uv run pytest tests/api/test_core_flow.py

# Run with verbose output
uv run pytest -v

# Run only test mode guard tests
uv run pytest tests/test_llm_test_mode.py
```

#### Frontend Unit Tests (Vitest)

```bash
cd frontend

# Run all unit tests
pnpm test:unit

# Run in watch mode
pnpm test:unit:watch

# Run with coverage
pnpm test:unit:cov
```

#### E2E Tests (Playwright)

```bash
cd frontend

# Run all E2E tests
pnpm test:e2e

# Run with UI mode
pnpm test:e2e:ui

# Run in debug mode
pnpm test:e2e:debug
```

**Note:** E2E tests automatically start both backend and frontend servers via Playwright's `webServer` configuration. The backend runs in test mode with a temporary database.

### Test Directory Structure

```
backend/tests/
├── conftest.py           # Pytest fixtures
├── helpers/              # Test helper functions
│   ├── __init__.py
│   └── api.py            # API test helpers
├── api/
│   └── test_core_flow.py # Core flow integration test
├── test_llm_test_mode.py # Test mode guard tests
├── test_migrations.py    # Migration smoke tests
└── test_*.py             # Other tests

frontend/tests/
├── setup.ts              # Vitest setup
├── unit/                 # Unit tests
│   └── composables/
│       ├── useAPI.spec.ts
│       └── sseParser.spec.ts
└── e2e/                  # Playwright E2E tests
    ├── helpers/          # E2E test helpers
    └── core-flow.spec.ts
```

### Troubleshooting Tests

#### `pytest-socket` blocks network access

The backend tests use `pytest-socket` to block network access by default. If a test fails with socket errors:

1. **Check Chroma configuration:** Ensure `AIRBEEPS_CHROMA_SERVER_HOST` is empty (uses embedded mode)
2. **Check for accidental API calls:** Test mode should mock all external calls
3. **Add hosts to allowlist** (if truly needed): Edit `backend/pytest.ini` and add to `--allow-hosts`

```ini
# In pytest.ini
addopts = -v --tb=short --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,localhost,::1,your-host
```

#### Tests fail with database errors

1. **Stale test database:** Delete `backend/testing.db` if it exists
2. **Import order issues:** Ensure environment is set before importing `airbeeps.main`
3. **Use fresh_client fixture:** For tests needing complete isolation

#### E2E tests timeout

1. **Backend not starting:** Check that `uv` is installed and backend dependencies are synced
2. **Frontend not starting:** Check that `pnpm` is installed and dependencies are synced
3. **Increase timeout:** Edit `frontend/playwright.config.ts` and increase `timeout` values

#### Vitest fails with import errors

1. **Run `pnpm postinstall`:** Regenerates Nuxt types
2. **Check setup.ts:** Ensure mocks are properly configured

## Code Quality Standards

### Python

- **Line length:** 88 characters (Black-compatible)
- **Formatter:** Ruff (Black-compatible)
- **Import style:** `isort` compatible via Ruff
- **Type annotations:** Required for public APIs
- **Docstrings:** Google style recommended

### TypeScript/Vue

- **Line length:** 100 characters
- **Formatter:** Prettier with Tailwind CSS plugin
- **Script order:** `<script>`, `<template>`, `<style>`
- **Type annotations:** Required (TypeScript strict mode)
- **Composition API:** Preferred over Options API

## Conventional Commits

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

**Examples:**
```bash
feat(chat): add streaming response support
fix(auth): resolve token refresh race condition
docs: update API documentation
chore(deps): update ruff to v0.9.3
```

## Troubleshooting

### Ruff not finding config

```bash
# Run from backend (uses root config via backend/.ruff.toml)
cd backend
uv run ruff check .
```

### ESLint errors about globals

ESLint is configured with Nuxt auto-imports. If you see errors about undefined globals like `ref`, `computed`, etc., ensure you're running ESLint from the `frontend` directory.

### Pre-commit skipping hooks

Some hooks require dependencies to be installed:

```bash
# Ensure frontend dependencies are installed
cd frontend && pnpm install

# Reinstall pre-commit hooks
pre-commit clean
pre-commit install
```

### Type checking is slow

- **mypy:** Uses project-level caching. First run is slower.
- **vue-tsc:** Nuxt generates types on `nuxt prepare`. Run `pnpm postinstall` if types are stale.

### Windows-specific issues

**Line endings:** The project uses LF line endings. Git should handle this automatically via `.gitattributes`. If you see CRLF warnings:

```powershell
git config core.autocrlf input
```

**Execution policy:** If PowerShell blocks script execution:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Long paths:** Enable long path support if you encounter path length errors:

```powershell
# Run as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```
