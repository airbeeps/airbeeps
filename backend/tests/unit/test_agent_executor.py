"""
Unit tests for Agent Execution Engine.

Tests for tool parsing, tool execution, and agent loop logic.
"""

from unittest.mock import AsyncMock, Mock

import pytest


class TestToolCallParsing:
    """Tests for parsing tool calls from LLM responses."""

    def setup_method(self):
        """Create a fresh executor for each test."""
        from airbeeps.agents.executor import AgentExecutionEngine

        # Create executor without initialization
        self.executor = AgentExecutionEngine.__new__(AgentExecutionEngine)
        self.executor.tools = []

    def test_parse_simple_json_tool_call(self):
        """Should parse a simple JSON tool call."""
        content = '{"tool": "calculator", "input": {"expression": "2+2"}}'
        result = self.executor._parse_tool_call(content)

        assert result is not None
        assert result["tool"] == "calculator"
        assert result["input"] == {"expression": "2+2"}

    def test_parse_json_in_markdown_code_block(self):
        """Should parse JSON from markdown code blocks."""
        content = """Here's what I'll do:
```json
{"tool": "search", "input": {"query": "weather"}}
```
"""
        result = self.executor._parse_tool_call(content)

        assert result is not None
        assert result["tool"] == "search"
        assert result["input"] == {"query": "weather"}

    def test_parse_json_embedded_in_text(self):
        """Should extract JSON object from surrounding text."""
        content = 'Let me use a tool: {"tool": "translate", "input": {"text": "hello"}} to help you.'
        result = self.executor._parse_tool_call(content)

        assert result is not None
        assert result["tool"] == "translate"

    def test_parse_non_tool_json_returns_none(self):
        """Should return None for JSON without tool key."""
        content = '{"name": "test", "value": 123}'
        result = self.executor._parse_tool_call(content)

        assert result is None

    def test_parse_invalid_json_returns_none(self):
        """Should return None for invalid JSON."""
        content = "This is just plain text without any JSON"
        result = self.executor._parse_tool_call(content)

        assert result is None

    def test_parse_malformed_json_returns_none(self):
        """Should return None for malformed JSON."""
        content = '{"tool": "test", "input": }'
        result = self.executor._parse_tool_call(content)

        assert result is None

    def test_parse_nested_json_input(self):
        """Should handle nested JSON in input."""
        content = '{"tool": "api", "input": {"data": {"nested": {"key": "value"}}}}'
        result = self.executor._parse_tool_call(content)

        assert result is not None
        assert result["tool"] == "api"
        assert result["input"]["data"]["nested"]["key"] == "value"

    def test_parse_empty_input(self):
        """Should handle tool call with empty input."""
        content = '{"tool": "simple_tool", "input": {}}'
        result = self.executor._parse_tool_call(content)

        assert result is not None
        assert result["tool"] == "simple_tool"
        assert result["input"] == {}


class TestToolsDescription:
    """Tests for tools description building."""

    def setup_method(self):
        """Create executor with mock tools."""
        from airbeeps.agents.executor import AgentExecutionEngine

        self.executor = AgentExecutionEngine.__new__(AgentExecutionEngine)

        # Create mock tools
        mock_tool_1 = Mock()
        mock_tool_1.name = "calculator"
        mock_tool_1.description = "Performs mathematical calculations"

        mock_tool_2 = Mock()
        mock_tool_2.name = "search"
        mock_tool_2.description = "Searches the web for information"

        self.executor.tools = [mock_tool_1, mock_tool_2]

    def test_build_tools_description_with_tools(self):
        """Should build description including all tools."""
        description = self.executor._build_tools_description()

        assert "calculator" in description
        assert "Performs mathematical calculations" in description
        assert "search" in description
        assert "Searches the web for information" in description

    def test_build_tools_description_includes_format_instructions(self):
        """Should include JSON format instructions."""
        description = self.executor._build_tools_description()

        assert '"tool"' in description
        assert '"input"' in description
        assert "JSON" in description

    def test_build_tools_description_no_tools(self):
        """Should return empty string when no tools."""
        self.executor.tools = []
        description = self.executor._build_tools_description()

        assert description == ""


class TestSystemPromptBuilding:
    """Tests for system prompt construction."""

    def setup_method(self):
        """Create executor with mock assistant."""
        from airbeeps.agents.executor import AgentExecutionEngine

        self.executor = AgentExecutionEngine.__new__(AgentExecutionEngine)

        # Mock assistant
        self.executor.assistant = Mock()
        self.executor.assistant.system_prompt = "You are a helpful assistant."
        self.executor.system_prompt_override = None
        self.executor.tools = []

    def test_build_system_prompt_uses_assistant_prompt(self):
        """Should use assistant's system prompt."""
        prompt = self.executor._build_system_prompt()

        assert "You are a helpful assistant." in prompt

    def test_build_system_prompt_override_takes_precedence(self):
        """System prompt override should take precedence."""
        self.executor.system_prompt_override = "Custom override prompt"
        prompt = self.executor._build_system_prompt()

        assert "Custom override prompt" in prompt
        assert "You are a helpful assistant." not in prompt

    def test_build_system_prompt_default_when_none(self):
        """Should use default when no prompt configured."""
        self.executor.assistant.system_prompt = None
        prompt = self.executor._build_system_prompt()

        assert "helpful AI agent" in prompt

    def test_build_system_prompt_includes_tools(self):
        """Should include tools description when tools exist."""
        mock_tool = Mock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        self.executor.tools = [mock_tool]

        prompt = self.executor._build_system_prompt()

        assert "test_tool" in prompt
        assert "A test tool" in prompt


class TestToolExecution:
    """Tests for tool execution logic."""

    def setup_method(self):
        """Create executor with mock tool."""
        from airbeeps.agents.executor import AgentExecutionEngine

        self.executor = AgentExecutionEngine.__new__(AgentExecutionEngine)

        # Create mock tool
        self.mock_tool = Mock()
        self.mock_tool.name = "calculator"
        self.mock_tool.execute = AsyncMock(return_value="Result: 4")

        self.executor.tools = [self.mock_tool]

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """Should execute tool and return result."""
        result = await self.executor._execute_tool("calculator", {"expression": "2+2"})

        assert result == "Result: 4"
        self.mock_tool.execute.assert_called_once_with(expression="2+2")

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        """Should return error for unknown tool."""
        result = await self.executor._execute_tool("unknown_tool", {})

        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_error_handling(self):
        """Should handle tool execution errors gracefully."""
        self.mock_tool.execute = AsyncMock(side_effect=Exception("Tool crashed"))

        result = await self.executor._execute_tool("calculator", {})

        assert "error" in result.lower()
        assert "Tool crashed" in result


class TestMaxIterations:
    """Tests for iteration limit handling."""

    def test_max_iterations_default(self):
        """Should use assistant's configured max iterations."""
        from airbeeps.agents.executor import AgentExecutionEngine

        mock_assistant = Mock()
        mock_assistant.agent_max_iterations = 5

        executor = AgentExecutionEngine(assistant=mock_assistant)

        assert executor.max_iterations == 5

    def test_max_iterations_fallback(self):
        """Should fallback to 10 when not configured."""
        from airbeeps.agents.executor import AgentExecutionEngine

        mock_assistant = Mock()
        mock_assistant.agent_max_iterations = None

        executor = AgentExecutionEngine(assistant=mock_assistant)

        assert executor.max_iterations == 10
