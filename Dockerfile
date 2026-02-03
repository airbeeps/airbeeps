# syntax=docker/dockerfile:1.7

FROM node:20-slim AS frontend-build
WORKDIR /app/frontend

ENV NODE_ENV=production \
    NUXT_TELEMETRY_DISABLED=1 \
    AIRBEEPS_API_BASE_URL=/api \
    AIRBEEPS_APP_NAME=Airbeeps

RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run generate

FROM python:3.13-slim AS backend
WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libmagic1 \
        libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY backend/ /app/backend/
RUN uv sync --locked --no-dev

COPY --from=frontend-build /app/frontend/.output/public /app/backend/airbeeps/static

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin airbeeps \
    && chown -R airbeeps:airbeeps /app

ENV PATH="/app/backend/.venv/bin:$PATH"

USER airbeeps
EXPOSE 8080

CMD ["airbeeps", "run", "--host", "0.0.0.0", "--port", "8080"]
