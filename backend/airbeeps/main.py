import contextvars
import logging
import logging.config
import sys
import uuid

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


app_config = {"title": settings.PROJECT_NAME}

if settings.ENVIRONMENT not in settings.SHOW_DOCS_ENVIRONMENT:
    app_config["openapi_url"] = None

app = FastAPI(**app_config)

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
    except Exception:
        logging.getLogger("app").exception("Unhandled exception")
        raise


app.include_router(configs_user_router_v1, prefix="/api/v1", tags=["Public Configs"])

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

# OAuth Admin routes
admin_router_v1.include_router(oauth_admin_router_v1, tags=["Admin - OAuth"])

# Users Admin routes
admin_router_v1.include_router(users_admin_router_v1, tags=["Admin - Users"])
admin_router_v1.include_router(configs_admin_router_v1, tags=["Admin - System Config"])

app.include_router(admin_router_v1)

# Add pagination support
add_pagination(app)


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
