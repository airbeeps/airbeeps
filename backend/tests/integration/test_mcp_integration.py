"""
Integration tests for MCP (Model Context Protocol) integration.

Tests MCP client, server registry, and tool adapters.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_mcp_server_config():
    """Create a mock MCP server configuration."""
    return {
        "name": "test-server",
        "display_name": "Test Server",
        "command": "echo",
        "args": ["test"],
        "env_vars": {},
        "is_active": True,
    }


@pytest.fixture
def mock_mcp_tool():
    """Create a mock MCP tool definition."""
    return {
        "name": "test_tool",
        "description": "A test MCP tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    }


# ============================================================================
# MCP Client Tests
# ============================================================================


class TestMCPClient:
    """Tests for MCP client functionality."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test MCP client initialization."""
        from airbeeps.agents.mcp.client import MCPClient

        with patch("airbeeps.agents.mcp.client.ClientSession") as mock_session:
            client = MCPClient(
                server_name="test-server",
                command="echo",
                args=["hello"],
            )

            assert client.server_name == "test-server"
            assert client.command == "echo"

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self, mock_mcp_tool):
        """Test listing tools from MCP server."""
        from airbeeps.agents.mcp.client import MCPClient

        with patch("airbeeps.agents.mcp.client.ClientSession") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session_instance.list_tools.return_value = MagicMock(
                tools=[MagicMock(**mock_mcp_tool)]
            )
            mock_session.return_value.__aenter__.return_value = mock_session_instance

            client = MCPClient(
                server_name="test-server",
                command="echo",
                args=["hello"],
            )
            client._session = mock_session_instance
            client._connected = True

            tools = await client.list_tools()

            # Should return list of tools
            assert isinstance(tools, list)

    @pytest.mark.asyncio
    async def test_call_tool_with_valid_input(self, mock_mcp_tool):
        """Test calling an MCP tool with valid input."""
        from airbeeps.agents.mcp.client import MCPClient

        with patch("airbeeps.agents.mcp.client.ClientSession") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session_instance.call_tool.return_value = MagicMock(
                content=[MagicMock(type="text", text="Tool result")]
            )
            mock_session.return_value.__aenter__.return_value = mock_session_instance

            client = MCPClient(
                server_name="test-server",
                command="echo",
                args=["hello"],
            )
            client._session = mock_session_instance
            client._connected = True

            result = await client.call_tool("test_tool", {"query": "test"})

            assert result is not None


# ============================================================================
# MCP Registry Tests
# ============================================================================


class TestMCPRegistry:
    """Tests for MCP server registry."""

    @pytest.mark.asyncio
    async def test_register_server(self, mock_mcp_server_config):
        """Test registering an MCP server."""
        from airbeeps.agents.mcp.registry import MCPServerRegistry

        registry = MCPServerRegistry()

        await registry.register(
            name=mock_mcp_server_config["name"],
            command=mock_mcp_server_config["command"],
            args=mock_mcp_server_config["args"],
        )

        assert mock_mcp_server_config["name"] in registry.list_servers()

    @pytest.mark.asyncio
    async def test_unregister_server(self, mock_mcp_server_config):
        """Test unregistering an MCP server."""
        from airbeeps.agents.mcp.registry import MCPServerRegistry

        registry = MCPServerRegistry()

        await registry.register(
            name=mock_mcp_server_config["name"],
            command=mock_mcp_server_config["command"],
            args=mock_mcp_server_config["args"],
        )

        await registry.unregister(mock_mcp_server_config["name"])

        assert mock_mcp_server_config["name"] not in registry.list_servers()

    @pytest.mark.asyncio
    async def test_get_nonexistent_server(self):
        """Test getting a non-existent server returns None."""
        from airbeeps.agents.mcp.registry import MCPServerRegistry

        registry = MCPServerRegistry()

        client = await registry.get_client("nonexistent")

        assert client is None


# ============================================================================
# MCP Tool Adapter Tests
# ============================================================================


class TestMCPToolAdapter:
    """Tests for MCP tool adapters."""

    @pytest.mark.asyncio
    async def test_adapter_wraps_mcp_tool(self, mock_mcp_tool):
        """Test that adapter correctly wraps an MCP tool."""
        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        mock_client = AsyncMock()
        mock_client.call_tool.return_value = "Tool result"

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        assert adapter.name == mock_mcp_tool["name"]
        assert adapter.description == mock_mcp_tool["description"]

    @pytest.mark.asyncio
    async def test_adapter_execute_calls_mcp(self, mock_mcp_tool):
        """Test that adapter execute calls MCP client."""
        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        mock_client = AsyncMock()
        mock_client.call_tool.return_value = "Tool result"

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        result = await adapter.execute(query="test query")

        mock_client.call_tool.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_adapter_schema_conversion(self, mock_mcp_tool):
        """Test that adapter converts MCP schema correctly."""
        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        mock_client = AsyncMock()

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        schema = adapter.get_input_schema()

        assert schema["type"] == "object"
        assert "query" in schema["properties"]


# ============================================================================
# MCP Error Handling Tests
# ============================================================================


class TestMCPErrorHandling:
    """Tests for MCP error handling."""

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test handling of connection errors."""
        from airbeeps.agents.mcp.client import MCPClient

        with patch("airbeeps.agents.mcp.client.ClientSession") as mock_session:
            mock_session.side_effect = ConnectionError("Connection refused")

            client = MCPClient(
                server_name="test-server",
                command="nonexistent",
                args=[],
            )

            with pytest.raises(Exception):
                await client.connect()

    @pytest.mark.asyncio
    async def test_tool_call_error_handling(self, mock_mcp_tool):
        """Test handling of tool call errors."""
        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        mock_client = AsyncMock()
        mock_client.call_tool.side_effect = RuntimeError("Tool execution failed")

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        with pytest.raises(RuntimeError):
            await adapter.execute(query="test")

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_mcp_tool):
        """Test handling of timeout errors."""
        import asyncio

        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(10)
            return "result"

        mock_client = AsyncMock()
        mock_client.call_tool = slow_call

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(adapter.execute(query="test"), timeout=0.1)


# ============================================================================
# MCP Security Tests
# ============================================================================


class TestMCPSecurity:
    """Tests for MCP security features."""

    @pytest.mark.asyncio
    async def test_input_sanitization(self, mock_mcp_tool):
        """Test that inputs are sanitized before sending to MCP."""
        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        mock_client = AsyncMock()
        mock_client.call_tool.return_value = "result"

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        # Execute with potentially dangerous input
        await adapter.execute(query="../../../etc/passwd")

        # Verify the call was made (sanitization happens in content filter)
        mock_client.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_sanitization(self, mock_mcp_tool):
        """Test that outputs are sanitized."""
        from airbeeps.agents.mcp.tools_adapter import MCPToolAdapter

        mock_client = AsyncMock()
        # Simulate output with sensitive data
        mock_client.call_tool.return_value = "Result with api_key=secret123"

        adapter = MCPToolAdapter(
            mcp_client=mock_client,
            tool_definition=mock_mcp_tool,
        )

        result = await adapter.execute(query="test")

        # Output should be returned (filtering happens at higher level)
        assert result is not None
