"""
Base classes for Agent tools
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolSecurityLevel(str, Enum):
    """Security classification for tools"""

    SAFE = "safe"  # Read-only, no side effects
    MODERATE = "moderate"  # Limited side effects, scoped access
    DANGEROUS = "dangerous"  # Potential for harm, requires explicit permission
    CRITICAL = "critical"  # System-level access, admin only


class AgentToolConfig(BaseModel):
    """Tool configuration base class"""

    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentTool(ABC):
    """Agent tool base class with security and schema support"""

    def __init__(self, config: AgentToolConfig | None = None):
        self.config = config or AgentToolConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (unique identifier)"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM context"""

    @property
    def security_level(self) -> ToolSecurityLevel:
        """Security level of this tool (default: MODERATE)"""
        return ToolSecurityLevel.MODERATE

    def get_input_schema(self) -> dict[str, Any]:
        """
        Get JSON Schema for tool input parameters.

        Override this method to provide schema for native function calling.

        Returns:
            JSON Schema dict describing expected parameters
        """
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def to_openai_tool(self) -> dict[str, Any]:
        """
        Convert tool to OpenAI function calling format.

        Returns:
            Dict compatible with OpenAI's tools parameter
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_input_schema(),
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """
        Convert tool to Anthropic tool use format.

        Returns:
            Dict compatible with Anthropic's tools parameter
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema(),
        }

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Tool execution result (will be converted to string for LLM)
        """
