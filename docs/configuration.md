# Configuration Management

Airbeeps uses a layered configuration system that supports multiple deployment scenarios (development, Docker, production) with sensible defaults.

## Configuration Priority

Settings are loaded in the following priority order (highest to lowest):

1. **Environment Variables** - `AIRBEEPS_*` prefix (highest priority)
2. **.env File** - Local environment file
3. **Environment-Specific YAML** - `config/settings.{env}.yaml`
4. **Base YAML** - `config/settings.yaml`
5. **Hardcoded Defaults** - In `config.py` (lowest priority)

## Quick Start

### For Development

1. Copy `.env.example` to `.env`:

   ```bash
   cp backend/.env.example backend/.env
   ```

2. Edit `.env` to customize your settings:

   ```bash
   AIRBEEPS_DATABASE_URL="sqlite+aiosqlite:///./data/airbeeps.db"
   AIRBEEPS_SECRET_KEY="your-secret-key-here"
   ```

3. The system automatically loads `config/settings.yaml` + `config/settings.dev.yaml`

### For Docker

1. Set `AIRBEEPS_CONFIG_ENV=docker` in your Docker environment
2. The system loads `config/settings.yaml` + `config/settings.docker.yaml`
3. Override specific settings via Docker environment variables

### For Production

1. Set `AIRBEEPS_CONFIG_ENV=production`
2. Create `config/settings.production.yaml` with production-specific settings
3. Use environment variables for secrets (API keys, passwords, etc.)

## Configuration Structure

### YAML Configuration Files

Located in `backend/airbeeps/config/`:

- **`settings.yaml`** - Base configuration with all defaults
- **`settings.dev.yaml`** - Development overrides (DEBUG logging, local services)
- **`settings.docker.yaml`** - Docker overrides (container hostnames)
- **`settings.production.yaml`** - Production overrides (create as needed)

### Environment Variable Format

Use double underscores (`__`) for nested configuration:

```bash
# Flat config
AIRBEEPS_LOG_LEVEL=DEBUG

# Nested config
AIRBEEPS__VECTOR_STORE__TYPE=qdrant
AIRBEEPS__VECTOR_STORE__QDRANT__URL=http://localhost:6333
AIRBEEPS__RAG__FEATURES__ENABLE_HYBRID_SEARCH=true
```

## Configuration Sections

### Vector Store

Configure your vector database:

```yaml
# YAML (config/settings.yaml)
vector_store:
  type: "qdrant" # qdrant | chromadb | pgvector | milvus
  qdrant:
    url: "http://localhost:6333"
    api_key: ""
    persist_dir: "qdrant"
```

```bash
# Environment Variables
AIRBEEPS__VECTOR_STORE__TYPE=qdrant
AIRBEEPS__VECTOR_STORE__QDRANT__URL=http://localhost:6333
AIRBEEPS__VECTOR_STORE__QDRANT__API_KEY=your-api-key
```

### RAG Settings

Control RAG features and behavior:

```yaml
# YAML
rag:
  features:
    enable_hybrid_search: true
    enable_reranking: true
    enable_hierarchical: true
    enable_semantic_chunking: true
  reranker:
    model: "BAAI/bge-reranker-v2-m3"
    top_n: 5
  query_transform:
    type: "multi_query" # none | hyde | multi_query | step_back
```

```bash
# Environment Variables
AIRBEEPS__RAG__FEATURES__ENABLE_HYBRID_SEARCH=true
AIRBEEPS__RAG__RERANKER__MODEL=BAAI/bge-reranker-v2-m3
AIRBEEPS__RAG__QUERY_TRANSFORM__TYPE=multi_query
```

### Agent Configuration

Configure agentic behavior:

```yaml
# YAML
agent:
  max_iterations: 10
  timeout_seconds: 300
  enable_memory: false
```

```bash
# Environment Variables
AIRBEEPS__AGENT__MAX_ITERATIONS=15
AIRBEEPS__AGENT__ENABLE_MEMORY=true
```

### File Storage

Choose between local or S3 storage:

```yaml
# YAML
file_storage:
  backend: "local" # local | s3
  local:
    storage_root: "files"
  s3:
    endpoint_url: "http://minio:9000"
    access_key_id: "minioadmin"
    secret_access_key: "minioadmin"
    bucket_name: "airbeeps"
```

```bash
# Environment Variables
AIRBEEPS__FILE_STORAGE__BACKEND=s3
AIRBEEPS__FILE_STORAGE__S3__ENDPOINT_URL=http://minio:9000
AIRBEEPS__FILE_STORAGE__S3__ACCESS_KEY_ID=your-key
AIRBEEPS__FILE_STORAGE__S3__SECRET_ACCESS_KEY=your-secret
```

