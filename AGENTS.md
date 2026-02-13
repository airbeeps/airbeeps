# AGENTS.md - Airbeeps Agent Playbook

This file is for coding agents working in this repo.
It favors fast, real workflows over generic boilerplate.

## 1) Golden Path (Daily Dev)

These are the two core commands used for regular local development.
They are the same on PowerShell and Linux/macOS shells.

### Backend
```bash
cd backend
uv run fastapi dev --port 8500 airbeeps/main.py
```

### Frontend
```bash
cd frontend
pnpm dev
```

Local URLs:
- Backend API: `http://localhost:8500`
- Frontend: `http://localhost:3000`
- API docs (dev): `http://localhost:8500/docs`

## 2) First-Time Setup (When Needed)

Run once per machine or after dependency resets.

### Backend setup
```bash
cd backend
cp .env.example .env            # Linux/macOS
# Copy-Item .env.example .env   # Windows PowerShell
uv sync --locked
uv run scripts/bootstrap.py init
```

### Frontend setup
```bash
cd frontend
cp .env.example .env            # Linux/macOS
# Copy-Item .env.example .env   # Windows PowerShell
pnpm install
```

Notes:
- First registered user becomes admin.
- Backend env vars must use `AIRBEEPS_` prefix.

## 3) High-Value Repo Map

### Backend (FastAPI)
- Entry point: `backend/airbeeps/main.py`
- App config/env loader: `backend/airbeeps/config.py`
- Domain modules: `backend/airbeeps/<domain>/`
- Typical domain layout:
  - `api/v1/user_router.py`, `api/v1/admin_router.py`, `api/v1/schemas.py`
  - `service.py`
  - `models.py`

Routing model:
- Public + auth routes under `/api/v1/...`
- Authenticated user routes grouped under `/api/v1/...`
- Admin routes grouped under `/api/v1/admin/...`

### Frontend (Nuxt 3 SPA)
- Root app: `frontend/app/app.vue`
- API plugin with auth refresh + timeout defaults: `frontend/app/plugins/api.ts`
- API helper wrapper: `frontend/app/composables/useAPI.ts`
- State stores: `frontend/app/stores/*.ts`
- Pages: `frontend/app/pages/**/*.vue`
- Shared API types: `frontend/app/types/api.d.ts`

API path convention on frontend:
- `$api` already uses base URL `/api`.
- Use paths like `/v1/...` with `$api` and `useAPI`.
- For manual XHR/fetch bypassing `$api`, include full `/api/v1/...`.

## 4) How to Work in This Codebase

### Backend change pattern
1. Update domain `service.py` for business logic.
2. Update `schemas.py` for request/response models.
3. Update `user_router.py` or `admin_router.py`.
4. If creating a new domain, wire routers in `backend/airbeeps/main.py`.
5. Add/update tests in `backend/tests`.

### Frontend change pattern
1. Put API calls in composables or stores (not scattered in views).
2. Reuse `~/types/api` types when possible.
3. Keep page components thin; extract reusable UI/components.
4. Prefer updating existing store/composable flow over adding one-off fetch logic.

### Config-driven UI toggles
If adding a new public config key:
1. Add key to `backend/airbeeps/config/seed.yaml`.
2. Re-seed configs: `cd backend && uv run scripts/bootstrap.py config-init`
3. Add key in frontend type: `frontend/app/types/api.d.ts` (`PublicConfig`).

## 5) Fast Validation Commands (No Makefile Required)

Use targeted checks while iterating.

### Backend
```bash
cd backend
uv run ruff check path/to/file.py
uv run ruff format path/to/file.py
uv run pytest tests/path/test_file.py -v
uv run pytest -k "pattern" -v
```

### Frontend
```bash
cd frontend
pnpm lint -- app/path/to/file.ts
pnpm typecheck
pnpm test:unit -- tests/unit/path.spec.ts
```

Before opening a PR, run broader checks for changed area:
- Backend: `uv run ruff check .` and relevant `pytest` scope.
- Frontend: `pnpm check` and relevant unit/e2e tests.

## 6) Test and Runtime Guardrails

### Backend tests
- Test config is prepared in `backend/tests/conftest.py`.
- Tests force `AIRBEEPS_TEST_MODE=1` (fake LLM/embedding clients).
- `pytest-socket` blocks outbound network by default.
- Embedded Chroma mode uses empty `AIRBEEPS_CHROMA_SERVER_HOST`.

### E2E tests
- Config: `frontend/playwright.config.ts`
- Starts backend and frontend automatically via `webServer`.
- Runs with a single worker intentionally (stateful first-user-admin behavior).

### Browser smoke testing (Chrome MCP)
- If Chrome MCP is available in the current agent session, prefer using it for UI smoke tests.
- Typical quick check: sign in -> open/create chat -> send a message -> confirm response renders.
- Default local login to try:
  - User ID/email: `s@s.com`
  - Password: `s`
- If that login fails (for example on a clean database), create a new user via sign-up.

## 7) Critical Environment Facts

- Backend reads `.env` from `backend/.env` in dev mode.
- Frontend runtime config defaults:
  - `AIRBEEPS_API_BASE_URL=http://localhost:8500/api`
  - `AIRBEEPS_APP_NAME=Airbeeps`
- Backend default secret key is for local dev only; do not use in production.

## 8) Style and Quality Baseline

- Python:
  - Ruff format/lint, line length 88, type hints on public APIs.
  - Async-first for I/O paths.
- Vue/TS:
  - Composition API + strict typing.
  - Prettier + ESLint.
  - Keep script/template/style blocks clean and readable.
- Editor consistency:
  - LF line endings, spaces, `.editorconfig` is source of truth.

## 9) Commit and PR Expectations

- Use Conventional Commit style: `type(scope): message`
- Keep commits focused and reviewable.
- Include tests for behavior changes.
- Mention any env/config/bootstrap requirement in PR description.

## 10) What to Avoid

- Do not add Makefile-only instructions as primary workflow.
- Do not hardcode secrets or commit `.env` files.
- Do not bypass existing API plugin/auth refresh flow without reason.
- Do not introduce broad refactors when a scoped fix is enough.
