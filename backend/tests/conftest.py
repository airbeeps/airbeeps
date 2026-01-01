"""
Pytest configuration for Airbeeps backend tests.

IMPORTANT: Environment variables must be set BEFORE importing any airbeeps modules
to ensure proper test isolation with temp directories and test mode.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

# =============================================================================
# Environment Setup - MUST happen before any airbeeps imports
# =============================================================================


def _setup_test_environment(tmp_path: Path) -> dict:
    """
    Configure environment for testing.

    This sets up:
    - TEST_MODE=1 to use fake LLM/embedding clients
    - Temp DATA_ROOT, DATABASE_URL, and CHROMA_PERSIST_DIR
    - Empty CHROMA_SERVER_HOST to use embedded mode

    Returns the original environment values for restoration.
    """
    original_env = {}

    # Test mode: enables fake LLM and embedding clients
    original_env["AIRBEEPS_TEST_MODE"] = os.environ.get("AIRBEEPS_TEST_MODE")
    os.environ["AIRBEEPS_TEST_MODE"] = "1"

    # Data root: use temp directory
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    original_env["AIRBEEPS_DATA_ROOT"] = os.environ.get("AIRBEEPS_DATA_ROOT")
    os.environ["AIRBEEPS_DATA_ROOT"] = str(data_root)

    # Database: use temp SQLite file
    db_path = tmp_path / "test.db"
    original_env["AIRBEEPS_DATABASE_URL"] = os.environ.get("AIRBEEPS_DATABASE_URL")
    os.environ["AIRBEEPS_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    # Chroma: use temp persist dir in embedded mode
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    original_env["AIRBEEPS_CHROMA_PERSIST_DIR"] = os.environ.get(
        "AIRBEEPS_CHROMA_PERSIST_DIR"
    )
    os.environ["AIRBEEPS_CHROMA_PERSIST_DIR"] = str(chroma_dir)

    # Ensure Chroma uses embedded mode (no server)
    original_env["AIRBEEPS_CHROMA_SERVER_HOST"] = os.environ.get(
        "AIRBEEPS_CHROMA_SERVER_HOST"
    )
    os.environ["AIRBEEPS_CHROMA_SERVER_HOST"] = ""

    # Disable mail to avoid any email sending attempts
    original_env["AIRBEEPS_MAIL_ENABLED"] = os.environ.get("AIRBEEPS_MAIL_ENABLED")
    os.environ["AIRBEEPS_MAIL_ENABLED"] = "false"

    # Use a known secret key for tests
    original_env["AIRBEEPS_SECRET_KEY"] = os.environ.get("AIRBEEPS_SECRET_KEY")
    os.environ["AIRBEEPS_SECRET_KEY"] = "test-secret-key-not-for-production"

    return original_env


def _restore_environment(original_env: dict) -> None:
    """Restore original environment values."""
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# =============================================================================
# Session-scoped fixtures for test environment
# =============================================================================


@pytest.fixture(scope="session")
def session_tmp_path(tmp_path_factory) -> Path:
    """Create a session-scoped temp directory."""
    return tmp_path_factory.mktemp("airbeeps_test")


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(session_tmp_path: Path):
    """
    Session-scoped fixture to set up test environment.

    This runs ONCE before any tests and sets up:
    - TEST_MODE environment variable
    - Temp directories for data, database, and chroma
    """
    original_env = _setup_test_environment(session_tmp_path)
    yield
    _restore_environment(original_env)


# =============================================================================
# Now safe to import airbeeps modules (after environment is configured)
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-level event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine(setup_test_environment):
    """Create test database engine after environment is configured."""
    # Import after environment setup
    from sqlalchemy.ext.asyncio import create_async_engine

    from airbeeps.config import settings

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def setup_database(test_engine):
    """Create database tables using Alembic migrations."""
    # Import after environment setup
    import airbeeps.agents.models
    import airbeeps.ai_models.models
    import airbeeps.assistants.models
    import airbeeps.auth.oauth_models
    import airbeeps.auth.refresh_token_models
    import airbeeps.feedback.models
    import airbeeps.files.models
    import airbeeps.rag.models
    import airbeeps.system_config.models

    # Import all models to register them with Base.metadata
    import airbeeps.users.models  # noqa: F401
    from airbeeps.models import Base

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Drop all tables after tests
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="session")
async def session_maker(test_engine, setup_database):
    """Create async session maker."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def session(session_maker) -> AsyncGenerator:
    """Provide a database session for testing with rollback."""

    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session) -> AsyncGenerator:
    """Create test client and override database dependency."""
    from httpx import ASGITransport, AsyncClient

    from airbeeps.database import get_async_session
    from airbeeps.main import app

    async def override_get_async_session():
        yield session

    # Override database dependency
    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    # Clean up dependency overrides
    app.dependency_overrides.clear()