### Model Registry

Control external provider/model discovery lookups (LiteLLM provider list and Hugging Face Hub search):

```yaml
# YAML
ai_registry:
  allow_external: true
```

```bash
# Environment Variables
AIRBEEPS__AI_REGISTRY__ALLOW_EXTERNAL=true
```

## Best Practices

### 1. Secrets Management

**Never commit secrets to YAML files.** Always use environment variables for sensitive data:

```bash
# .env (not committed)
AIRBEEPS_SECRET_KEY=your-secret-key
AIRBEEPS__VECTOR_STORE__QDRANT__API_KEY=your-api-key
AIRBEEPS__FILE_STORAGE__S3__SECRET_ACCESS_KEY=your-secret
AIRBEEPS__EMAIL__PASSWORD=your-password
```

### 2. Environment-Specific Configuration

Use YAML files for environment-specific non-secret settings:

```yaml
# config/settings.dev.yaml
logging:
  level: "DEBUG"

agent:
  max_iterations: 15  # More iterations for testing

# config/settings.production.yaml
logging:
  level: "INFO"

agent:
  max_iterations: 10
```

### 3. Docker Deployments

In Docker Compose:

```yaml
services:
  airbeeps:
    environment:
      - AIRBEEPS_CONFIG_ENV=docker
      - AIRBEEPS_SECRET_KEY=${SECRET_KEY}
      - AIRBEEPS__VECTOR_STORE__TYPE=qdrant
      - AIRBEEPS__VECTOR_STORE__QDRANT__URL=http://qdrant:6333
```

### 4. Wheel Distribution

When distributing as a wheel:

1. Ship YAML files with sensible defaults
2. Users override via `.env` file in their working directory
3. Advanced users can create custom YAML files

## Example Configurations

### Local Development (SQLite + Embedded Qdrant)

```yaml
# config/settings.dev.yaml
vector_store:
  type: "qdrant"
  qdrant:
    url: "" # Empty = embedded mode
    persist_dir: "qdrant"

file_storage:
  backend: "local"
```

### Docker (External Services)

```yaml
# config/settings.docker.yaml
vector_store:
  type: "qdrant"
  qdrant:
    url: "http://qdrant:6333"

file_storage:
  backend: "s3"
  s3:
    endpoint_url: "http://minio:9000"
```

### Production (Cloud Services)

```bash
# .env (production)
AIRBEEPS_CONFIG_ENV=production
AIRBEEPS__VECTOR_STORE__TYPE=qdrant
AIRBEEPS__VECTOR_STORE__QDRANT__URL=https://your-qdrant-cluster.cloud:6333
AIRBEEPS__VECTOR_STORE__QDRANT__API_KEY=your-production-key
AIRBEEPS__FILE_STORAGE__BACKEND=s3
AIRBEEPS__FILE_STORAGE__S3__ENDPOINT_URL=https://s3.amazonaws.com
AIRBEEPS__FILE_STORAGE__S3__ACCESS_KEY_ID=your-aws-key
AIRBEEPS__FILE_STORAGE__S3__SECRET_ACCESS_KEY=your-aws-secret
AIRBEEPS__FILE_STORAGE__S3__BUCKET_NAME=your-production-bucket
```

## Troubleshooting

### Check Loaded Configuration

```python
from airbeeps.config import settings

print(f"Environment: {settings.ENVIRONMENT}")
print(f"Vector Store: {settings.VECTOR_STORE_TYPE}")
print(f"RAG Hybrid Search: {settings.RAG_ENABLE_HYBRID_SEARCH}")
```

### Configuration Not Loading

1. Check `AIRBEEPS_CONFIG_ENV` is set correctly
2. Verify YAML files exist in `backend/airbeeps/config/`
3. Ensure environment variable names use correct prefixes (`AIRBEEPS_` or `AIRBEEPS__`)
4. Remember: env vars take precedence over YAML

### Override Not Working

Priority order matters! If an environment variable is set, it will override YAML:

```bash
# This env var takes precedence over any YAML config
export AIRBEEPS__VECTOR_STORE__TYPE=chromadb

# To use YAML value, unset the env var
unset AIRBEEPS__VECTOR_STORE__TYPE
```

## Migration from Old Config

If upgrading from a previous version:

1. Old environment variables still work (backward compatible)
2. Gradually migrate settings to new YAML structure
3. Old flat variables (e.g., `AIRBEEPS_QDRANT_URL`) map to new nested structure
4. Review `config/settings.yaml` for all available options

## See Also

- [settings.yaml](../backend/airbeeps/config/settings.yaml) - Base configuration with all options
- [.env.example](../backend/.env.example) - Environment variable examples
- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
