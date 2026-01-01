"""
Agent Pydantic schemas for API
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .models import MCPServerTypeEnum


# Tool Registry Schemas
class LocalToolInfo(BaseModel):
    """Local tool information"""

    name: str
    description: str


class AvailableToolsResponse(BaseModel):
    """Available tools response"""

    local_tools: list[LocalToolInfo]
    mcp_servers: list[str]


# MCP Server Schemas
class MCPServerConfigBase(BaseModel):
    """Base MCP server config schema"""

    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=500)
    server_type: MCPServerTypeEnum = MCPServerTypeEnum.STDIO
    connection_config: dict[str, Any]
    is_active: bool = True
    extra_data: dict[str, Any] = Field(default_factory=dict)


class MCPServerConfigCreate(MCPServerConfigBase):
    """Create MCP server config"""


class MCPServerConfigUpdate(BaseModel):
    """Update MCP server config"""

    description: str | None = Field(None, max_length=500)
    connection_config: dict[str, Any] | None = None
    is_active: bool | None = None
    extra_data: dict[str, Any] | None = None


class MCPServerConfigResponse(MCPServerConfigBase):
    """MCP server config response"""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MCPToolInfo(BaseModel):
    """MCP tool information"""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")

    class Config:
        populate_by_name = True


class MCPServerToolsResponse(BaseModel):
    """MCP server tools response"""

    server_name: str
    tools: list[MCPToolInfo]
