"""
Tools module initialization
"""

# Import dynamic tools (classes that need dependency injection) - triggers @tool_registry.register
from . import knowledge_base  # noqa: F401
from .base import AgentTool, AgentToolConfig
from .registry import LocalToolRegistry, tool_registry

# Export all tools
__all__ = [
    "AgentTool",
    "AgentToolConfig",
    "LocalToolRegistry",
    "tool_registry",
]
