from enum import Enum
from pathlib import Path
from typing import ClassVar

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
else:
    # Development mode: use project structure
    BASE_DIR = Path(__file__).resolve().parent.parent
    PROJECT_ROOT = BASE_DIR.parent
    TEMPLATE_DIR = BASE_DIR / "templates"


class EnvironmentType(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


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

    # Vector Store
    CHROMA_SERVER_HOST: str = ""  # Chroma service address (empty = embedded mode)
    CHROMA_SERVER_PORT: int = 8500
    CHROMA_PERSIST_DIR: str = "chroma"  # Relative to DATA_ROOT

    # Agent Configuration
    AGENT_MAX_ITERATIONS: int = 10  # Agent max iterations
    AGENT_TIMEOUT_SECONDS: int = 300  # Agent execution timeout (seconds)
    AGENT_ENABLE_MEMORY: bool = False  # Whether to enable Agent memory

    # MCP Configuration
    MCP_ENABLED: bool = False  # Whether to enable MCP features
    MCP_SERVERS_CONFIG_PATH: str = (
        "/app/mcp_servers.json"  # MCP servers config file path
    )

    # Test Mode Configuration
    # When enabled, all external LLM/embedding calls are replaced with deterministic fakes.
    # This ensures tests never hit real APIs even if keys are present in the environment.
    TEST_MODE: bool = False  # Set via AIRBEEPS_TEST_MODE=1 in environment


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

# Normalize chroma persist dir
if settings.CHROMA_PERSIST_DIR:
    settings.CHROMA_PERSIST_DIR = str(
        _resolve_under_project(settings.CHROMA_PERSIST_DIR, data_root_path)
    )
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
