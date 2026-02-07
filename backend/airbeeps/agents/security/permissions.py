"""
Permission system for agent tools.

Provides role-based access control for tool execution with:
- Security levels for tools (safe, moderate, dangerous)
- Role-based permissions
- Usage quotas
- Audit logging
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ToolSecurityLevel(str, Enum):
    """Security classification for tools"""

    SAFE = "safe"  # Read-only, no side effects (e.g., web search)
    MODERATE = "moderate"  # Limited side effects, scoped access (e.g., file read in specific directory)
    DANGEROUS = "dangerous"  # Potential for harm, requires explicit permission (e.g., code execution, file write)
    CRITICAL = "critical"  # System-level access, admin only (e.g., database admin, system commands)


class UserRole(str, Enum):
    """User roles for permission checking"""

    GUEST = "guest"
    USER = "user"
    POWER_USER = "power_user"
    ADMIN = "admin"
    SUPERUSER = "superuser"


@dataclass
class ToolPermission:
    """Permission configuration for a tool"""

    tool_name: str
    security_level: ToolSecurityLevel
    allowed_roles: list[UserRole] = field(default_factory=lambda: [UserRole.USER])
    requires_approval: bool = False
    max_calls_per_hour: int = 100
    max_calls_per_day: int = 1000
    cost_per_call: float = 0.0  # For budget tracking


@dataclass
class UsageQuota:
    """Usage quota tracking"""

    calls_this_hour: int = 0
    calls_today: int = 0
    hour_reset_time: datetime = field(default_factory=datetime.utcnow)
    day_reset_time: datetime = field(default_factory=datetime.utcnow)
    total_cost: float = 0.0


@dataclass
class PermissionCheckResult:
    """Result of permission check"""

    allowed: bool
    reason: str | None = None
    warning: str | None = None


# Default tool permissions
DEFAULT_TOOL_PERMISSIONS: dict[str, ToolPermission] = {
    # Safe tools - available to all users
    "knowledge_base_query": ToolPermission(
        tool_name="knowledge_base_query",
        security_level=ToolSecurityLevel.SAFE,
        allowed_roles=[
            UserRole.GUEST,
            UserRole.USER,
            UserRole.POWER_USER,
            UserRole.ADMIN,
            UserRole.SUPERUSER,
        ],
        max_calls_per_hour=200,
    ),
    "web_search": ToolPermission(
        tool_name="web_search",
        security_level=ToolSecurityLevel.SAFE,
        allowed_roles=[
            UserRole.USER,
            UserRole.POWER_USER,
            UserRole.ADMIN,
            UserRole.SUPERUSER,
        ],
        max_calls_per_hour=50,
    ),
    # Moderate tools - available to users
    "file_read": ToolPermission(
        tool_name="file_read",
        security_level=ToolSecurityLevel.MODERATE,
        allowed_roles=[
            UserRole.USER,
            UserRole.POWER_USER,
            UserRole.ADMIN,
            UserRole.SUPERUSER,
        ],
        max_calls_per_hour=100,
    ),
    "file_list": ToolPermission(
        tool_name="file_list",
        security_level=ToolSecurityLevel.SAFE,
        allowed_roles=[
            UserRole.USER,
            UserRole.POWER_USER,
            UserRole.ADMIN,
            UserRole.SUPERUSER,
        ],
        max_calls_per_hour=200,
    ),
    "analyze_data": ToolPermission(
        tool_name="analyze_data",
        security_level=ToolSecurityLevel.MODERATE,
        allowed_roles=[
            UserRole.USER,
            UserRole.POWER_USER,
            UserRole.ADMIN,
            UserRole.SUPERUSER,
        ],
        max_calls_per_hour=50,
    ),
    "list_tabular_documents": ToolPermission(
        tool_name="list_tabular_documents",
        security_level=ToolSecurityLevel.SAFE,
        allowed_roles=[
            UserRole.USER,
            UserRole.POWER_USER,
            UserRole.ADMIN,
            UserRole.SUPERUSER,
        ],
        max_calls_per_hour=100,
    ),
    # Dangerous tools - power users and above
    "execute_python": ToolPermission(
        tool_name="execute_python",
        security_level=ToolSecurityLevel.DANGEROUS,
        allowed_roles=[UserRole.POWER_USER, UserRole.ADMIN, UserRole.SUPERUSER],
        max_calls_per_hour=20,
        max_calls_per_day=100,
    ),
    "file_write": ToolPermission(
        tool_name="file_write",
        security_level=ToolSecurityLevel.DANGEROUS,
        allowed_roles=[UserRole.POWER_USER, UserRole.ADMIN, UserRole.SUPERUSER],
        max_calls_per_hour=50,
    ),
    # Critical tools - admin only
    "sql_execute": ToolPermission(
        tool_name="sql_execute",
        security_level=ToolSecurityLevel.CRITICAL,
        allowed_roles=[UserRole.ADMIN, UserRole.SUPERUSER],
        max_calls_per_hour=20,
        requires_approval=True,
    ),
    "system_command": ToolPermission(
        tool_name="system_command",
        security_level=ToolSecurityLevel.CRITICAL,
        allowed_roles=[UserRole.SUPERUSER],
        max_calls_per_hour=10,
        requires_approval=True,
    ),
}


class PermissionChecker:
    """
    Check permissions for tool execution.

    Enforces role-based access control and usage quotas.
    """

    def __init__(
        self,
        custom_permissions: dict[str, ToolPermission] | None = None,
        audit_log_enabled: bool = True,
    ):
        self.permissions = {**DEFAULT_TOOL_PERMISSIONS}
        if custom_permissions:
            self.permissions.update(custom_permissions)

        self.audit_log_enabled = audit_log_enabled
        self._usage_cache: dict[str, UsageQuota] = {}  # user_id:tool_name -> UsageQuota

    def get_tool_permission(self, tool_name: str) -> ToolPermission:
        """Get permission config for a tool"""
        if tool_name in self.permissions:
            return self.permissions[tool_name]

        # Default permission for unknown tools (moderate, user access)
        return ToolPermission(
            tool_name=tool_name,
            security_level=ToolSecurityLevel.MODERATE,
            allowed_roles=[
                UserRole.USER,
                UserRole.POWER_USER,
                UserRole.ADMIN,
                UserRole.SUPERUSER,
            ],
        )

    def get_user_role(self, user: Any) -> UserRole:
        """
        Determine user role from user object.

        Override this method to integrate with your auth system.
        """
        if user is None:
            return UserRole.GUEST

        # Check for superuser
        if hasattr(user, "is_superuser") and user.is_superuser:
            return UserRole.SUPERUSER

        # Check for admin
        if hasattr(user, "is_admin") and user.is_admin:
            return UserRole.ADMIN

        # Check for role attribute
        if hasattr(user, "role"):
            role_name = str(user.role).upper()
            try:
                return UserRole(role_name.lower())
            except ValueError:
                pass

        # Default to user
        return UserRole.USER

    async def can_use_tool(
        self,
        user: Any,
        tool_name: str,
        check_quota: bool = True,
    ) -> PermissionCheckResult:
        """
        Check if user can use a tool.

        Args:
            user: User object
            tool_name: Name of the tool
            check_quota: Whether to check usage quotas

        Returns:
            PermissionCheckResult with allowed status and reason
        """
        permission = self.get_tool_permission(tool_name)
        user_role = self.get_user_role(user)
        user_id = str(getattr(user, "id", "anonymous"))

        # Log the check
        if self.audit_log_enabled:
            logger.info(
                f"Permission check: user={user_id}, tool={tool_name}, "
                f"role={user_role.value}, security_level={permission.security_level.value}"
            )

        # Check role permission
        if user_role not in permission.allowed_roles:
            reason = (
                f"Tool '{tool_name}' requires role {[r.value for r in permission.allowed_roles]}, "
                f"but user has role '{user_role.value}'"
            )
            self._log_denial(user_id, tool_name, reason)
            return PermissionCheckResult(allowed=False, reason=reason)

        # Check if tool requires approval
        if permission.requires_approval:
            # In a full implementation, check an approval table
            # For now, superusers bypass approval
            if user_role != UserRole.SUPERUSER:
                reason = f"Tool '{tool_name}' requires admin approval"
                return PermissionCheckResult(allowed=False, reason=reason)

        # Check quotas
        if check_quota:
            quota_result = self._check_quota(user_id, tool_name, permission)
            if not quota_result.allowed:
                return quota_result

        # Check passed
        warning = None
        if permission.security_level in [
            ToolSecurityLevel.DANGEROUS,
            ToolSecurityLevel.CRITICAL,
        ]:
            warning = f"Tool '{tool_name}' has security level '{permission.security_level.value}'"

        return PermissionCheckResult(allowed=True, warning=warning)

    def _check_quota(
        self, user_id: str, tool_name: str, permission: ToolPermission
    ) -> PermissionCheckResult:
        """Check usage quota for user/tool combination"""
        cache_key = f"{user_id}:{tool_name}"
        now = datetime.utcnow()

        # Get or create quota
        if cache_key not in self._usage_cache:
            self._usage_cache[cache_key] = UsageQuota()

        quota = self._usage_cache[cache_key]

        # Reset hourly counter if needed
        if now - quota.hour_reset_time > timedelta(hours=1):
            quota.calls_this_hour = 0
            quota.hour_reset_time = now

        # Reset daily counter if needed
        if now - quota.day_reset_time > timedelta(days=1):
            quota.calls_today = 0
            quota.day_reset_time = now

        # Check hourly limit
        if quota.calls_this_hour >= permission.max_calls_per_hour:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Hourly limit reached ({permission.max_calls_per_hour} calls/hour)",
            )

        # Check daily limit
        if quota.calls_today >= permission.max_calls_per_day:
            return PermissionCheckResult(
                allowed=False,
                reason=f"Daily limit reached ({permission.max_calls_per_day} calls/day)",
            )

        return PermissionCheckResult(allowed=True)

    def record_usage(self, user_id: str, tool_name: str, cost: float = 0.0):
        """Record tool usage for quota tracking"""
        cache_key = f"{user_id}:{tool_name}"

        if cache_key not in self._usage_cache:
            self._usage_cache[cache_key] = UsageQuota()

        quota = self._usage_cache[cache_key]
        quota.calls_this_hour += 1
        quota.calls_today += 1
        quota.total_cost += cost

    def _log_denial(self, user_id: str, tool_name: str, reason: str):
        """Log permission denial for audit"""
        logger.warning(
            f"Permission denied: user={user_id}, tool={tool_name}, reason={reason}"
        )

    def get_allowed_tools(self, user: Any) -> list[str]:
        """Get list of tools the user is allowed to use"""
        user_role = self.get_user_role(user)
        allowed = []

        for tool_name, permission in self.permissions.items():
            if user_role in permission.allowed_roles:
                allowed.append(tool_name)

        return allowed

    def get_tool_security_badge(self, tool_name: str) -> dict[str, Any]:
        """Get security badge info for UI display"""
        permission = self.get_tool_permission(tool_name)

        badge_colors = {
            ToolSecurityLevel.SAFE: "green",
            ToolSecurityLevel.MODERATE: "yellow",
            ToolSecurityLevel.DANGEROUS: "orange",
            ToolSecurityLevel.CRITICAL: "red",
        }

        return {
            "level": permission.security_level.value,
            "color": badge_colors[permission.security_level],
            "requires_approval": permission.requires_approval,
            "allowed_roles": [r.value for r in permission.allowed_roles],
        }
