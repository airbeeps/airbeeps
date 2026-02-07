"""
Unit tests for CodeExecutorTool.

Tests for code execution with mocked sandbox to avoid real execution.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCodeExecutorTool:
    """Tests for CodeExecutorTool class."""

    @pytest.fixture
    def mock_sandbox_result_success(self):
        """Create a successful sandbox result."""
        result = MagicMock()
        result.success = True
        result.stdout = "Hello, World!"
        result.stderr = ""
        result.return_value = None
        result.execution_time_ms = 50
        result.was_timeout = False
        result.was_memory_limit = False
        result.error_message = None
        return result

    @pytest.fixture
    def mock_sandbox_result_failure(self):
        """Create a failed sandbox result."""
        result = MagicMock()
        result.success = False
        result.stdout = ""
        result.stderr = "NameError: name 'undefined' is not defined"
        result.return_value = None
        result.execution_time_ms = 10
        result.was_timeout = False
        result.was_memory_limit = False
        result.error_message = "NameError: name 'undefined' is not defined"
        return result

    @pytest.fixture
    def mock_sandbox_result_timeout(self):
        """Create a timeout sandbox result."""
        result = MagicMock()
        result.success = False
        result.stdout = ""
        result.stderr = ""
        result.return_value = None
        result.execution_time_ms = 30000
        result.was_timeout = True
        result.was_memory_limit = False
        result.error_message = "Execution timed out"
        return result

    def test_tool_properties(self):
        """Should have correct tool properties."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox"):
            from airbeeps.agents.tools.code_executor import CodeExecutorTool
            from airbeeps.agents.tools.base import ToolSecurityLevel

            tool = CodeExecutorTool()

            assert tool.name == "execute_python"
            assert "Python" in tool.description
            assert tool.security_level == ToolSecurityLevel.DANGEROUS

    def test_get_input_schema(self):
        """Should return valid input schema."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox"):
            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            schema = tool.get_input_schema()

            assert schema["type"] == "object"
            assert "code" in schema["properties"]
            assert "code" in schema["required"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_sandbox_result_success):
        """Should return output on successful execution."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=mock_sandbox_result_success)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            result = await tool.execute('print("Hello, World!")')

            assert "Hello, World!" in result
            assert "Output:" in result

    @pytest.mark.asyncio
    async def test_execute_with_return_value(self, mock_sandbox_result_success):
        """Should show return value when present."""
        mock_sandbox_result_success.return_value = 42

        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=mock_sandbox_result_success)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            result = await tool.execute("2 + 2")

            assert "Return value: 42" in result

    @pytest.mark.asyncio
    async def test_execute_no_output(self):
        """Should indicate success when no output."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            result = MagicMock()
            result.success = True
            result.stdout = ""
            result.return_value = None
            result.execution_time_ms = 10

            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=result)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            output = await tool.execute("x = 1")

            assert "successfully" in output.lower()

    @pytest.mark.asyncio
    async def test_execute_failure(self, mock_sandbox_result_failure):
        """Should return error message on failure."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=mock_sandbox_result_failure)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            result = await tool.execute("undefined")

            assert "Error" in result
            assert "NameError" in result

    @pytest.mark.asyncio
    async def test_execute_timeout(self, mock_sandbox_result_timeout):
        """Should indicate timeout."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=mock_sandbox_result_timeout)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            result = await tool.execute("while True: pass")

            assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_memory_limit(self):
        """Should indicate memory limit exceeded."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            result = MagicMock()
            result.success = False
            result.was_timeout = False
            result.was_memory_limit = True
            result.error_message = None
            result.stderr = ""

            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=result)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            output = await tool.execute("[0] * 999999999")

            assert "memory" in output.lower()

    @pytest.mark.asyncio
    async def test_execute_with_context(self, mock_sandbox_result_success):
        """Should pass context to sandbox."""
        with patch("airbeeps.agents.tools.code_executor.CodeSandbox") as MockSandbox:
            mock_sandbox = AsyncMock()
            mock_sandbox.execute = AsyncMock(return_value=mock_sandbox_result_success)
            MockSandbox.return_value = mock_sandbox

            from airbeeps.agents.tools.code_executor import CodeExecutorTool

            tool = CodeExecutorTool()
            tool.sandbox = mock_sandbox

            context = {"x": 10, "y": 20}
            await tool.execute("print(x + y)", context=context)

            mock_sandbox.execute.assert_called_once_with("print(x + y)", context)
