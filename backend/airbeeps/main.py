import contextvars
import logging
import logging.config
import os
import sys
import uuid

# Disable third-party telemetry (but NOT OpenTelemetry for our own tracing)
os.environ["LLAMA_INDEX_INSTRUMENTATION"] = "false"
os.environ["LLAMA_INDEX_NO_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
# Disable LlamaIndex global handler (prevents any telemetry setup)
os.environ["LLAMA_INDEX_DISABLE_GLOBAL_HANDLER"] = "1"
# Note: OTEL_SDK_DISABLED is NOT set - we use OpenTelemetry for our own agent tracing

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import add_pagination
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .agents.api.v1.admin_router import router as agents_admin_router_v1
from .agents.api.v1.admin_router import tools_router as tools_admin_router_v1
from .agents.memory import memory_admin_router, memory_router
from .agents.resilience.api import router as health_router
from .agents.specialist.api import router as multiagent_router
from .agents.specialist.api import admin_router as multiagent_admin_router
from .agents.tracing.api import router as tracing_router
from .audit.api import router as audit_router
from .ai_models.api.v1.admin_router import router as models_admin_router_v1
from .ai_models.api.v1.user_router import router as models_user_router_v1
from .assistants.api.v1.admin_router import router as assistants_admin_router_v1
from .assistants.api.v1.user_router import router as assistants_user_router_v1
from .auth import current_active_user, current_superuser
from .auth.api.v1.oauth_admin_router import router as oauth_admin_router_v1
from .auth.api.v1.oauth_user_router import router as oauth_user_router
from .auth.api.v1.refresh_router import router as auth_refresh_router
from .auth.api.v1.user_router import router as auth_user_router
from .chat.api.v1.admin_router import router as chat_admin_router_v1
from .chat.api.v1.share_router import router as chat_share_router_v1
from .chat.api.v1.user_router import router as chat_user_router_v1
from .config import EnvironmentType, settings
from .files.api.v1.admin_router import router as files_admin_router_v1
from .files.api.v1.user_router import router as files_user_router_v1
from .rag.api.v1.admin_router import router as rag_admin_router_v1
from .rag.api.v1.user_router import router as rag_user_router_v1
from .system_config.api.v1.admin_router import router as configs_admin_router_v1
from .system_config.api.v1.user_router import router as configs_user_router_v1
from .users.api.v1.admin_router import router as users_admin_router_v1
from .users.api.v1.user_router import router as users_user_router_v1
from .ai_models.analytics import router as analytics_router
from .ai_models.analytics import admin_router as analytics_admin_router

# Request-scoped ID
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    """Inject request_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        record.request_id = request_id_var.get("-")
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": RequestIdFilter}},
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s [req=%(request_id)s] %(name)s: %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["request_id"],
        }
    },
    "root": {
        "level": settings.LOG_LEVEL,
        "handlers": ["console"],
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)

# Log telemetry status at startup
logger.info("=" * 60)
logger.info("TELEMETRY STATUS: Third-party telemetry DISABLED")
logger.info("=" * 60)
logger.info("✓ ChromaDB telemetry: DISABLED (anonymized_telemetry=False)")
logger.info("✓ LlamaIndex telemetry: DISABLED")
logger.info("✓ HuggingFace telemetry: DISABLED")
logger.info("✓ DO_NOT_TRACK: ENABLED")
if settings.TRACING_ENABLED:
    logger.info(f"✓ Agent Tracing: ENABLED (backend: {settings.TRACING_BACKEND})")
else:
    logger.info("✓ Agent Tracing: DISABLED")
logger.info("=" * 60)

# ============================================================================
# Security: Validate SECRET_KEY in production
# ============================================================================
_DEFAULT_SECRET_KEY = "change-me-in-production"
if (
    settings.ENVIRONMENT == EnvironmentType.PRODUCTION
    and settings.SECRET_KEY == _DEFAULT_SECRET_KEY
):
    logging.getLogger(__name__).critical(
        "SECURITY ERROR: Default SECRET_KEY detected in production! "
        "Set AIRBEEPS_SECRET_KEY to a secure random value."
    )
    sys.exit(1)

# ============================================================================
# Rate Limiting Configuration
# ============================================================================
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


async def require_active_user(current_active_user=Depends(current_active_user)):
    if not current_active_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Active user required"
        )
    return current_active_user


async def require_admin(current_superuser=Depends(current_superuser)):
    if not current_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_superuser


# ============================================================================
# OpenAPI / Interactive API Documentation Configuration
# ============================================================================
app_config: dict[str, Any] = {
    "title": settings.PROJECT_NAME,
    "description": """
**Airbeeps** - Local-first, self-hosted AI assistant for chat and RAG.

## Features
- 🤖 **Multi-LLM Chat** - Support for OpenAI, Anthropic, Google, local models via LiteLLM
- 📚 **RAG System** - Advanced retrieval with hybrid search, reranking, and multi-hop
- 🔧 **Agent Tools** - Code execution, web search, file operations, data analysis
- 🧠 **Agent Memory** - Persistent memory with encryption and GDPR compliance
- 🔌 **MCP Integration** - Model Context Protocol for external tool integration
- 📊 **Observability** - OpenTelemetry tracing and metrics

## Authentication
Most endpoints require authentication via JWT tokens. Use the `/api/v1/auth/login` endpoint to obtain tokens.

## API Versioning
All endpoints are versioned under `/api/v1/`. Future versions will be added as `/api/v2/` etc.
""",
    "version": "1.0.0",
    "license_info": {
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    "contact": {
        "name": "Airbeeps Support",
        "url": "https://github.com/airbeeps/airbeeps",
        "email": "hello@airbeeps.com",
    },
    "openapi_tags": [
        {"name": "Health", "description": "Health check endpoints for monitoring"},
        {"name": "Auth", "description": "Authentication and token management"},
        {"name": "OAuth", "description": "OAuth provider integrations"},
        {"name": "Users", "description": "User profile management"},
        {"name": "Assistants", "description": "AI assistant configurations"},
        {"name": "Chat", "description": "Conversation and messaging"},
        {"name": "RAG", "description": "Retrieval-Augmented Generation"},
        {"name": "Agent Memory", "description": "Agent memory management"},
        {"name": "Multi-Agent", "description": "Multi-agent orchestration"},
        {"name": "Files", "description": "File upload and management"},
        {"name": "AI Models", "description": "AI model discovery and configuration"},
        {
            "name": "Model Analytics",
            "description": "Model usage analytics and A/B testing",
        },
    ],
}

# Only show docs in allowed environments (or when explicitly enabled)
if settings.ENVIRONMENT not in settings.SHOW_DOCS_ENVIRONMENT:
    if not settings.DOCS_ENABLED:
        app_config["openapi_url"] = None
    else:
        # Docs explicitly enabled in non-dev environment
        app_config["docs_url"] = "/docs"
        app_config["redoc_url"] = "/redoc"
        app_config["openapi_url"] = "/openapi.json"
else:
    # Development environment - always show docs
    app_config["docs_url"] = "/docs"
    app_config["redoc_url"] = "/redoc"
    app_config["openapi_url"] = "/openapi.json"

app = FastAPI(**app_config)

# ============================================================================
# OpenTelemetry Tracing Setup (for agent observability)
# ============================================================================
if settings.TRACING_ENABLED:
    from .agents.tracing.config import (
        TracingConfig,
        TracingBackend,
        setup_global_tracing,
    )
    from .agents.tracing.pii_redactor import PIIRedactor, set_redactor
    from .agents.tracing.metrics import setup_metrics

    # Setup PII redactor
    redactor = PIIRedactor(enabled=settings.TRACING_REDACT_PII)
    set_redactor(redactor)

    # Setup tracing
    try:
        tracing_config = TracingConfig(
            backend=TracingBackend(settings.TRACING_BACKEND),
            endpoint=settings.TRACING_ENDPOINT or None,
            service_name="airbeeps-agents",
            enable_pii_redaction=settings.TRACING_REDACT_PII,
            sample_rate=settings.TRACING_SAMPLE_RATE,
            admin_only=settings.TRACING_ADMIN_ONLY,
        )
        setup_global_tracing(tracing_config)
        logger.info(
            f"OpenTelemetry tracing initialized: backend={settings.TRACING_BACKEND}"
        )
    except Exception as e:
        logger.warning(f"Failed to initialize tracing: {e}")

    # Setup metrics
    try:
        setup_metrics(service_name="airbeeps-agents", enable_console=False)
        logger.info("OpenTelemetry metrics initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize metrics: {e}")

    # Optionally instrument FastAPI (requires tracing to be enabled)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented with OpenTelemetry")
    except ImportError:
        logger.debug("FastAPI instrumentation not available")
    except Exception as e:
        logger.warning(f"Failed to instrument FastAPI: {e}")

# ============================================================================
# Security Middleware
# ============================================================================

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration
# In production, only allow the configured frontend origin
# In development, allow localhost origins for convenience
if settings.ENVIRONMENT == EnvironmentType.PRODUCTION:
    cors_origins = [str(settings.FRONTEND_URL).rstrip("/")]
    if settings.EXTERNAL_URL:
        cors_origins.append(str(settings.EXTERNAL_URL).rstrip("/"))
else:
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        str(settings.FRONTEND_URL).rstrip("/"),
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_var.set(req_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["x-request-id"] = req_id
    return response


@app.middleware("http")
async def log_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        # Log just the essential error info without the full stack trace for common errors
        logger = logging.getLogger("app")

        # For database errors, log a concise message
        if "sqlalchemy" in str(type(e).__module__).lower():
            logger.error(
                f"Database error in {request.method} {request.url.path}: {type(e).__name__}: {str(e)}"
            )
        else:
            # For other exceptions, log full trace
            logger.exception("Unhandled exception")
        raise


app.include_router(configs_user_router_v1, prefix="/api/v1", tags=["Public Configs"])

# Health endpoints (no auth required for liveness/readiness probes)
app.include_router(health_router, prefix="/api/v1", tags=["Health"])

app.include_router(auth_user_router, prefix="/api/v1", tags=["Auth"])
app.include_router(auth_refresh_router, prefix="/api/v1", tags=["Auth"])
app.include_router(oauth_user_router, prefix="/api/v1", tags=["OAuth"])

# Assistants (public endpoints)
app.include_router(assistants_user_router_v1, prefix="/api/v1", tags=["Assistants"])
app.include_router(chat_share_router_v1, prefix="/api/v1", tags=["Chat Shares"])


# User routes
user_route_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(require_active_user)])

user_route_v1.include_router(users_user_router_v1, tags=["Users"])

user_route_v1.include_router(models_user_router_v1, tags=["AI Models"])

user_route_v1.include_router(files_user_router_v1, tags=["Files"])

user_route_v1.include_router(chat_user_router_v1, tags=["Chat"])
user_route_v1.include_router(rag_user_router_v1, tags=["RAG"])
user_route_v1.include_router(memory_router, tags=["Agent Memory"])
user_route_v1.include_router(multiagent_router, tags=["Multi-Agent"])
user_route_v1.include_router(analytics_router, tags=["Model Analytics"])

app.include_router(user_route_v1)


# Admin routes
admin_router_v1 = APIRouter(
    prefix="/api/v1/admin", dependencies=[Depends(require_admin)]
)

admin_router_v1.include_router(assistants_admin_router_v1, tags=["Admin - Assistants"])

admin_router_v1.include_router(models_admin_router_v1, tags=["Admin - AI Models"])

admin_router_v1.include_router(files_admin_router_v1, tags=["Admin - Files"])

admin_router_v1.include_router(rag_admin_router_v1, prefix="/rag", tags=["Admin - RAG"])

admin_router_v1.include_router(chat_admin_router_v1, tags=["Admin - Chat"])

admin_router_v1.include_router(
    agents_admin_router_v1, tags=["Admin - Agent Tools & MCP"]
)

admin_router_v1.include_router(
    tools_admin_router_v1, tags=["Admin - Agent Tools & MCP"]
)
admin_router_v1.include_router(memory_admin_router, tags=["Admin - Agent Memory"])
admin_router_v1.include_router(tracing_router, tags=["Admin - Agent Tracing"])
admin_router_v1.include_router(multiagent_admin_router, tags=["Admin - Multi-Agent"])

# OAuth Admin routes
admin_router_v1.include_router(oauth_admin_router_v1, tags=["Admin - OAuth"])

# Users Admin routes
admin_router_v1.include_router(users_admin_router_v1, tags=["Admin - Users"])
admin_router_v1.include_router(configs_admin_router_v1, tags=["Admin - System Config"])

# Audit logs
admin_router_v1.include_router(audit_router, tags=["Admin - Audit Logs"])

# Model Analytics & A/B Testing
admin_router_v1.include_router(analytics_admin_router, tags=["Admin - Model Analytics"])

app.include_router(admin_router_v1)

# Add pagination support
add_pagination(app)


# ============================================================================
# Startup and Shutdown Events
# ============================================================================
@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    logger = logging.getLogger(__name__)

    # Initialize storage (create bucket if needed)
    try:
        from .files.storage import init_storage

        await init_storage()
    except Exception as e:
        logger.warning(f"Storage initialization warning: {e}")

    # Initialize cache (warm up connection)
    try:
        from .cache import get_cache

        cache = await get_cache()
        healthy = await cache.health_check()
        if healthy:
            logger.info("Cache backend initialized successfully")
        else:
            logger.warning("Cache health check failed")
    except Exception as e:
        logger.warning(f"Cache initialization warning: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown."""
    logger = logging.getLogger(__name__)

    # Close cache connection
    try:
        from .cache import close_cache

        await close_cache()
        logger.info("Cache connection closed")
    except Exception as e:
        logger.warning(f"Cache shutdown warning: {e}")


# ============================================================================
# Static File Serving (for bundled frontend in production)
# ============================================================================
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Check if static files are bundled (happens in pip-installed version)
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    logger = logging.getLogger(__name__)
    logger.info(f"Serving static frontend from {STATIC_DIR}")

    # Mount _nuxt assets (Nuxt's build artifacts)
    if (STATIC_DIR / "_nuxt").exists():
        app.mount(
            "/_nuxt",
            StaticFiles(directory=str(STATIC_DIR / "_nuxt")),
            name="nuxt-assets",
        )

    # Serve other static files (favicon, images, etc.)
    @app.get("/favicon.ico")
    async def favicon():
        favicon_path = STATIC_DIR / "favicon.ico"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404)

    @app.get("/logo.png")
    async def logo():
        logo_path = STATIC_DIR / "logo.png"
        if logo_path.exists():
            return FileResponse(logo_path)
        raise HTTPException(status_code=404)

    # Catch-all route for SPA (must be last!)
    # This serves index.html for all non-API routes to enable client-side routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        Serve the SPA for all routes not handled by API.
        This enables client-side routing in Nuxt/Vue.
        """
        # Don't intercept API routes (they should have been handled above)
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")

        # Check if it's a static file request
        file_path = STATIC_DIR / full_path
        resolved_path = file_path.resolve()
        static_dir_resolved = STATIC_DIR.resolve()
        # Prevent path traversal attacks
        if not str(resolved_path).startswith(str(static_dir_resolved)):
            raise HTTPException(status_code=403, detail="Access denied")
        if resolved_path.exists() and resolved_path.is_file():
            return FileResponse(resolved_path)

        # Otherwise, serve index.html for client-side routing
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        raise HTTPException(status_code=404, detail="Frontend not found")
