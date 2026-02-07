"""
Security layer for agent tools.

This module provides security infrastructure for safe tool execution:
- Sandboxing for code execution
- Permission checking for tool access
- Content filtering for input/output
- Input/output validation
- Tool approval workflows
"""

from .approval_service import ApprovalService, create_approval_service
from .content_filter import ContentFilter, PIIRedactor
from .permissions import PermissionChecker, ToolSecurityLevel
from .sandbox import CodeSandbox, SandboxConfig, SandboxResult
from .validator import InputValidator, OutputValidator

__all__ = [
    # Approval
    "ApprovalService",
    "create_approval_service",
    # Sandbox
    "CodeSandbox",
    "SandboxConfig",
    "SandboxResult",
    # Permissions
    "PermissionChecker",
    "ToolSecurityLevel",
    # Content
    "ContentFilter",
    "PIIRedactor",
    # Validators
    "InputValidator",
    "OutputValidator",
]
