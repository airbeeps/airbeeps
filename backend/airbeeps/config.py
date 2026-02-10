import os
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import AnyHttpUrl, EmailStr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from platformdirs import user_data_dir

    HAS_PLATFORMDIRS = True
except ImportError:
    HAS_PLATFORMDIRS = False


# Determine if we're running from an installed package or development
def _is_installed_package() -> bool:
    """Check if running from installed package (site-packages) vs dev environment"""
    return "site-packages" in __file__ or "dist-packages" in __file__


# Set base directories based on installation mode
if _is_installed_package():
    # Installed mode: use user data directory
    if HAS_PLATFORMDIRS:
        # Pass False as appauthor to avoid airbeeps/airbeeps redundancy on Windows
        BASE_DIR = Path(user_data_dir("airbeeps", False))
    else:
        BASE_DIR = Path.home() / ".local" / "share" / "airbeeps"
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_ROOT = BASE_DIR
    # Templates are in the package
    TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
    CONFIG_DIR = Path(__file__).resolve().parent / "config"
else:
    # Development mode: use project structure
    BASE_DIR = Path(__file__).resolve().parent.parent
    PROJECT_ROOT = BASE_DIR.parent
    TEMPLATE_DIR = BASE_DIR / "templates"
    CONFIG_DIR = Path(__file__).resolve().parent / "config"


