"""
Database seeding module for Airbeeps.

This module provides functionality to seed the database with initial data
(system configs and optional providers/models/assistants) from a YAML configuration file.
It supports both one-time seeding (for production) and manual seeding (for development).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select

from .agents.models import (  # noqa: F401 - load assistant_mcp_servers table
    AgentExecution,
    MCPServerConfig,
)
from .ai_models.models import (
    Model,
    ModelProvider,
    ModelStatusEnum,
    ProviderStatusEnum,
)
from .assistants.models import Assistant, AssistantStatusEnum
from .auth.manager import get_user_manager
from .auth.refresh_token_models import (
    RefreshToken,  # noqa: F401 - ensure mapper is loaded
)
from .config import data_root_path
from .database import async_session_maker
from .rag.models import IngestionProfile
from .system_config.models import SystemConfig
from .users.models import User

logger = logging.getLogger(__name__)

ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(:-([^}]*))?\}")

# Marker file to track if one-time seeding has been done
SEED_MARKER_FILE = data_root_path / ".seed_completed"


def expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} or ${VAR:-default} in YAML-loaded data."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(3)
            return os.getenv(var_name, default if default is not None else "")

        return ENV_VAR_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    return value


def load_seed_data(path: Path) -> dict[str, Any]:
    """Load and parse seed data from YAML file."""
    if not HAS_YAML:
        raise ImportError(
            "PyYAML is required for seeding. Install with `pip install pyyaml`."
        )

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return expand_env(raw)


async def ensure_users(users: list[dict[str, Any]]) -> dict[str, User]:
    """Create missing users; return mapping email -> User."""
    created: dict[str, User] = {}
    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager_gen = get_user_manager(user_db)
        user_manager = await user_manager_gen.__anext__()

        for entry in users:
            email = entry.get("email")
            password = entry.get("password")
            if not email or not password:
                logger.warning(f"Skipping user with missing email/password: {entry}")
                continue

            existing = await user_db.get_by_email(email)
            if existing:
                logger.info(f"User {email} exists, skipping create")
                created[email] = existing
                continue

            hashed_password = user_manager.password_helper.hash(password)
            user = User(
                email=email,
                hashed_password=hashed_password,
                name=entry.get("name"),
                # Safer defaults: normal users, active + verified unless explicitly set.
                is_superuser=bool(entry.get("is_superuser", False)),
                is_verified=bool(entry.get("is_verified", True)),
                is_active=bool(entry.get("is_active", True)),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Created user {email}")
            created[email] = user

    return created


async def ensure_providers(providers: list[dict[str, Any]]) -> dict[str, ModelProvider]:
    """Create or update providers; return mapping name -> ModelProvider."""
    created: dict[str, ModelProvider] = {}
    async with async_session_maker() as session:
        for entry in providers:
            name = entry.get("name")
            if not name:
                logger.warning(f"Skipping provider without name: {entry}")
                continue

            result = await session.execute(
                select(ModelProvider).where(ModelProvider.name == name)
            )
            provider = result.scalar_one_or_none()

            status_value = str(entry.get("status", "ACTIVE")).upper()
            status = ProviderStatusEnum[status_value]

            if provider:
                # Update selected fields (idempotent)
                provider.display_name = entry.get("display_name", provider.display_name)
                provider.description = entry.get("description", provider.description)
                provider.interface_type = entry.get(
                    "interface_type", provider.interface_type
                )
                provider.api_base_url = entry.get("api_base_url", provider.api_base_url)
                if entry.get("api_key"):
                    provider.api_key = entry.get("api_key")
                provider.status = status
                logger.info(f"Updated provider {name}")
            else:
                provider = ModelProvider(
                    name=name,
                    display_name=entry.get("display_name", name),
                    description=entry.get("description"),
                    interface_type=entry.get("interface_type", "CUSTOM"),
                    api_base_url=entry.get("api_base_url", ""),
                    api_key=entry.get("api_key"),
                    status=status,
                )
                session.add(provider)
                logger.info(f"Created provider {name}")

            await session.commit()
            await session.refresh(provider)
            created[name] = provider
    return created


async def ensure_models(
    models: list[dict[str, Any]], providers: dict[str, ModelProvider]
) -> dict[str, Model]:
    """Create or update models; return mapping name -> Model."""
    created: dict[str, Model] = {}
    async with async_session_maker() as session:
        for entry in models:
            name = entry.get("name")
            provider_name = entry.get("provider")
            if not name or not provider_name:
                logger.warning(f"Skipping model missing name/provider: {entry}")
                continue

            provider = providers.get(provider_name)
            if not provider:
                logger.error(
                    f"Provider {provider_name} not found for model {name}, skipping"
                )
                continue

            result = await session.execute(
                select(Model).where(
                    (Model.name == name) & (Model.provider_id == provider.id)
                )
            )
            model = result.scalar_one_or_none()

            status_value = str(entry.get("status", "ACTIVE")).upper()
            status = ModelStatusEnum[status_value]

            if model:
                model.display_name = entry.get("display_name", model.display_name)
                model.description = entry.get("description", model.description)
                model.capabilities = entry.get("capabilities", model.capabilities)
                model.generation_config = entry.get(
                    "generation_config", model.generation_config
                )
                model.status = status
                logger.info(f"Updated model {name}")
            else:
                model = Model(
                    name=name,
                    display_name=entry.get("display_name", name),
                    description=entry.get("description"),
                    capabilities=entry.get("capabilities", []),
                    generation_config=entry.get("generation_config", {}),
                    status=status,
                    provider_id=provider.id,
                )
                session.add(model)
                logger.info(f"Created model {name}")

            await session.commit()
            await session.refresh(model)
            created[name] = model
    return created


async def ensure_assistants(
    assistants: list[dict[str, Any]],
    models: dict[str, Model],
    users: dict[str, User],
) -> None:
    """Create or update assistants."""
    async with async_session_maker() as session:
        for entry in assistants:
            name = entry.get("name")
            model_name = entry.get("model")
            owner_email = entry.get("owner_email")
            if not name or not model_name or not owner_email:
                logger.warning(
                    f"Skipping assistant missing name/model/owner_email: {entry}"
                )
                continue

            model = models.get(model_name)
            owner = users.get(owner_email)
            if not model or not owner:
                logger.error(f"Missing model or owner for assistant {name}, skipping")
                continue

            result = await session.execute(
                select(Assistant).where(
                    (Assistant.name == name) & (Assistant.owner_id == owner.id)
                )
            )
            assistant = result.scalar_one_or_none()

            status_value = str(entry.get("status", "ACTIVE")).upper()
            status = AssistantStatusEnum[status_value]

            defaults = {
                "description": entry.get("description"),
                "system_prompt": entry.get("system_prompt"),
                "is_public": bool(entry.get("is_public", True)),
                "config": entry.get("config", {}),
                "temperature": float(entry.get("temperature", 1.0)),
                "max_tokens": int(entry.get("max_tokens", 2048)),
                "tags": entry.get("tags", []),
                "status": status,
            }

            if assistant:
                for key, value in defaults.items():
                    setattr(assistant, key, value)
                assistant.model_id = model.id
                logger.info(f"Updated assistant {name}")
            else:
                assistant = Assistant(
                    name=name,
                    model_id=model.id,
                    owner_id=owner.id,
                    **defaults,
                )
                session.add(assistant)
                logger.info(f"Created assistant {name}")

            await session.commit()
            await session.refresh(assistant)


async def ensure_system_configs(configs: list[dict[str, Any]]) -> None:
    """Create or update system configuration settings."""
    async with async_session_maker() as session:
        for entry in configs:
            key = entry.get("key")
            if not key:
                logger.warning(f"Skipping system config without key: {entry}")
                continue

            result = await session.execute(
                select(SystemConfig).where(SystemConfig.key == key)
            )
            config = result.scalar_one_or_none()

            value = entry.get("value", "")
            is_public = bool(entry.get("is_public", False))
            is_enabled = bool(entry.get("is_enabled", True))

            if config:
                # Update existing config (idempotent)
                config.set_value(value)
                config.description = entry.get("description", config.description)
                config.is_public = is_public
                config.is_enabled = is_enabled
                logger.info(f"Updated system config: {key}")
            else:
                config = SystemConfig(
                    key=key,
                    description=entry.get("description"),
                    is_public=is_public,
                    is_enabled=is_enabled,
                )
                config.set_value(value)
                session.add(config)
                logger.info(f"Created system config: {key}")

            await session.commit()
            await session.refresh(config)


async def ensure_ingestion_profiles(
    profiles: list[dict[str, Any]],
    users: dict[str, User],
) -> None:
    """Create or update builtin ingestion profiles (global templates)."""
    # Get a system user for owner_id (use first superuser, or first user)
    system_owner_id = None
    for user in users.values():
        if user.is_superuser:
            system_owner_id = user.id
            break
    if not system_owner_id and users:
        system_owner_id = next(iter(users.values())).id

    async with async_session_maker() as session:
        # If no user available, try to get any superuser from DB
        if not system_owner_id:
            result = await session.execute(
                select(User).where(User.is_superuser).limit(1)
            )
            system_user = result.scalar_one_or_none()
            if system_user:
                system_owner_id = system_user.id
            else:
                logger.warning("No users found, skipping ingestion profile seeding")
                return

        for entry in profiles:
            name = entry.get("name")
            if not name:
                logger.warning(f"Skipping ingestion profile without name: {entry}")
                continue

            # Find existing profile by name and is_builtin=True, knowledge_base_id=None (global)
            result = await session.execute(
                select(IngestionProfile).where(
                    (IngestionProfile.name == name)
                    & (IngestionProfile.is_builtin)
                    & (IngestionProfile.knowledge_base_id.is_(None))
                )
            )
            profile = result.scalar_one_or_none()

            if profile:
                # Update existing builtin profile
                profile.description = entry.get("description", profile.description)
                profile.config = entry.get("config", profile.config)
                profile.is_default = bool(entry.get("is_default", False))
                profile.file_types = entry.get("file_types", ["csv", "xlsx", "xls"])
                logger.info(f"Updated builtin ingestion profile: {name}")
            else:
                profile = IngestionProfile(
                    name=name,
                    description=entry.get("description"),
                    config=entry.get("config", {}),
                    is_builtin=True,
                    is_default=bool(entry.get("is_default", False)),
                    knowledge_base_id=None,  # Global profile, not KB-specific
                    owner_id=system_owner_id,
                    file_types=entry.get("file_types", ["csv", "xlsx", "xls"]),
                )
                session.add(profile)
                logger.info(f"Created builtin ingestion profile: {name}")

            await session.commit()
            await session.refresh(profile)


async def seed_from_file(path: Path) -> None:
    """
    Seed database from YAML file.

    This is the core seeding function that can be called from scripts or CLI.
    It's idempotent - running it multiple times won't create duplicates.
    """
    logger.info(f"Loading seed data from {path}")
    data = load_seed_data(path)

    users_data = data.get("users", [])
    providers_data = data.get("providers", [])
    models_data = data.get("models", [])
    assistants_data = data.get("assistants", [])
    system_configs_data = data.get("system_configs", [])
    ingestion_profiles_data = data.get("ingestion_profiles", [])

    users: dict[str, User] = {}
    if users_data:
        logger.info("Seeding users...")
        users = await ensure_users(users_data)

    # Merge created users with existing ones for owner lookups
    existing_emails = {u["email"] for u in users_data if u.get("email")}
    if existing_emails:
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.email.in_(list(existing_emails)))
            )
            for user in result.scalars().all():
                users[user.email] = user

    providers: dict[str, ModelProvider] = {}
    if providers_data:
        logger.info("Seeding providers...")
        providers = await ensure_providers(providers_data)

    models: dict[str, Model] = {}
    if models_data:
        logger.info("Seeding models...")
        models = await ensure_models(models_data, providers)

    if assistants_data:
        logger.info("Seeding assistants...")
        await ensure_assistants(assistants_data, models, users)

    if system_configs_data:
        logger.info("Seeding system configs...")
        await ensure_system_configs(system_configs_data)

    if ingestion_profiles_data:
        logger.info("Seeding builtin ingestion profiles...")
        await ensure_ingestion_profiles(ingestion_profiles_data, users)

    logger.info("Seeding completed successfully")


def get_default_seed_file() -> Path:
    """
    Get the default seed file path.

    The seed.yaml is always in the package (airbeeps/config/seed.yaml).
    This works for both development and installed modes.
    """
    # seed.yaml is always in the package, next to this module
    return Path(__file__).resolve().parent / "config" / "seed.yaml"


# One-time seeding functions (for production use)


def has_been_seeded() -> bool:
    """Check if one-time database seeding has already been done."""
    return SEED_MARKER_FILE.exists()


def mark_as_seeded() -> None:
    """Mark database as seeded by creating marker file."""
    SEED_MARKER_FILE.touch()
    logger.info(f"Created seed marker file: {SEED_MARKER_FILE}")


def reset_seed_marker() -> None:
    """
    Remove the seed marker file to allow re-seeding.

    This is useful for development/testing but should be used with caution
    as it will cause the seed to run again on next startup.
    """
    if SEED_MARKER_FILE.exists():
        SEED_MARKER_FILE.unlink()
        logger.info("Seed marker removed. Database will be seeded on next run.")
    else:
        logger.info("No seed marker found.")


async def run_initial_seed(seed_file: Path | None = None) -> bool:
    """
    Run initial database seeding if not already done (one-time execution).

    This function is designed for production use where seeding should only
    happen once on first startup. It uses a marker file to track execution.

    Args:
        seed_file: Optional path to seed file. If None, uses default location.

    Returns:
        True if seeding was performed or already done, False on error.
    """
    if has_been_seeded():
        logger.info("Database already seeded, skipping")
        return True

    if seed_file is None:
        seed_file = get_default_seed_file()

    if not seed_file.exists():
        logger.warning(f"Seed file not found at {seed_file}, skipping initial seed")
        # Still mark as seeded to avoid checking every time
        mark_as_seeded()
        return True

    try:
        logger.info("Running initial database seed...")
        await seed_from_file(seed_file)
        mark_as_seeded()
        logger.info("Initial seed completed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to seed database: {e}", exc_info=True)
        return False
