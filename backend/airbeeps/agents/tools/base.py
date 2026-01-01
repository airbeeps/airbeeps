"""
Base classes for Agent tools
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AgentToolConfig(BaseModel):
    """Tool configuration base class"""

    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentTool(ABC):
    """Agent tool base class"""

    def __init__(self, config: AgentToolConfig | None = None):
        self.config = config or AgentToolConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description"""

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute tool"""