# =============================================================================
# Fresh database fixtures for isolation-critical tests
# =============================================================================
#
# DB Isolation Strategy:
# - Default (session/client fixtures): Session-scoped DB with per-test rollback.
#   Fast but sequences/IDs may leak across tests.
# - Module-scoped (module_db_session/module_client): Fresh DB per test module.
#   Good balance for most integration tests.
# - Per-function (fresh_db_session/fresh_client): Fresh DB per test function.
#   Use for tests that need complete isolation (e.g., core flow).
# =============================================================================


@pytest_asyncio.fixture(scope="module")
async def module_db_session(session_tmp_path: Path, setup_test_environment):
    """
    Provide a fresh database per test module.

    This creates a new database file for each test module, providing
    better isolation than session-scoped without the overhead of
    per-function isolation.
    """
    import uuid

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    import airbeeps.agents.models
    import airbeeps.ai_models.models
    import airbeeps.assistants.models
    import airbeeps.auth.oauth_models
    import airbeeps.auth.refresh_token_models
    import airbeeps.feedback.models
    import airbeeps.files.models
    import airbeeps.rag.models
    import airbeeps.system_config.models

    # Import all models
    import airbeeps.users.models  # noqa: F401
    from airbeeps.models import Base

    # Create a unique database file for this module
    db_path = session_tmp_path / f"module_{uuid.uuid4().hex[:8]}.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(db_url, echo=False, future=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        yield session

    await engine.dispose()

    # Clean up database file
    if db_path.exists():
        db_path.unlink()


@pytest_asyncio.fixture(scope="module")
async def module_client(module_db_session, setup_test_environment):
    """Create test client with a module-scoped fresh database."""
    from httpx import ASGITransport, AsyncClient

    from airbeeps.database import get_async_session
    from airbeeps.main import app

    async def override_get_async_session():
        yield module_db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def fresh_db_session(session_tmp_path: Path, setup_test_environment):
    """
    Provide a completely fresh database for tests that need full isolation.

    Use this for tests that create lots of data and need a clean slate,
    such as the core flow integration test.
    """
    import uuid

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    import airbeeps.agents.models
    import airbeeps.ai_models.models
    import airbeeps.assistants.models
    import airbeeps.auth.oauth_models
    import airbeeps.auth.refresh_token_models
    import airbeeps.feedback.models
    import airbeeps.files.models
    import airbeeps.rag.models
    import airbeeps.system_config.models

    # Import all models
    import airbeeps.users.models  # noqa: F401
    from airbeeps.models import Base

    # Create a unique database file for this test
    db_path = session_tmp_path / f"fresh_{uuid.uuid4().hex[:8]}.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(db_url, echo=False, future=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        yield session

    await engine.dispose()

    # Clean up database file
    if db_path.exists():
        db_path.unlink()


@pytest_asyncio.fixture
async def fresh_client(fresh_db_session, setup_test_environment):
    """Create test client with a fresh database."""
    from httpx import ASGITransport, AsyncClient

    from airbeeps.database import get_async_session
    from airbeeps.main import app

    async def override_get_async_session():
        yield fresh_db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