class EnvironmentType(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_config() -> dict[str, Any]:
    """
    Load and merge YAML configuration files.

    Priority (highest to lowest):
    1. Environment-specific config (settings.{env}.yaml)
    2. Base config (settings.yaml)

    Environment is determined by AIRBEEPS_CONFIG_ENV or AIRBEEPS_ENVIRONMENT.
    """
    # Determine environment
    config_env = os.getenv("AIRBEEPS_CONFIG_ENV") or os.getenv(
        "AIRBEEPS_ENVIRONMENT", "development"
    )

    # Load base config
    base_config = {}
    base_config_path = CONFIG_DIR / "settings.yaml"
    if base_config_path.exists():
        with open(base_config_path, encoding="utf-8") as f:
            base_config = yaml.safe_load(f) or {}

    # Load environment-specific config
    env_config = {}
    env_config_path = CONFIG_DIR / f"settings.{config_env.lower()}.yaml"
    if env_config_path.exists():
        with open(env_config_path, encoding="utf-8") as f:
            env_config = yaml.safe_load(f) or {}

    # Merge configs
    merged_config = _deep_merge(base_config, env_config)

    return merged_config


def _flatten_dict(d: dict, parent_key: str = "", sep: str = "__") -> dict:
    """
    Flatten nested dictionary for environment variable override compatibility.

    Example: {"vector_store": {"type": "qdrant"}} -> {"VECTOR_STORE__TYPE": "qdrant"}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key.upper(), v))
    return dict(items)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use backend-level .env regardless of current working directory
        # In installed mode, look for .env in user data dir or current dir
        env_file=str((BASE_DIR / ".env").resolve())
        if not _is_installed_package()
        else str((Path.cwd() / ".env").resolve()),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        # All environment variables should be prefixed with AIRBEEPS_
        # e.g., AIRBEEPS_DATABASE_URL, AIRBEEPS_TEST_MODE, etc.
        env_prefix="AIRBEEPS_",
        env_nested_delimiter="__",  # Support nested overrides: AIRBEEPS__VECTOR_STORE__TYPE
    )
    PROJECT_NAME: str = "Airbeeps"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Environment
    ENVIRONMENT: EnvironmentType = EnvironmentType.DEVELOPMENT
    SHOW_DOCS_ENVIRONMENT: ClassVar[list[EnvironmentType]] = [
        EnvironmentType.DEVELOPMENT
    ]

    # Data root (base directory for local data: DB, files, chroma)
    DATA_ROOT: str = "data"

    FRONTEND_URL: AnyHttpUrl = "http://localhost:3000"

    EXTERNAL_URL: AnyHttpUrl | None = (
        None  # External API URL, used for OAuth callbacks etc.
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/airbeeps.db"

    # Auth
    SECRET_KEY: str = "change-me-in-production"  # Default for easy first run

    # Token Configuration
    ACCESS_TOKEN_LIFETIME_SECONDS: int = 60 * 30  # 30 minutes
    REFRESH_TOKEN_LIFETIME_SECONDS: int = 60 * 60 * 24 * 30  # 30 days
    REFRESH_TOKEN_ROTATION_ENABLED: bool = True  # Token rotation for better security
    REFRESH_TOKEN_MAX_PER_USER: int = 5  # Max active refresh tokens per user

    # Cookie Configuration (Security Enhancement)
    ACCESS_TOKEN_COOKIE_NAME: str = "access-token"
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh-token"
    REFRESH_TOKEN_COOKIE_PATH: str = (
        "/api/v1/auth/refresh"  # Limit refresh token to refresh endpoint only
    )

    # Account Lockout Configuration (Brute Force Protection)
    ACCOUNT_LOCKOUT_MAX_ATTEMPTS: int = 5  # Max failed attempts before lockout
    ACCOUNT_LOCKOUT_DURATION_MINUTES: int = 15  # Lockout duration in minutes

    # Email Server
    MAIL_ENABLED: bool = False
    MAIL_SERVER: str = ""
    MAIL_PORT: int = 587
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: SecretStr = SecretStr("")
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    MAIL_FROM: EmailStr = "noreply@example.com"

    # File Storage
    FILE_STORAGE_BACKEND: str = "local"  # Options: s3, local
    # Stored under DATA_ROOT; keep default simple to avoid data/data nesting
    LOCAL_STORAGE_ROOT: str = "files"
    LOCAL_PUBLIC_BASE_URL: str = ""  # Optional base URL if serving files publicly

    # File Storage (S3 Configuration)
    S3_ENDPOINT_URL: str = "http://minio:9000"  # Set in environment
    S3_EXTERNAL_ENDPOINT_URL: str = (
        ""  # External URL for accessing S3, if different from internal
    )
    S3_ACCESS_KEY_ID: str = (
        "minioadmin"  # Default for dev; override via AIRBEEPS_S3_ACCESS_KEY_ID
    )
    S3_SECRET_ACCESS_KEY: SecretStr = SecretStr(
        "minioadmin"
    )  # Default for dev; override via AIRBEEPS_S3_SECRET_ACCESS_KEY
    S3_BUCKET_NAME: str = "test"  # Default bucket name
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False
    S3_ADDRESSING_STYLE: str = "path"  # Use path-style for MinIO compatibility
    S3_SIGNATURE_VERSION: str = "s3v4"  # Use signature version 4

    # File Upload Settings
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB default
    ALLOWED_IMAGE_EXTENSIONS: list[str] = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".svg",
    ]
    ALLOWED_DOCUMENT_EXTENSIONS: list[str] = [
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".md",
        ".rtf",
    ]

    # OAuth Settings
    OAUTH_CREATE_USER_WITHOUT_EMAIL: bool = (
        True  # Whether to create new user when email is missing
    )
    OAUTH_REQUIRE_EMAIL_VERIFICATION: bool = (
        False  # Whether OAuth users require email verification
    )
    OAUTH_EMAIL_DOMAIN: str = (
        "oauth.example.com"  # Domain used when generating virtual emails
    )

    # Vector Store Configuration
    VECTOR_STORE_TYPE: str = "qdrant"  # qdrant | chromadb | pgvector | milvus

    # Qdrant Configuration
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_PREFER_GRPC: bool = True
    QDRANT_PERSIST_DIR: str = "qdrant"  # Relative to DATA_ROOT (for local mode)

    # ChromaDB Configuration (legacy, kept for migration)
    CHROMA_SERVER_HOST: str = ""  # Chroma service address (empty = embedded mode)
    CHROMA_SERVER_PORT: int = 8500
    CHROMA_PERSIST_DIR: str = "chroma"  # Relative to DATA_ROOT

    # Milvus Configuration
    MILVUS_URI: str = "http://localhost:19530"
    MILVUS_TOKEN: str = ""
    MILVUS_DB_NAME: str = "default"

    # PGVector Configuration (uses DATABASE_URL by default)
    PGVECTOR_CONNECTION_STRING: str = ""  # Override if different from main DB
    PGVECTOR_SCHEMA: str = "public"

    # RAG Feature Flags
    RAG_ENABLE_HYBRID_SEARCH: bool = True
    RAG_ENABLE_RERANKING: bool = True
    RAG_RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RAG_RERANKER_TOP_N: int = 5
    RAG_ENABLE_HIERARCHICAL: bool = True
    RAG_ENABLE_SEMANTIC_CHUNKING: bool = True
    RAG_QUERY_TRANSFORM_TYPE: str = (
        "multi_query"  # none | hyde | multi_query | step_back
    )

    # Semantic Chunking Settings
    RAG_SEMANTIC_BREAKPOINT_THRESHOLD: int = (
        95  # Percentile threshold for semantic splits
    )
    RAG_SEMANTIC_BUFFER_SIZE: int = 1  # Sentences to buffer for context

    # Hierarchical Chunking Settings
    RAG_HIERARCHICAL_CHUNK_SIZES: list[int] = [
        2048,
        512,
        128,
    ]  # parent -> child -> leaf

    # Hybrid Search Settings
    RAG_HYBRID_ALPHA: float = 0.5  # Weight for dense vs sparse (0=sparse, 1=dense)
    RAG_BM25_K1: float = 1.5
    RAG_BM25_B: float = 0.75

    # Agent Configuration
    AGENT_MAX_ITERATIONS: int = 10  # Agent max iterations
    AGENT_TIMEOUT_SECONDS: int = 300  # Agent execution timeout (seconds)
    AGENT_ENABLE_MEMORY: bool = False  # Whether to enable Agent memory

    # Memory System Configuration
    MEMORY_ENCRYPTION_KEY: str = ""  # Fernet encryption key for memory content
    MEMORY_DEFAULT_TTL_DAYS: int = 90  # Default retention period in days
    MEMORY_MAX_PER_USER: int = 1000  # Maximum memories per user
    MEMORY_REQUIRE_CONSENT: bool = True  # Whether to require user consent
    MEMORY_AUTO_PRUNE_THRESHOLD: float = (
        0.3  # Auto-prune memories below this importance
    )

    # MCP Configuration
    MCP_ENABLED: bool = False  # Whether to enable MCP features
    MCP_SERVERS_CONFIG_PATH: str = (
        "/app/mcp_servers.json"  # MCP servers config file path
    )

    # Observability / Tracing Configuration
    TRACING_ENABLED: bool = True  # Whether to enable tracing
    TRACING_BACKEND: str = "local"  # local | otlp | jaeger | console | none
    TRACING_ENDPOINT: str = ""  # OTLP/Jaeger endpoint URL
    TRACING_SAMPLE_RATE: float = 1.0  # Sampling rate (0.0 - 1.0)
    TRACING_REDACT_PII: bool = True  # Redact PII from traces (GDPR)
    TRACING_ADMIN_ONLY: bool = True  # Only admins can view traces
    TRACING_RETENTION_DAYS: int = 30  # Days to keep traces (for local storage)

    # AI Registry Configuration
    AI_REGISTRY_ALLOW_EXTERNAL: bool = True  # Allow external registry lookups

    # Test Mode Configuration
    # When enabled, all external LLM/embedding calls are replaced with deterministic fakes.
    # This ensures tests never hit real APIs even if keys are present in the environment.
    TEST_MODE: bool = False  # Set via AIRBEEPS_TEST_MODE=1 in environment

    # API Documentation
    DOCS_ENABLED: bool = False  # Enable API docs in production (disabled by default)

    # =========================================================================
    # Redis Cache Configuration (Optional)
    # =========================================================================
    # Redis is optional. When disabled, in-memory caching is used.
    # For pip installations, Redis is disabled by default.
    # For Docker deployments, Redis is enabled by default.
    REDIS_ENABLED: bool = False  # Set via AIRBEEPS_REDIS_ENABLED=true
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""
    REDIS_SSL: bool = False
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    # Cache TTLs (in seconds)
    CACHE_TTL_DEFAULT: int = 3600  # 1 hour
    CACHE_TTL_CONVERSATIONS: int = 1800  # 30 minutes
    CACHE_TTL_EMBEDDINGS: int = 86400  # 24 hours
    CACHE_TTL_MODEL_RESPONSES: int = 3600  # 1 hour
    CACHE_TTL_RAG_RESULTS: int = 1800  # 30 minutes
    CACHE_TTL_MODEL_DISCOVERY: int = 300  # 5 minutes

    # =========================================================================
    # Celery Task Queue Configuration (Optional)
    # =========================================================================
    # Celery is optional. When disabled, in-process async tasks are used.
    # For pip installations, Celery is disabled by default.
    # For Docker deployments, Celery is enabled by default.
    CELERY_ENABLED: bool = False  # Set via AIRBEEPS_CELERY_ENABLED=true
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list[str] = ["json"]
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 3600  # 1 hour max per task
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1  # Fair scheduling

    # =========================================================================
    # S3 Storage Improvements
    # =========================================================================
    S3_AUTO_CREATE_BUCKET: bool = True  # Auto-create bucket on startup
    S3_RETRY_MAX_ATTEMPTS: int = 3  # Max retry attempts for S3 operations
    S3_RETRY_BACKOFF_FACTOR: float = 0.5  # Exponential backoff factor

    def model_post_init(self, __context: Any) -> None:
        """
        Post-initialization hook to load and merge YAML configuration.

        Priority order (highest to lowest):
        1. Environment variables (AIRBEEPS_*)
        2. .env file
        3. Environment-specific YAML (settings.{env}.yaml)
        4. Base YAML (settings.yaml)
        5. Hardcoded defaults

        This method is called AFTER Pydantic has loaded env vars and .env file,
        so we only apply YAML values if the field hasn't been explicitly set.
        """
        super().model_post_init(__context)

        # Load YAML config
        yaml_config = _load_yaml_config()
        if not yaml_config:
            return

        # Flatten YAML config to match Pydantic field names
        flat_config = _flatten_dict(yaml_config)

        # Map YAML keys to Settings field names
        yaml_to_field_mapping = {
            "VECTOR_STORE__TYPE": "VECTOR_STORE_TYPE",
            "VECTOR_STORE__QDRANT__URL": "QDRANT_URL",
            "VECTOR_STORE__QDRANT__API_KEY": "QDRANT_API_KEY",
            "VECTOR_STORE__QDRANT__PREFER_GRPC": "QDRANT_PREFER_GRPC",
            "VECTOR_STORE__QDRANT__PERSIST_DIR": "QDRANT_PERSIST_DIR",
            "VECTOR_STORE__CHROMA__SERVER_HOST": "CHROMA_SERVER_HOST",
            "VECTOR_STORE__CHROMA__SERVER_PORT": "CHROMA_SERVER_PORT",
            "VECTOR_STORE__CHROMA__PERSIST_DIR": "CHROMA_PERSIST_DIR",
            "VECTOR_STORE__MILVUS__URI": "MILVUS_URI",
            "VECTOR_STORE__MILVUS__TOKEN": "MILVUS_TOKEN",
            "VECTOR_STORE__MILVUS__DB_NAME": "MILVUS_DB_NAME",
            "VECTOR_STORE__PGVECTOR__CONNECTION_STRING": "PGVECTOR_CONNECTION_STRING",
            "VECTOR_STORE__PGVECTOR__SCHEMA": "PGVECTOR_SCHEMA",
            "RAG__FEATURES__ENABLE_HYBRID_SEARCH": "RAG_ENABLE_HYBRID_SEARCH",
            "RAG__FEATURES__ENABLE_RERANKING": "RAG_ENABLE_RERANKING",
            "RAG__FEATURES__ENABLE_HIERARCHICAL": "RAG_ENABLE_HIERARCHICAL",
            "RAG__FEATURES__ENABLE_SEMANTIC_CHUNKING": "RAG_ENABLE_SEMANTIC_CHUNKING",
            "RAG__RERANKER__MODEL": "RAG_RERANKER_MODEL",
            "RAG__RERANKER__TOP_N": "RAG_RERANKER_TOP_N",
            "RAG__QUERY_TRANSFORM__TYPE": "RAG_QUERY_TRANSFORM_TYPE",
            "RAG__SEMANTIC_CHUNKING__BREAKPOINT_THRESHOLD": "RAG_SEMANTIC_BREAKPOINT_THRESHOLD",
            "RAG__SEMANTIC_CHUNKING__BUFFER_SIZE": "RAG_SEMANTIC_BUFFER_SIZE",
            "RAG__HIERARCHICAL_CHUNKING__CHUNK_SIZES": "RAG_HIERARCHICAL_CHUNK_SIZES",
            "RAG__HYBRID_SEARCH__ALPHA": "RAG_HYBRID_ALPHA",
            "RAG__HYBRID_SEARCH__BM25_K1": "RAG_BM25_K1",
            "RAG__HYBRID_SEARCH__BM25_B": "RAG_BM25_B",
            "AGENT__MAX_ITERATIONS": "AGENT_MAX_ITERATIONS",
            "AGENT__TIMEOUT_SECONDS": "AGENT_TIMEOUT_SECONDS",
            "AGENT__ENABLE_MEMORY": "AGENT_ENABLE_MEMORY",
            "MCP__ENABLED": "MCP_ENABLED",
            "MCP__SERVERS_CONFIG_PATH": "MCP_SERVERS_CONFIG_PATH",
            "AI_REGISTRY__ALLOW_EXTERNAL": "AI_REGISTRY_ALLOW_EXTERNAL",
            "FILE_STORAGE__BACKEND": "FILE_STORAGE_BACKEND",
            "FILE_STORAGE__LOCAL__STORAGE_ROOT": "LOCAL_STORAGE_ROOT",
            "FILE_STORAGE__LOCAL__PUBLIC_BASE_URL": "LOCAL_PUBLIC_BASE_URL",
            "FILE_STORAGE__S3__ENDPOINT_URL": "S3_ENDPOINT_URL",
            "FILE_STORAGE__S3__EXTERNAL_ENDPOINT_URL": "S3_EXTERNAL_ENDPOINT_URL",
            "FILE_STORAGE__S3__ACCESS_KEY_ID": "S3_ACCESS_KEY_ID",
            "FILE_STORAGE__S3__SECRET_ACCESS_KEY": "S3_SECRET_ACCESS_KEY",
            "FILE_STORAGE__S3__BUCKET_NAME": "S3_BUCKET_NAME",
            "FILE_STORAGE__S3__REGION": "S3_REGION",
            "FILE_STORAGE__S3__USE_SSL": "S3_USE_SSL",
            "FILE_STORAGE__S3__ADDRESSING_STYLE": "S3_ADDRESSING_STYLE",
            "FILE_STORAGE__S3__SIGNATURE_VERSION": "S3_SIGNATURE_VERSION",
            "FILE_UPLOAD__MAX_FILE_SIZE": "MAX_FILE_SIZE",
            "FILE_UPLOAD__ALLOWED_IMAGE_EXTENSIONS": "ALLOWED_IMAGE_EXTENSIONS",
            "FILE_UPLOAD__ALLOWED_DOCUMENT_EXTENSIONS": "ALLOWED_DOCUMENT_EXTENSIONS",
            "AUTH__ACCESS_TOKEN_LIFETIME_SECONDS": "ACCESS_TOKEN_LIFETIME_SECONDS",
            "AUTH__REFRESH_TOKEN_LIFETIME_SECONDS": "REFRESH_TOKEN_LIFETIME_SECONDS",
            "AUTH__REFRESH_TOKEN_ROTATION_ENABLED": "REFRESH_TOKEN_ROTATION_ENABLED",
            "AUTH__REFRESH_TOKEN_MAX_PER_USER": "REFRESH_TOKEN_MAX_PER_USER",
            "AUTH__ACCESS_TOKEN_COOKIE_NAME": "ACCESS_TOKEN_COOKIE_NAME",
            "AUTH__REFRESH_TOKEN_COOKIE_NAME": "REFRESH_TOKEN_COOKIE_NAME",
            "AUTH__REFRESH_TOKEN_COOKIE_PATH": "REFRESH_TOKEN_COOKIE_PATH",
            "AUTH__ACCOUNT_LOCKOUT__MAX_ATTEMPTS": "ACCOUNT_LOCKOUT_MAX_ATTEMPTS",
            "AUTH__ACCOUNT_LOCKOUT__DURATION_MINUTES": "ACCOUNT_LOCKOUT_DURATION_MINUTES",
            "EMAIL__ENABLED": "MAIL_ENABLED",
            "EMAIL__SERVER": "MAIL_SERVER",
            "EMAIL__PORT": "MAIL_PORT",
            "EMAIL__USERNAME": "MAIL_USERNAME",
            "EMAIL__PASSWORD": "MAIL_PASSWORD",
            "EMAIL__STARTTLS": "MAIL_STARTTLS",
            "EMAIL__SSL_TLS": "MAIL_SSL_TLS",
            "EMAIL__FROM": "MAIL_FROM",
            "OAUTH__CREATE_USER_WITHOUT_EMAIL": "OAUTH_CREATE_USER_WITHOUT_EMAIL",
            "OAUTH__REQUIRE_EMAIL_VERIFICATION": "OAUTH_REQUIRE_EMAIL_VERIFICATION",
            "OAUTH__EMAIL_DOMAIN": "OAUTH_EMAIL_DOMAIN",
            "LOGGING__LEVEL": "LOG_LEVEL",
            # Redis configuration
            "REDIS__ENABLED": "REDIS_ENABLED",
            "REDIS__URL": "REDIS_URL",
            "REDIS__PASSWORD": "REDIS_PASSWORD",
            "REDIS__SSL": "REDIS_SSL",
            "REDIS__MAX_CONNECTIONS": "REDIS_MAX_CONNECTIONS",
            # Celery configuration
            "CELERY__ENABLED": "CELERY_ENABLED",
            "CELERY__BROKER_URL": "CELERY_BROKER_URL",
            "CELERY__RESULT_BACKEND": "CELERY_RESULT_BACKEND",
            "CELERY__WORKER_CONCURRENCY": "CELERY_WORKER_CONCURRENCY",
        }

        # Apply YAML config values (only if not already set by env vars)
        # We check if the current value equals the model's default value
        model_defaults = self.__class__.model_fields

        for yaml_key, field_name in yaml_to_field_mapping.items():
            if yaml_key in flat_config and field_name in model_defaults:
                yaml_value = flat_config[yaml_key]
                current_value = getattr(self, field_name)
                field_info = model_defaults[field_name]
                default_value = field_info.default

                # Only apply YAML value if current value is still the default
                # (meaning it wasn't overridden by env var or .env file)
                if current_value == default_value and yaml_value is not None:
                    # Handle SecretStr fields specially
                    if field_info.annotation == SecretStr or (
                        hasattr(field_info.annotation, "__origin__")
                        and SecretStr in getattr(field_info.annotation, "__args__", ())
                    ):
                        if isinstance(yaml_value, str):
                            yaml_value = SecretStr(yaml_value)

                    setattr(self, field_name, yaml_value)


settings = Settings()


# Resolve paths under PROJECT_ROOT when relative
def _resolve_under_project(path_str: str, base: Path) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


# Resolve and create data root
data_root_path = _resolve_under_project(settings.DATA_ROOT, PROJECT_ROOT)
data_root_path.mkdir(parents=True, exist_ok=True)

# Normalize SQLite path to absolute under data root when using sqlite
sqlite_prefix = "sqlite+aiosqlite:///"
if settings.DATABASE_URL.startswith(sqlite_prefix):
    db_path_str = settings.DATABASE_URL.removeprefix(sqlite_prefix)
    db_path = Path(db_path_str)
    if not db_path.is_absolute():
        # keep filename but place under data root
        db_path = data_root_path / db_path.name
    db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.DATABASE_URL = f"{sqlite_prefix}{db_path}"

# Normalize local storage root
settings.LOCAL_STORAGE_ROOT = str(
    _resolve_under_project(settings.LOCAL_STORAGE_ROOT, data_root_path)
)
Path(settings.LOCAL_STORAGE_ROOT).mkdir(parents=True, exist_ok=True)

# Normalize vector store persist directories
if settings.CHROMA_PERSIST_DIR:
    settings.CHROMA_PERSIST_DIR = str(
        _resolve_under_project(settings.CHROMA_PERSIST_DIR, data_root_path)
    )
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)

if settings.QDRANT_PERSIST_DIR:
    settings.QDRANT_PERSIST_DIR = str(
        _resolve_under_project(settings.QDRANT_PERSIST_DIR, data_root_path)
    )
    Path(settings.QDRANT_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
