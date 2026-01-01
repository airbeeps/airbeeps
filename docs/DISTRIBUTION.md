# Distribution Guide

This document explains how to build and distribute Airbeeps as a PyPI package.

## Overview

Airbeeps can be distributed as a Python wheel that users can install with:

```bash
uv pip install airbeeps
uv run airbeeps run
```

## Build Process

### Prerequisites

1. **Python 3.13+** with `uv` installed
2. **Node.js 18+** with `pnpm` installed
3. **Build tools**: `hatchling` (installed automatically)

### Building the Wheel

We provide a build script that automates the entire process:

```bash
uv run scripts/build_wheel.py
```

To override the version number (e.g. for a specific release or test build), use the `--version` flag:

```bash
uv run scripts/build_wheel.py --version 0.1.0
```

This script will:

1. Build the Nuxt frontend (`pnpm run generate`)
2. Copy static assets to `backend/airbeeps/static/`
3. Build the Python wheel with `uv build`
4. Output the wheel to `backend/dist/`
5. **Clean up temporary files** (removes static/ and .output/)

**Important**: The build script automatically cleans up generated files after building the wheel. This prevents cluttering your repository with build artifacts. The static files are only needed during the build process - they're bundled into the wheel and then removed.

If you need to manually clean up build artifacts:

```bash
uv run scripts/clean_build.py
```

### Manual Build Steps

If you prefer to build manually:

```bash
# 1. Build frontend
cd frontend
pnpm install
pnpm run generate

# 2. Copy static files
mkdir -p ../backend/airbeeps/static
cp -r .output/public/* ../backend/airbeeps/static/

# 3. Build wheel
cd ../backend
uv build
```

## Package Structure

The built wheel includes:

```
airbeeps/
├── airbeeps/              # Main package
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── cli.py               # CLI entry point
│   ├── config.py            # Configuration
│   ├── migrations.py        # Programmatic Alembic
│   ├── alembic/             # Database migrations (namespaced)
│   │   ├── env.py
│   │   └── versions/
│   ├── static/              # Bundled frontend (added at build time)
│   ├── templates/           # Email templates
│   └── [other modules]
└── pyproject.toml           # Package metadata
```

## Installation Modes

### Development Mode

For local development, run frontend and backend separately:

```bash
# Terminal 1 - Backend
cd backend
uv run fastapi dev airbeeps/main.py

# Terminal 2 - Frontend
cd frontend
pnpm dev
```

The backend serves API at `http://localhost:8500` and frontend runs at `http://localhost:3000`.

### Installed Mode

When installed via pip:

```bash
pip install airbeeps
airbeeps run
```

The application:

- Uses `~/.local/share/airbeeps` for data (Linux/Mac) or `%APPDATA%\airbeeps` (Windows)
- Runs migrations automatically on first start
- Serves both API and frontend from a single port (8080)
- Uses embedded ChromaDB (no external services needed)

## Configuration Differences

### Development

- `DATA_ROOT`: Defaults to `./data` in project root
- `.env`: Read from `backend/.env`
- Frontend: Separate dev server with HMR
- Database: `./data/airbeeps.db`

### Production (Installed)

- `DATA_ROOT`: User data directory (`~/.local/share/airbeeps`)
- `.env`: Read from current directory or set via environment
- Frontend: Bundled static files served by FastAPI
- Database: `~/.local/share/airbeeps/airbeeps.db`

## Testing the Build

### Local Installation

Test the wheel before publishing:

```bash
# Create a test environment
uv venv test-env
source test-env/bin/activate  # or test-env\Scripts\activate on Windows

# Install the wheel
uv pip install backend/dist/airbeeps-0.1.0-py3-none-any.whl

# Test it
airbeeps run
```

### Verify Installation

```bash
airbeeps info      # Check configuration
airbeeps version   # Check version
airbeeps --help    # See all commands
```

## Publishing to PyPI

### Prerequisites

1. PyPI account and API token
2. `uv` installed (already required for building)

### Upload to Test PyPI

```bash
cd backend
uv publish --publish-url https://test.pypi.org/legacy/ dist/*
```

### Upload to PyPI

```bash
cd backend
uv publish dist/*
```

### Using GitHub Actions (Recommended)

See the `.github/workflows/publish-pypi.yml` workflow in the repository. To use it:

1. Add your PyPI API token as a repository secret named `PYPI_API_TOKEN`
2. Create a new release on GitHub
3. The workflow will automatically build and publish to PyPI

The workflow handles:
- Building the frontend with Node.js and pnpm
- Building the Python wheel with uv
- Publishing to PyPI using uv

## Version Management

Airbeeps uses **dynamic versioning** based on Git tags. You do NOT need to manually update version numbers in files.

### Creating a Release

1.  **Tag the commit**:
    ```bash
    git tag v0.2.0
    git push origin v0.2.0
    ```

2.  **Build**:
    The build script will automatically detect the tag `v0.2.0` and build `airbeeps-0.2.0-py3-none-any.whl`.

### Development Builds

If you build without a tag, the version will look like `0.1.0.post4+g8a2b3c` (distance from last tag + commit hash). This ensures every dev build is unique.

### Frontend Version

The build script automatically injects the current Git version into the frontend as `NUXT_PUBLIC_APP_VERSION`.

## Troubleshooting

### Frontend not showing

- Ensure `backend/airbeeps/static/index.html` exists in the wheel
- Check build script ran successfully
- Verify `[tool.hatch.build.targets.wheel.force-include]` in pyproject.toml

### Migrations failing

- Ensure `airbeeps/alembic/` directory is included in the wheel
- Check `[tool.hatch.build.targets.wheel.force-include]` includes `airbeeps/alembic`
- Verify `migrations.py` can locate the alembic directory

### Import errors

- Ensure all imports use `airbeeps.` not `src.`
- Check `backend/airbeeps/alembic/env.py` imports from `airbeeps`

## Dependencies

The wheel includes all Python dependencies, but users need:

- **System**: Python 3.13+, SQLite (usually included)
- **Optional**: PostgreSQL/MySQL for production databases
- **Optional**: External ChromaDB server (embedded mode works by default)

## Size Optimization

The wheel can be large due to ML dependencies. To reduce size:

1. Make heavy dependencies optional:

   ```toml
   [project.optional-dependencies]
   embeddings = ["sentence-transformers>=3.0.1"]
   ```

2. Use lighter alternatives where possible

3. Consider separate wheels for different use cases

## Support

For issues with the build process, check:

- Build script output
- `backend/dist/` for generated files
- Package contents: `unzip -l backend/dist/*.whl`
