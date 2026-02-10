"""
Unit tests for File Operation Tools.

Tests for FileReadTool, FileWriteTool, and FileListTool.
Uses temporary directories to avoid touching the real filesystem.
"""

import tempfile
from pathlib import Path

import pytest


class TestFileReadTool:
    """Tests for FileReadTool class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello, World!\nLine 2\nLine 3")

            binary_file = Path(tmpdir) / "binary.bin"
            binary_file.write_bytes(b"\x00\x01\x02\x03")

            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("Nested content")

            yield tmpdir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create FileReadTool with allowed paths."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.file_operations import FileReadTool

        config = AgentToolConfig(
            name="file_read",
            parameters={"allowed_paths": [temp_dir]},
        )
        return FileReadTool(config=config)

    def test_tool_properties(self, tool):
        """Should have correct tool properties."""
        from airbeeps.agents.tools.base import ToolSecurityLevel

        assert tool.name == "file_read"
        assert tool.security_level == ToolSecurityLevel.MODERATE

    def test_validate_path_allowed(self, tool, temp_dir):
        """Should allow paths within allowed directories."""
        is_valid, error, resolved = tool._validate_path("test.txt")

        assert is_valid is True
        assert error == ""
        assert resolved is not None

    def test_validate_path_traversal(self, tool):
        """Should block path traversal."""
        is_valid, error, resolved = tool._validate_path("../../../etc/passwd")

        assert is_valid is False
        assert "traversal" in error.lower()

    def test_validate_path_absolute(self, tool):
        """Should block paths outside allowed directories."""
        is_valid, error, resolved = tool._validate_path("/etc/passwd")

        assert is_valid is False

    def test_validate_path_no_config(self):
        """Should reject when no allowed paths configured."""
        from airbeeps.agents.tools.file_operations import FileReadTool

        tool = FileReadTool()  # No allowed paths

        is_valid, error, resolved = tool._validate_path("any.txt")

        assert is_valid is False
        assert "No allowed paths" in error

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Should read file contents."""
        result = await tool.execute(path="test.txt")

        assert "Hello, World!" in result
        assert "Line 2" in result

    @pytest.mark.asyncio
    async def test_execute_max_lines(self, tool):
        """Should limit lines when max_lines specified."""
        result = await tool.execute(path="test.txt", max_lines=2)

        assert "Hello, World!" in result
        assert "truncated" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_binary_file(self, tool):
        """Should handle binary files."""
        result = await tool.execute(path="binary.bin")

        # Tool may return raw content, binary indicator, or hex representation
        assert result is not None
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        """Should handle missing files."""
        result = await tool.execute(path="nonexistent.txt")

        assert "Error" in result
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_nested_file(self, tool):
        """Should read nested files."""
        result = await tool.execute(path="subdir/nested.txt")

        assert "Nested content" in result


class TestFileWriteTool:
    """Tests for FileWriteTool class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create FileWriteTool with allowed paths."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.file_operations import FileWriteTool

        config = AgentToolConfig(
            name="file_write",
            parameters={"allowed_paths": [temp_dir]},
        )
        return FileWriteTool(config=config)

    def test_tool_properties(self, tool):
        """Should have correct tool properties."""
        from airbeeps.agents.tools.base import ToolSecurityLevel

        assert tool.name == "file_write"
        assert tool.security_level == ToolSecurityLevel.DANGEROUS

    @pytest.mark.asyncio
    async def test_execute_create_new_file(self, tool, temp_dir):
        """Should create new file."""
        result = await tool.execute(path="new_file.txt", content="New content")

        assert "Successfully" in result

        # Verify file was created
        file_path = Path(temp_dir) / "new_file.txt"
        assert file_path.exists()
        assert file_path.read_text() == "New content"

    @pytest.mark.asyncio
    async def test_execute_overwrite(self, tool, temp_dir):
        """Should overwrite existing file."""
        file_path = Path(temp_dir) / "existing.txt"
        file_path.write_text("Old content")

        result = await tool.execute(path="existing.txt", content="New content")

        assert "Successfully" in result
        assert file_path.read_text() == "New content"

    @pytest.mark.asyncio
    async def test_execute_append(self, tool, temp_dir):
        """Should append to existing file."""
        file_path = Path(temp_dir) / "append.txt"
        file_path.write_text("Initial ")

        result = await tool.execute(
            path="append.txt", content="appended", mode="append"
        )

        assert "Successfully" in result
        assert file_path.read_text() == "Initial appended"

    @pytest.mark.asyncio
    async def test_execute_creates_directories(self, tool, temp_dir):
        """Should create parent directories."""
        result = await tool.execute(path="nested/deep/file.txt", content="Deep content")

        assert "Successfully" in result

        file_path = Path(temp_dir) / "nested/deep/file.txt"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_execute_path_traversal_blocked(self, tool):
        """Should block path traversal."""
        result = await tool.execute(path="../outside.txt", content="Malicious")

        assert "Error" in result
        assert "traversal" in result.lower()


class TestFileListTool:
    """Tests for FileListTool class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with test structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("content")
            Path(tmpdir, "file2.py").write_text("code")
            subdir = Path(tmpdir, "subdir")
            subdir.mkdir()
            Path(subdir, "nested.txt").write_text("nested")
            yield tmpdir

    @pytest.fixture
    def tool(self, temp_dir):
        """Create FileListTool with allowed paths."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.file_operations import FileListTool

        config = AgentToolConfig(
            name="file_list",
            parameters={"allowed_paths": [temp_dir]},
        )
        return FileListTool(config=config)

    def test_tool_properties(self, tool):
        """Should have correct tool properties."""
        from airbeeps.agents.tools.base import ToolSecurityLevel

        assert tool.name == "file_list"
        assert tool.security_level == ToolSecurityLevel.SAFE

    @pytest.mark.asyncio
    async def test_execute_list_directory(self, tool):
        """Should list directory contents."""
        result = await tool.execute(path=".")

        assert "file1.txt" in result
        assert "file2.py" in result
        assert "[DIR]" in result  # subdir

    @pytest.mark.asyncio
    async def test_execute_with_pattern(self, tool):
        """Should filter with glob pattern."""
        result = await tool.execute(path=".", pattern="*.py")

        assert "file2.py" in result
        assert "file1.txt" not in result

    @pytest.mark.asyncio
    async def test_execute_recursive(self, tool):
        """Should list recursively when specified."""
        result = await tool.execute(path=".", recursive=True)

        assert "nested.txt" in result

    @pytest.mark.asyncio
    async def test_execute_not_found(self, tool):
        """Should handle missing directory."""
        result = await tool.execute(path="nonexistent")

        assert "Error" in result
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_path_traversal_blocked(self, tool):
        """Should block path traversal."""
        result = await tool.execute(path="../outside")

        assert "Error" in result
