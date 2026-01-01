"""
Authentication module

This module provides authentication-related dependencies and utilities.
"""

from .dependencies import get_user_db
from .fastapi_users import (
    auth_backend,
    current_active_user,
    current_active_user_optional,
    current_superuser,
    current_user,
    fastapi_users,
)
from .manager import get_user_manager
from .oauth_service import get_oauth_service

__all__ = [
    "auth_backend",
    "current_active_user",
    "current_active_user_optional",
    "current_superuser",
    "current_user",
    "fastapi_users",
    "get_oauth_service",
    "get_user_db",
    "get_user_manager",
]
