# Configuration Guide

Airbeeps reads backend settings from `backend/.env` (overridable by process environment variables) and frontend runtime values from Nuxt runtime config. Environment variables always win over the file.

## Backend Environment

**Important**: All backend environment variables must use the `AIRBEEPS_` prefix. For example:
- `AIRBEEPS_SECRET_KEY`
- `AIRBEEPS_DATABASE_URL`
- `AIRBEEPS_LOG_LEVEL`

The tables below show the **unprefixed key names** for readability. Always add `AIRBEEPS_` when setting them in your environment or `.env` file.

### Core runtime

| Variable       | Description                                     | Default                                  |
| -------------- | ----------------------------------------------- | ---------------------------------------- |
| `PROJECT_NAME` | Display name shown in APIs/logs                 | `Airbeeps`                               |
| `ENVIRONMENT`  | `development` or `production`                   | `development`                            |
| `LOG_LEVEL`    | Logging verbosity                               | `DEBUG`                                  |
| `DATA_ROOT`    | Base folder for DB/files/vectors                | `data`                                   |
| `FRONTEND_URL` | Public URL of the web UI                        | `http://localhost:3000`                  |
| `EXTERNAL_URL` | Public backend URL (OAuth callbacks, links)     | `None`                                   |
| `DATABASE_URL` | DB URL (Postgres recommended, SQLite supported) | `sqlite+aiosqlite:///./data/airbeeps.db` |
| `SECRET_KEY`   | JWT/crypto secret (change in production!)       | `change-me-in-production`                |

### Auth & tokens

| Variable                                                                             | Description               | Default                                                 |
| ------------------------------------------------------------------------------------ | ------------------------- | ------------------------------------------------------- |
| `ACCESS_TOKEN_LIFETIME_SECONDS`                                                      | Access token lifetime     | `1800`                                                  |
| `REFRESH_TOKEN_LIFETIME_SECONDS`                                                     | Refresh token lifetime    | `2592000`                                               |
| `REFRESH_TOKEN_ROTATION_ENABLED`                                                     | Rotate refresh tokens     | `true`                                                  |
| `REFRESH_TOKEN_MAX_PER_USER`                                                         | Max active refresh tokens | `5`                                                     |
| `ACCESS_TOKEN_COOKIE_NAME`, `REFRESH_TOKEN_COOKIE_NAME`, `REFRESH_TOKEN_COOKIE_PATH` | Cookie names/scope        | `access-token`, `refresh-token`, `/api/v1/auth/refresh` |

### Email

| Variable                          | Description          | Default               |
| --------------------------------- | -------------------- | --------------------- |
| `MAIL_ENABLED`                    | Toggle email sending | `false`               |
| `MAIL_SERVER` / `MAIL_PORT`       | SMTP host/port       | ``/`587`              |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | SMTP credentials     | ``                    |
| `MAIL_STARTTLS` / `MAIL_SSL_TLS`  | TLS settings         | `true` / `false`      |
| `MAIL_FROM`                       | From address         | `noreply@example.com` |

### File storage

