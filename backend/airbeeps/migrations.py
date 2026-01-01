"""
Programmatic Alembic migrations for installed packages.

This module allows running Alembic migrations without relying on alembic.ini file,
which is necessary when the package is installed via pip.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

from .config import settings

logger = logging.getLogger(__name__)


def get_alembic_config() -> Config:
    """
    Create Alembic configuration programmatically.

    This locates the alembic directory within the installed package
    and configures it to work without alembic.ini.
    """
    # Find the alembic directory bundled inside the airbeeps package.
    # Keeping migrations under our own namespace prevents installing a top-level
    # `alembic/` folder into site-packages (namespace pollution / conflicts).
    package_dir = Path(__file__).resolve().parent
    alembic_dir = package_dir / "alembic"

    if not alembic_dir.exists():
        raise RuntimeError(
            f"Alembic directory not found at {alembic_dir}. "
            "Make sure alembic migrations are included in the package."
        )

    # Create Alembic config
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

    # Set other common options
    alembic_cfg.set_main_option("prepend_sys_path", ".")
    alembic_cfg.set_main_option(
        "file_template",
        "%%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s",
    )

    return alembic_cfg


def get_current_revision() -> str | None:
    """Get the current database revision."""
    try:
        # Create a sync engine for Alembic (it doesn't support async)
        sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        engine = create_engine(sync_url, poolclass=pool.NullPool)

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()

        engine.dispose()
        return current_rev
    except Exception as e:
        logger.warning(f"Could not get current revision: {e}")
        return None


def get_head_revision() -> str | None:
    """Get the head revision from migration scripts."""
    try:
        alembic_cfg = get_alembic_config()
        script = ScriptDirectory.from_config(alembic_cfg)
        return script.get_current_head()
    except Exception as e:
        logger.warning(f"Could not get head revision: {e}")
        return None


def needs_migration() -> bool:
    """Check if database needs migration."""
    current = get_current_revision()
    head = get_head_revision()

    if current is None:
        # No alembic_version table = fresh database
        return True

    return current != head


def fix_old_migration_history() -> bool:
    """
    Fix databases with old migration history that references deleted migrations.

    Returns:
        True if fix was applied, False if no fix was needed
    """
    # Current base revision - update this when creating new base migrations
    CURRENT_BASE_REVISION = "448ffe33748b"

    try:
        from sqlalchemy import text

        # Create a sync engine
        sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        engine = create_engine(sync_url, poolclass=pool.NullPool)

        with engine.connect() as connection:
            # Check if alembic_version table exists
            result = connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                )
            )

            if not result.fetchone():
                # No alembic_version table, this is a fresh database
                engine.dispose()
                return False

            # Get current version
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()

            if not row:
                # No version recorded, let migrations run normally
                engine.dispose()
                return False

            current_version = row[0]

            # If it's already at the current base revision, we're good
            if current_version == CURRENT_BASE_REVISION:
                engine.dispose()
                return False

            # Check if the current version exists in our migration files
            alembic_cfg = get_alembic_config()
            script = ScriptDirectory.from_config(alembic_cfg)

            try:
                script.get_revision(current_version)
                # Version exists, no fix needed
                engine.dispose()
                return False
            except Exception:
                # Version doesn't exist - this is an old migration reference
                logger.info(f"Detected old migration reference: {current_version}")
                logger.info("Updating to new migration system...")

                # Update to current base revision
                connection.execute(text("DELETE FROM alembic_version"))
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
                    {"version": CURRENT_BASE_REVISION},
                )
                connection.commit()

                logger.info(f"Migration history updated to '{CURRENT_BASE_REVISION}'")
                engine.dispose()
                return True

        engine.dispose()
        return False

    except Exception as e:
        logger.warning(f"Could not fix migration history: {e}")
        return False


def verify_tables_exist() -> bool:
    """
    Verify that essential tables exist in the database.

    Returns:
        True if tables exist, False if missing
    """
    from sqlalchemy import text

    # Essential tables that must exist
    essential_tables = ["users", "oauth_providers", "system_configs", "models"]

    try:
        sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        engine = create_engine(sync_url, poolclass=pool.NullPool)

        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            existing_tables = {row[0] for row in result.fetchall()}

        engine.dispose()

        # Check if essential tables exist
        missing = [t for t in essential_tables if t not in existing_tables]
        if missing:
            logger.warning(f"Missing essential tables: {missing}")
            return False
        return True

    except Exception as e:
        logger.warning(f"Could not verify tables: {e}")
        return False


def create_tables_from_models() -> None:
    """
    Create all tables from SQLAlchemy models.

    This is a fallback for when migrations fail to create tables.
    """
    from .models import Base

    logger.info("Creating tables from SQLAlchemy models...")

    sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
    engine = create_engine(sync_url, poolclass=pool.NullPool)

    # Import all model classes to ensure they're registered with Base.metadata
    # Order matters - base tables first, then dependent tables
    from .agents.models import (  # noqa: F401
        AgentExecution,
        MCPServerConfig,
        assistant_mcp_servers,
    )
    from .ai_models.models import Model, ModelAsset, ModelProvider  # noqa: F401
    from .assistants.models import (  # noqa: F401
        Assistant,
        Conversation,
        ConversationShare,
        Message,
        PinnedAssistant,
    )
    from .auth.oauth_models import (  # noqa: F401
        OAuthProvider,
        OAuthState,
        OAuthUserLink,
    )
    from .auth.refresh_token_models import RefreshToken  # noqa: F401
    from .files.models import FileRecord  # noqa: F401
    from .rag.models import Document, DocumentChunk, KnowledgeBase  # noqa: F401
    from .system_config.models import SystemConfig  # noqa: F401
    from .users.models import User  # noqa: F401

    Base.metadata.create_all(bind=engine)
    engine.dispose()

    logger.info("Tables created successfully from models")


def run_migrations(revision: str = "head") -> None:
    """
    Run Alembic migrations to the specified revision.

    Args:
        revision: Target revision (default: "head" for latest)
    """
    logger.info(f"Running Alembic migrations to revision: {revision}")

    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, revision)
        logger.info("Migrations completed successfully")

        # Verify tables exist after migration
        if not verify_tables_exist():
            logger.warning("Tables missing after migration. Creating from models...")
            create_tables_from_models()

    except Exception as e:
        # Check if this is an old migration reference error
        error_msg = str(e)
        if "Can't locate revision" in error_msg or "No such revision" in error_msg:
            logger.warning("Detected old migration reference. Attempting to fix...")
            if fix_old_migration_history():
                logger.info("Migration history fixed. Retrying migration...")
                # Retry the migration
                command.upgrade(alembic_cfg, revision)
                logger.info("Migrations completed successfully")

                # Verify tables after retry
                if not verify_tables_exist():
                    logger.warning(
                        "Tables missing after migration. Creating from models..."
                    )
                    create_tables_from_models()
                return

        logger.error(f"Migration failed: {e}", exc_info=True)
        raise


def create_initial_revision(message: str = "Initial migration") -> None:
    """Create a new migration revision (for development)."""
    alembic_cfg = get_alembic_config()
    command.revision(alembic_cfg, message=message, autogenerate=True)


def downgrade_migration(revision: str = "-1") -> None:
    """
    Downgrade database to a previous revision.

    Args:
        revision: Target revision (default: "-1" for one step back)
    """
    logger.info(f"Downgrading database to revision: {revision}")
    alembic_cfg = get_alembic_config()
    command.downgrade(alembic_cfg, revision)
    logger.info("Downgrade completed successfully")


def ensure_tables_exist() -> bool:
    """
    Ensure all required tables exist, creating them if missing.

    This should be called on startup to handle edge cases where
    alembic_version exists but tables don't.

    Returns:
        True if tables were created/verified, False on error
    """
    try:
        if not verify_tables_exist():
            logger.info("Essential tables missing. Creating from models...")
            create_tables_from_models()
            return True
        return True
    except Exception as e:
        logger.error(f"Failed to ensure tables exist: {e}")
        return False


def get_database_path() -> str:
    """Get the actual database file path for display purposes."""
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite"):
        # Extract path from sqlite URL
        path = db_url.split("///")[-1]
        return path
    return db_url


def show_current_revision() -> None:
    """Display current database revision."""
    current = get_current_revision()
    head = get_head_revision()

    if current is None:
        pass
    else:
        pass

    if head:
        pass

    if (current and head and current != head) or (current and head and current == head):
        pass
