"""
MCP Tools Adapter - Convert MCP tools to Agent tools
"""

from typing import Any

from airbeeps.agents.tools.base import AgentTool, AgentToolConfig

from .client import MCPClient


class MCPToolAdapter(AgentTool):
    """Adapter to convert MCP tools to Agent tools"""

    def __init__(
        self,
        mcp_client: MCPClient,
        tool_info: dict[str, Any],
        config: AgentToolConfig | None = None,
    ):
        super().__init__(config)
        self.mcp_client = mcp_client
        self.tool_info = tool_info
        self._name = tool_info["name"]
        self._description = tool_info.get("description", "")
        self._input_schema = tool_info.get("inputSchema", {})

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def execute(self, **kwargs) -> Any:
        """Execute MCP tool"""
        try:
            result = await self.mcp_client.call_tool(self._name, kwargs)

            # Extract content from result
            if hasattr(result, "content"):
                # Handle list of content items
                if isinstance(result.content, list):
                    content_parts = []
                    for item in result.content:
                        if hasattr(item, "text"):
                            content_parts.append(item.text)
                        else:
                            content_parts.append(str(item))
                    return "\n".join(content_parts)
                return str(result.content)

            return str(result)

        except Exception as e:
            return f"Error executing MCP tool {self._name}: {e!s}"
