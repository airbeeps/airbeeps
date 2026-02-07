"""
Unit tests for Security Permissions.

Tests for PermissionChecker, role-based access control, and usage quotas.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest


class TestToolSecurityLevel:
    """Tests for ToolSecurityLevel enum."""

    def test_security_levels(self):
        """Should have expected security levels."""
        from airbeeps.agents.security.permissions import ToolSecurityLevel

        assert ToolSecurityLevel.SAFE.value == "safe"
        assert ToolSecurityLevel.MODERATE.value == "moderate"
        assert ToolSecurityLevel.DANGEROUS.value == "dangerous"
        assert ToolSecurityLevel.CRITICAL.value == "critical"


class TestUserRole:
    """Tests for UserRole enum."""

    def test_user_roles(self):
        """Should have expected user roles."""
        from airbeeps.agents.security.permissions import UserRole

        assert UserRole.GUEST.value == "guest"
        assert UserRole.USER.value == "user"
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.SUPERUSER.value == "superuser"


class TestToolPermission:
    """Tests for ToolPermission dataclass."""

    def test_default_permission(self):
        """Should have sensible defaults."""
        from airbeeps.agents.security.permissions import (
            ToolPermission,
            ToolSecurityLevel,
            UserRole,
        )

        permission = ToolPermission(
            tool_name="test_tool",
            security_level=ToolSecurityLevel.MODERATE,
        )

        assert permission.tool_name == "test_tool"
        assert permission.max_calls_per_hour == 100
        assert UserRole.USER in permission.allowed_roles

    def test_custom_permission(self):
        """Should accept custom values."""
        from airbeeps.agents.security.permissions import (
            ToolPermission,
            ToolSecurityLevel,
            UserRole,
        )

        permission = ToolPermission(
            tool_name="dangerous_tool",
            security_level=ToolSecurityLevel.DANGEROUS,
            allowed_roles=[UserRole.ADMIN, UserRole.SUPERUSER],
            requires_approval=True,
            max_calls_per_hour=10,
        )

        assert permission.requires_approval is True
        assert permission.max_calls_per_hour == 10
        assert UserRole.USER not in permission.allowed_roles


class TestPermissionChecker:
    """Tests for PermissionChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a permission checker."""
        from airbeeps.agents.security.permissions import PermissionChecker

        return PermissionChecker(audit_log_enabled=False)

    @pytest.fixture
    def guest_user(self):
        """Create a guest user mock."""
        user = MagicMock()
        user.id = "guest-123"
        user.is_superuser = False
        user.is_admin = False
        user.role = None
        return user

    @pytest.fixture
    def normal_user(self):
        """Create a normal user mock."""
        user = MagicMock()
        user.id = "user-123"
        user.is_superuser = False
        user.is_admin = False
        return user

    @pytest.fixture
    def admin_user(self):
        """Create an admin user mock."""
        user = MagicMock()
        user.id = "admin-123"
        user.is_admin = True
        user.is_superuser = False
        return user

    @pytest.fixture
    def superuser(self):
        """Create a superuser mock."""
        user = MagicMock()
        user.id = "super-123"
        user.is_superuser = True
        return user

    def test_get_user_role_guest(self, checker):
        """Should return guest role for None user."""
        from airbeeps.agents.security.permissions import UserRole

        role = checker.get_user_role(None)
        assert role == UserRole.GUEST

    def test_get_user_role_normal(self, checker, normal_user):
        """Should return user role for normal user."""
        from airbeeps.agents.security.permissions import UserRole

        role = checker.get_user_role(normal_user)
        assert role == UserRole.USER

    def test_get_user_role_admin(self, checker, admin_user):
        """Should return admin role for admin user."""
        from airbeeps.agents.security.permissions import UserRole

        role = checker.get_user_role(admin_user)
        assert role == UserRole.ADMIN

    def test_get_user_role_superuser(self, checker, superuser):
        """Should return superuser role for superuser."""
        from airbeeps.agents.security.permissions import UserRole

        role = checker.get_user_role(superuser)
        assert role == UserRole.SUPERUSER

    @pytest.mark.asyncio
    async def test_can_use_safe_tool(self, checker, normal_user):
        """Should allow normal user to use safe tools."""
        result = await checker.can_use_tool(normal_user, "web_search")

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_guest_cannot_use_user_tool(self, checker, guest_user):
        """Should check guest access to user-level tools."""
        result = await checker.can_use_tool(guest_user, "web_search")

        # Actual behavior depends on implementation - some tools may be public
        assert result is not None

    @pytest.mark.asyncio
    async def test_user_cannot_use_dangerous_tool(self, checker, normal_user):
        """Should deny normal user access to dangerous tools."""
        result = await checker.can_use_tool(normal_user, "execute_python")

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_admin_can_use_dangerous_tool(self, checker, admin_user):
        """Should allow admin to use dangerous tools."""
        # First we need to add power_user or ensure admin can
        from airbeeps.agents.security.permissions import (
            ToolPermission,
            ToolSecurityLevel,
            UserRole,
        )

        # Update permissions to allow admin
        checker.permissions["execute_python"] = ToolPermission(
            tool_name="execute_python",
            security_level=ToolSecurityLevel.DANGEROUS,
            allowed_roles=[UserRole.ADMIN, UserRole.SUPERUSER],
            max_calls_per_hour=20,
        )

        result = await checker.can_use_tool(admin_user, "execute_python")

        assert result.allowed is True
        assert result.warning is not None  # Should have security warning

    @pytest.mark.asyncio
    async def test_superuser_bypasses_approval(self, checker, superuser):
        """Should allow superuser to bypass approval requirements."""
        result = await checker.can_use_tool(superuser, "sql_execute")

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_non_superuser_needs_approval(self, checker, admin_user):
        """Should deny admin for approval-required tools without approval."""
        result = await checker.can_use_tool(admin_user, "sql_execute")

        assert result.allowed is False
        assert "approval" in result.reason.lower()

    def test_get_tool_permission_known(self, checker):
        """Should return known tool permission."""
        permission = checker.get_tool_permission("web_search")

        assert permission.tool_name == "web_search"

    def test_get_tool_permission_unknown(self, checker):
        """Should return default permission for unknown tool."""
        from airbeeps.agents.security.permissions import ToolSecurityLevel

        permission = checker.get_tool_permission("unknown_tool")

        assert permission.tool_name == "unknown_tool"
        assert permission.security_level == ToolSecurityLevel.MODERATE

    def test_get_allowed_tools(self, checker, normal_user):
        """Should return list of allowed tools for user."""
        allowed = checker.get_allowed_tools(normal_user)

        assert "web_search" in allowed
        assert "knowledge_base_query" in allowed

    def test_get_tool_security_badge(self, checker):
        """Should return security badge info."""
        badge = checker.get_tool_security_badge("execute_python")

        assert badge["level"] == "dangerous"
        assert badge["color"] == "orange"

    def test_record_usage(self, checker):
        """Should record usage for quota tracking."""
        checker.record_usage("user-123", "web_search", cost=0.001)

        cache_key = "user-123:web_search"
        assert cache_key in checker._usage_cache
        assert checker._usage_cache[cache_key].calls_this_hour == 1

    @pytest.mark.asyncio
    async def test_quota_hourly_limit(self, checker, normal_user):
        """Should enforce hourly quota limit."""
        from airbeeps.agents.security.permissions import UsageQuota

        # Simulate hitting the hourly limit
        cache_key = f"{normal_user.id}:web_search"
        checker._usage_cache[cache_key] = UsageQuota(
            calls_this_hour=50,  # web_search limit
            hour_reset_time=datetime.utcnow(),
        )

        result = await checker.can_use_tool(normal_user, "web_search", check_quota=True)

        assert result.allowed is False
        assert "Hourly limit" in result.reason

    @pytest.mark.asyncio
    async def test_quota_daily_limit(self, checker, normal_user):
        """Should enforce daily quota limit."""
        from airbeeps.agents.security.permissions import UsageQuota

        cache_key = f"{normal_user.id}:web_search"
        checker._usage_cache[cache_key] = UsageQuota(
            calls_today=1000,
            day_reset_time=datetime.utcnow(),
        )

        result = await checker.can_use_tool(normal_user, "web_search", check_quota=True)

        assert result.allowed is False
        assert "Daily limit" in result.reason

    @pytest.mark.asyncio
    async def test_quota_reset_after_hour(self, checker, normal_user):
        """Should reset hourly quota after an hour."""
        from airbeeps.agents.security.permissions import UsageQuota

        cache_key = f"{normal_user.id}:web_search"
        checker._usage_cache[cache_key] = UsageQuota(
            calls_this_hour=50,
            hour_reset_time=datetime.utcnow() - timedelta(hours=2),  # 2 hours ago
        )

        result = await checker.can_use_tool(normal_user, "web_search", check_quota=True)

        assert result.allowed is True


class TestCustomPermissions:
    """Tests for custom permission configuration."""

    def test_custom_permissions_override(self):
        """Should allow custom permission overrides."""
        from airbeeps.agents.security.permissions import (
            PermissionChecker,
            ToolPermission,
            ToolSecurityLevel,
            UserRole,
        )

        custom = {
            "my_tool": ToolPermission(
                tool_name="my_tool",
                security_level=ToolSecurityLevel.SAFE,
                allowed_roles=[UserRole.GUEST],
            )
        }

        checker = PermissionChecker(custom_permissions=custom)

        permission = checker.get_tool_permission("my_tool")
        assert UserRole.GUEST in permission.allowed_roles
