# Docker Deployment

This setup runs Airbeeps as a single production container with Postgres, Qdrant, and MinIO.

## Prerequisites

- Docker Engine + Docker Compose (v2)
- A local `.env.docker` file (see below)

## Quick Start

1. Create your environment file:
   ```bash
   cp .env.docker.example .env.docker
   ```

2. Set a secure secret key and credentials in `.env.docker`:
   ```bash
   AIRBEEPS_SECRET_KEY=replace-with-a-long-random-string
   POSTGRES_PASSWORD=replace-with-a-strong-password
   MINIO_ROOT_USER=replace-with-a-strong-user
   MINIO_ROOT_PASSWORD=replace-with-a-strong-password
   MINIO_BUCKET=airbeeps
   ```

3. Start the stack:
   ```bash
   docker compose --env-file .env.docker up --build
   ```

4. Open the app:
   - App: http://localhost:8080
   - MinIO Console: http://localhost:9001

The backend runs migrations and seeds defaults automatically on first boot.

## Services

- **airbeeps**: API + bundled frontend on port `8080`
- **postgres**: primary database
- **qdrant**: vector store
- **minio**: S3-compatible storage (bucket created at startup)

## Volumes

- `airbeeps-data`: application data (files, qdrant/chroma data paths)
- `postgres-data`: Postgres data
- `qdrant-data`: Qdrant storage
- `minio-data`: MinIO object storage

## Configuration Notes

- The stack sets `AIRBEEPS_CONFIG_ENV=docker`, which loads
  `backend/airbeeps/config/settings.docker.yaml`.
- The frontend and API are served from the same container and port (`8080`).
- MinIO bucket is created at startup and set to public read for file URLs.

## Optional: Use PGVector for embeddings

If you want to store vectors in Postgres instead of Qdrant, set:

```bash
AIRBEEPS_VECTOR_STORE_TYPE=pgvector
AIRBEEPS_PGVECTOR_CONNECTION_STRING=postgresql://airbeeps:${POSTGRES_PASSWORD}@postgres:5432/airbeeps
```

## Stopping

```bash
docker compose down
```

To delete volumes (destroys data):

```bash
docker compose down -v
```
