# AGENTS.md - Agentic Coding Guidelines for Airbeeps

## Project Overview
Airbeeps is a local-first, self-hosted AI assistant with FastAPI backend and Nuxt 3 frontend.

## Build/Lint/Test Commands

### Full Stack (via Makefile on Linux/macOS)
```bash
make install        # Install all dependencies
make lint           # Lint all code
make format         # Format all code
make fix            # Auto-fix all issues
make typecheck      # Type check all code
make check          # Run all checks (lint + typecheck)
make test           # Run all tests
make pre-commit     # Run pre-commit on all files
```

### Backend (Python)
```bash
cd backend

# Install
uv sync --all-groups

# Lint & Format
uv run ruff check .
uv run ruff check --fix .    # Auto-fix
uv run ruff format .

# Type Check
uv run mypy

# Test - SINGLE TEST
uv run pytest tests/path/test_file.py::test_function_name -v
uv run pytest tests/path/test_file.py -v                 # Single file
uv run pytest -k "test_pattern" -v                       # By pattern
uv run pytest --cov=airbeeps --cov-report=html          # With coverage

# Run dev server
uv run airbeeps dev
```

### Frontend (Nuxt/Vue/TypeScript)
```bash
cd frontend

# Install
pnpm install

# Lint & Format
pnpm lint
pnpm lint:fix                  # Auto-fix
pnpm format

# Type Check
pnpm typecheck

# Test - SINGLE TEST
pnpm test:unit -- test-file-pattern   # Run specific test file
pnpm test:unit:watch                  # Watch mode
pnpm test:unit -- --reporter=verbose  # Verbose output
pnpm test:e2e                         # E2E with Playwright

# Dev server
pnpm dev
```

## Code Style Guidelines

### Python (Backend)
- **Line length:** 88 characters (Black-compatible via Ruff)
- **Formatter:** Ruff (configured in root `pyproject.toml`)
- **Import style:** Use Ruff's isort; first-party package is `airbeeps`
- **Type annotations:** Required for public APIs; use `| None` not `Optional`
- **Docstrings:** Google style recommended
- **Async:** Use `async`/`await` for I/O operations; pytest uses `asyncio_mode = auto`
- **Error handling:** Use FastAPI's HTTPException with appropriate status codes
- **Security:** Tests block network access via `pytest-socket`; use `AIRBEEPS_TEST_MODE=1` for mocks

**Example:**
```python
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from airbeeps.database import get_async_session

router = APIRouter()

class ItemCreate(BaseModel):
    name: str
    value: int | None = None

@router.post("/items", response_model=ItemResponse)
async def create_item(data: ItemCreate) -> ItemResponse:
    """Create a new item."""
    if not data.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name required")
    return ItemResponse(id=1, name=data.name)
```

### TypeScript/Vue (Frontend)
- **Line length:** 100 characters (Prettier)
- **Formatter:** Prettier with Tailwind plugin
- **Script order:** `<script>`, `<template>`, `<style>`
- **Type annotations:** Required (TypeScript strict mode)
- **Composition API:** Preferred over Options API
- **Imports:** Use `@/` alias for project files
- **Vue rules:** PascalCase components, camelCase events, type-based props/emits

**Example:**
```vue
<script setup lang="ts">
import { computed, ref } from "vue";
import MyComponent from "@/components/MyComponent.vue";

interface Props {
  title: string;
  count?: number;
}

const props = withDefaults(defineProps<Props>(), {
  count: 0,
});

const emit = defineEmits<{
  update: [value: number];
}>();

const doubled = computed(() => props.count * 2);
</script>

<template>
  <div>
    <h1>{{ title }}</h1>
    <MyComponent :value="doubled" @update="emit('update', $event)" />
  </div>
</template>
```

### Naming Conventions
- **Python:** `snake_case` for functions/variables, `PascalCase` for classes, `SCREAMING_SNAKE_CASE` for constants
- **TypeScript:** `camelCase` for functions/variables, `PascalCase` for classes/types/interfaces, `SCREAMING_SNAKE_CASE` for constants
- **Vue files:** `PascalCase.vue` for components, `camelCase.ts` for composables
- **Tests:** `test_*.py` (Python), `*.spec.ts` (Vitest), `*.e2e.ts` (Playwright)

### Git & Commits
- Follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description`
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- Examples: `feat(chat): add streaming response`, `fix(auth): resolve token refresh race condition`
- Pre-commit hooks will run automatically; use `pre-commit run --all-files` to check manually

## Testing Guidelines

### Backend Test Mode
Always use `AIRBEEPS_TEST_MODE=1` in tests to mock external API calls:
```python
# Tests automatically use TEST_MODE via conftest.py fixtures
# Fake LLM and embedding clients are used automatically
```

### Network Security
Tests block network access via `pytest-socket`. If you need to allow specific hosts:
```ini
# Add to backend/pytest.ini --allow-hosts list
--allow-hosts=127.0.0.1,localhost,::1,your-host
```

### Database
- Tests use SQLite by default (configured in test fixtures)
- Delete `backend/testing.db` if tests fail due to stale database

## Configuration Files
- `pyproject.toml` (root): Ruff, mypy, pytest, coverage config
- `backend/pyproject.toml`: Python package definition
- `backend/pytest.ini`: Test-specific pytest config
- `frontend/eslint.config.mjs`: ESLint flat config
- `frontend/prettier.config.mjs`: Prettier config
- `.pre-commit-config.yaml`: Pre-commit hooks
- `.editorconfig`: Editor settings (2 spaces, LF endings)

## Common Patterns
- **Backend:** FastAPI routers in `backend/airbeeps/*/api/v1/`, models in `models/`, schemas in `schemas/`
- **Frontend:** Composables in `frontend/app/composables/`, components in `components/`, pages in `pages/`
- **Database:** Use Alembic for migrations; seed data via `uv run scripts/bootstrap.py init`
- **Environment:** All settings use `AIRBEEPS_` prefix; see `.env.docker.example` for reference