| Variable                                                      | Description                            | Default                           |
| ------------------------------------------------------------- | -------------------------------------- | --------------------------------- |
| `FILE_STORAGE_BACKEND`                                        | `local` or `s3`                        | `local`                           |
| `LOCAL_STORAGE_ROOT`                                          | Local storage root (under `DATA_ROOT`) | `files`                           |
| `LOCAL_PUBLIC_BASE_URL`                                       | Optional public URL for local files    | ``                                |
| `S3_ENDPOINT_URL` / `S3_EXTERNAL_ENDPOINT_URL`                | S3 internal/external endpoints         | `http://minio:9000` / ``          |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`                   | S3 credentials                         | `minioadmin` / `minioadmin`       |
| `S3_BUCKET_NAME` / `S3_REGION`                                | Bucket + region                        | `test` / `us-east-1`              |
| `S3_USE_SSL` / `S3_ADDRESSING_STYLE` / `S3_SIGNATURE_VERSION` | S3 options                             | `false` / `path` / `s3v4`         |
| `MAX_FILE_SIZE`                                               | Upload size limit (bytes)              | `10485760` (10MB)                 |
| `ALLOWED_IMAGE_EXTENSIONS`                                    | Image whitelist                        | `.jpg,.jpeg,.png,.webp,.gif,.svg` |
| `ALLOWED_DOCUMENT_EXTENSIONS`                                 | Document whitelist                     | `.pdf,.doc,.docx,.txt,.md,.rtf`   |

### Vector store

| Variable                                    | Description                                      | Default   |
| ------------------------------------------- | ------------------------------------------------ | --------- |
| `CHROMA_SERVER_HOST` / `CHROMA_SERVER_PORT` | Chroma server address (empty host = embedded)    | `` / `8500` |
| `CHROMA_PERSIST_DIR`                        | Local Chroma persistence (relative to DATA_ROOT) | `chroma`  |

### RAG retrieval (feature flags, API-level)

- Multi-query: send `multi_query=true` and `multi_query_count` (default 3) to generate deterministic alt queries and merge results.
- Rerank: `rerank_top_k` to re-score top candidates with an embedding-based rerank.
- Hybrid lexical: `hybrid_enabled=true` to fuse lightweight BM25 over recent chunks (cap via `hybrid_corpus_limit`, default 1000).

### Agent & MCP

| Variable                  | Description                            | Default                 |
| ------------------------- | -------------------------------------- | ----------------------- |
| `AGENT_MAX_ITERATIONS`    | Default max agent loops                | `10`                    |
| `AGENT_TIMEOUT_SECONDS`   | Agent timeout                          | `300`                   |
| `AGENT_ENABLE_MEMORY`     | Experimental agent memory toggle       | `false`                 |
| `MCP_ENABLED`             | Enable Model Context Protocol features | `false`                 |
| `MCP_SERVERS_CONFIG_PATH` | Path to MCP server configs             | `/app/mcp_servers.json` |

### OAuth helpers

| Variable                           | Description                                   | Default             |
| ---------------------------------- | --------------------------------------------- | ------------------- |
| `OAUTH_CREATE_USER_WITHOUT_EMAIL`  | Allow user creation when provider omits email | `true`              |
| `OAUTH_REQUIRE_EMAIL_VERIFICATION` | Force verification for OAuth accounts         | `false`             |
| `OAUTH_EMAIL_DOMAIN`               | Domain for generated emails                   | `oauth.example.com` |

## Frontend Environment

Set via process env or `.env` for Nuxt:

- `AIRBEEPS_API_BASE_URL`: Backend API base for dev proxy (default `http://localhost:8500/api`).
- `AIRBEEPS_APP_NAME`: Title shown in the browser (default `Airbeeps`).
- `AIRBEEPS_ENABLE_OAUTH_PROVIDERS`: Toggle OAuth buttons (default `true`).

## System Configuration (DB-backed)

- Stored in the `system_configs` table, cached in-memory, and exposed through the Admin UI (`/admin/system-config`).
- Used for runtime feature toggles such as `allow_user_create_assistants` and `conversation_title_model_id` (model used for title generation).
- When new keys are added, run `uv run scripts/bootstrap.py config-init` to backfill defaults.

## Seed Data & Bootstrap

- Default seed file: `backend/airbeeps/config/seed.yaml` (system config defaults). Override via `AIRBEEPS_SEED_FILE`.
- `uv run scripts/bootstrap.py init` runs migrations and seeds safe defaults. Airbeeps does **not** ship a default admin credential — the first registered user becomes an admin.

## Example Configuration

### Minimal Development Setup

Create `backend/.env`:

```bash
# Generate a secure secret
AIRBEEPS_SECRET_KEY=your-secret-key-here

# Optional: override defaults
AIRBEEPS_LOG_LEVEL=DEBUG
AIRBEEPS_DATABASE_URL=sqlite+aiosqlite:///./data/airbeeps.db
AIRBEEPS_CHROMA_PERSIST_DIR=chroma
```

### Production Recommendations

```bash
# Security
AIRBEEPS_SECRET_KEY=<strong-random-key>
AIRBEEPS_ENVIRONMENT=production

# Database (use PostgreSQL)
AIRBEEPS_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/airbeeps

# External access
AIRBEEPS_EXTERNAL_URL=https://your-domain.com
AIRBEEPS_FRONTEND_URL=https://your-domain.com

# Email
AIRBEEPS_MAIL_ENABLED=true
AIRBEEPS_MAIL_SERVER=smtp.gmail.com
AIRBEEPS_MAIL_PORT=587
AIRBEEPS_MAIL_USERNAME=your-email@gmail.com
AIRBEEPS_MAIL_PASSWORD=app-specific-password
AIRBEEPS_MAIL_FROM=noreply@your-domain.com
```

See [SECURITY.md](../SECURITY.md) for additional production hardening recommendations.
