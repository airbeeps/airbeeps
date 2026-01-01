# Quickstart

## Requirements

- Python 3.13+ with [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ (18+ minimum) with [`pnpm`](https://pnpm.io/)

## Local setup

1. **Create backend configuration**:
   ```bash
   cd backend
   cp .env.example .env          # Copy example config and edit as needed
   uv sync --locked              # Install dependencies
   uv run scripts/bootstrap.py init  # Initialize database
   uv run fastapi dev --port 8500 airbeeps/main.py  # Start backend (http://localhost:8500)
   ```

   See [configuration.md](configuration.md) for all available options. Remember all backend env vars need the `AIRBEEPS_` prefix.

   **Generate a secret key and write it to .env:**

   Linux/macOS:
   ```bash
   echo "AIRBEEPS_SECRET_KEY=$(openssl rand -hex 32)" >> .env
   ```

   Windows (PowerShell):
   ```powershell
   "AIRBEEPS_SECRET_KEY=$(openssl rand -hex 32)" | Out-File .env -Append
   ```



2. **Install backend dependencies**:
   ```bash
   uv sync --locked
   ```

3. **Initialize database and seed defaults**:
   ```bash
   uv run scripts/bootstrap.py init
   ```

   Options:
   - `--skip-migrate` — Skip database migrations
   - `--skip-seed` — Skip seeding default data
   - `--seed-file path/to/custom.yaml` — Use custom seed file

   If you add new system config keys later, reapply defaults:
   ```bash
   uv run scripts/bootstrap.py config-init
   ```

4. **Start backend**:
   ```bash
   uv run fastapi dev airbeeps/main.py
   ```
   Backend runs at `http://localhost:8500`

5. **Start frontend** (in another terminal):
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```
   Frontend runs at `http://localhost:3000`

6. **First user**: Open `http://localhost:3000` and sign up - the first registered user automatically becomes an admin.

## Admin CLI Reference

All commands run from `backend/` directory:

### Primary Command

- `uv run scripts/bootstrap.py init` — **Full initialization** (migrations + seeding). Use this for setup and updates.

### Advanced Commands

**Database:**
- `uv run scripts/bootstrap.py migrate` — Migrations only (no seeding)
- `uv run scripts/bootstrap.py config-init` — Reseed configs from YAML (useful when adding new settings)
- `uv run scripts/bootstrap.py reset-db --force` — ⚠️ Drop all data (dev only)

**User Management:**
- `uv run scripts/bootstrap.py superuser --email user@example.com` — Create admin manually
- `uv run scripts/bootstrap.py list-superusers` — List all admins

## Next Steps

- Configure LLM providers in the Admin UI (`/admin/model-providers`)
- Create your first assistant (`/admin/assistants`)
- Upload documents to a knowledge base (`/admin/kbs`)
- Start chatting!

For production deployment, see [configuration.md](configuration.md) for security hardening and [SECURITY.md](../SECURITY.md) for best practices.
