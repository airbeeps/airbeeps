"""
File Operations tool for agents.

Provides scoped file read/write operations within allowed directories only.
"""

import logging
import os
from pathlib import Path
from typing import Any

from .base import AgentTool, AgentToolConfig, ToolSecurityLevel
from .registry import tool_registry

logger = logging.getLogger(__name__)


@tool_registry.register
class FileReadTool(AgentTool):
    """
    Read files from allowed directories.

    Only reads from explicitly configured allowed paths.
    """

    def __init__(self, config: AgentToolConfig | None = None):
        super().__init__(config)

        # Get allowed paths from config (must be set by admin)
        self.allowed_paths = self.config.parameters.get("allowed_paths", [])
        self.max_file_size = self.config.parameters.get(
            "max_file_size", 1024 * 1024
        )  # 1MB default

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "Read contents of a file. Only files within allowed directories can be read. "
            "Supports text files. Binary files will show a preview."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.MODERATE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read (relative to allowed directories)",
                },
                "encoding": {
                    "type": "string",
                    "description": "Text encoding (default: utf-8)",
                    "default": "utf-8",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (default: all)",
                },
            },
            "required": ["path"],
        }

    def _validate_path(self, path: str) -> tuple[bool, str, Path | None]:
        """
        Validate that path is within allowed directories.

        Security: Uses Path.is_relative_to() to prevent prefix collision attacks.
        e.g., prevents C:\\allowed_bypass from matching when C:\\allowed is allowed.

        Returns (is_valid, error_message, resolved_path)
        """
        if not self.allowed_paths:
            return False, "No allowed paths configured for file operations", None

        # Normalize the path
        try:
            # Convert to Path object
            file_path = Path(path)

            # Check for path traversal attempts in the raw string
            if ".." in path:
                return False, "Path traversal not allowed", None

            # Try to resolve against each allowed path
            for allowed in self.allowed_paths:
                allowed_path = Path(allowed).resolve()

                # Try both absolute and relative paths
                candidates = [
                    allowed_path / file_path,  # Relative to allowed
                    file_path if file_path.is_absolute() else None,  # Absolute
                ]

                for candidate in candidates:
                    if candidate is None:
                        continue

                    try:
                        resolved = candidate.resolve()

                        # Use is_relative_to() for secure path containment check
                        # This prevents prefix collision attacks like:
                        # allowed: C:\allowed, attack: C:\allowed_bypass
                        if resolved.is_relative_to(allowed_path):
                            # Additional check: ensure no symlink escape
                            # The resolved path should still be under allowed after resolution
                            if resolved.is_relative_to(allowed_path.resolve()):
                                return True, "", resolved
                    except (ValueError, OSError):
                        # is_relative_to raises ValueError if not relative
                        continue

            return False, f"Path '{path}' is outside allowed directories", None

        except Exception as e:
            return False, f"Invalid path: {e}", None

    async def execute(
        self,
        path: str,
        encoding: str = "utf-8",
        max_lines: int | None = None,
    ) -> str:
        """Read file contents"""
        # Validate path
        is_valid, error_msg, resolved_path = self._validate_path(path)
        if not is_valid:
            return f"Error: {error_msg}"

        try:
            # Check if file exists
            if not resolved_path.exists():
                return f"Error: File not found: {path}"

            if not resolved_path.is_file():
                return f"Error: Not a file: {path}"

            # Check file size
            file_size = resolved_path.stat().st_size
            if file_size > self.max_file_size:
                return (
                    f"Error: File too large ({file_size / 1024 / 1024:.2f}MB). "
                    f"Maximum allowed: {self.max_file_size / 1024 / 1024:.2f}MB"
                )

            # Read file
            try:
                content = resolved_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                # Try to read as binary and show preview
                binary_content = resolved_path.read_bytes()[:500]
                return (
                    f"Binary file detected. First 500 bytes (hex):\n"
                    f"{binary_content.hex()}"
                )

            # Apply max_lines limit
            if max_lines:
                lines = content.split("\n")
                if len(lines) > max_lines:
                    content = "\n".join(lines[:max_lines])
                    content += f"\n\n... (truncated, showing {max_lines} of {len(lines)} lines)"

            return f"File: {path}\n---\n{content}"

        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            logger.error(f"File read error: {e}")
            return f"Error reading file: {e!s}"


@tool_registry.register
class FileWriteTool(AgentTool):
    """
    Write files to allowed directories.

    Only writes to explicitly configured allowed paths.
    """

    def __init__(self, config: AgentToolConfig | None = None):
        super().__init__(config)

        # Get allowed paths from config (must be set by admin)
        self.allowed_paths = self.config.parameters.get("allowed_paths", [])
        self.max_file_size = self.config.parameters.get(
            "max_file_size", 1024 * 1024
        )  # 1MB

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Only writes to allowed directories. "
            "Can create new files or overwrite existing ones."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.DANGEROUS

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write (relative to allowed directories)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "description": "Write mode: overwrite or append (default: overwrite)",
                    "default": "overwrite",
                },
                "encoding": {
                    "type": "string",
                    "description": "Text encoding (default: utf-8)",
                    "default": "utf-8",
                },
            },
            "required": ["path", "content"],
        }

    def _validate_path(self, path: str) -> tuple[bool, str, Path | None]:
        """
        Validate that path is within allowed directories.

        Security: Uses Path.is_relative_to() to prevent prefix collision attacks.
        """
        if not self.allowed_paths:
            return False, "No allowed paths configured for file operations", None

        try:
            file_path = Path(path)

            if ".." in path:
                return False, "Path traversal not allowed", None

            for allowed in self.allowed_paths:
                allowed_path = Path(allowed).resolve()
                resolved = (allowed_path / file_path).resolve()

                # Use is_relative_to() for secure containment check
                try:
                    if resolved.is_relative_to(allowed_path):
                        return True, "", resolved
                except ValueError:
                    continue

            return False, f"Path '{path}' is outside allowed directories", None

        except Exception as e:
            return False, f"Invalid path: {e}", None

    async def execute(
        self,
        path: str,
        content: str,
        mode: str = "overwrite",
        encoding: str = "utf-8",
    ) -> str:
        """Write content to file"""
        # Validate path
        is_valid, error_msg, resolved_path = self._validate_path(path)
        if not is_valid:
            return f"Error: {error_msg}"

        # Check content size
        content_size = len(content.encode(encoding))
        if content_size > self.max_file_size:
            return (
                f"Error: Content too large ({content_size / 1024 / 1024:.2f}MB). "
                f"Maximum allowed: {self.max_file_size / 1024 / 1024:.2f}MB"
            )

        try:
            # Create parent directories if needed
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            if mode == "append":
                with open(resolved_path, "a", encoding=encoding) as f:
                    f.write(content)
                action = "appended to"
            else:
                resolved_path.write_text(content, encoding=encoding)
                action = "written to"

            file_size = resolved_path.stat().st_size
            return f"Successfully {action} {path} ({file_size} bytes)"

        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            logger.error(f"File write error: {e}")
            return f"Error writing file: {e!s}"


@tool_registry.register
class FileListTool(AgentTool):
    """
    List files in allowed directories.
    """

    def __init__(self, config: AgentToolConfig | None = None):
        super().__init__(config)
        self.allowed_paths = self.config.parameters.get("allowed_paths", [])

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def description(self) -> str:
        return "List files and directories in an allowed path."

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (relative to allowed directories)",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py')",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List files recursively",
                    "default": False,
                },
            },
        }

    def _validate_path(self, path: str) -> tuple[bool, str, Path | None]:
        """
        Validate path is within allowed directories.

        Security: Uses Path.is_relative_to() to prevent prefix collision attacks.
        """
        if not self.allowed_paths:
            return False, "No allowed paths configured", None

        try:
            dir_path = Path(path) if path and path != "." else Path(".")

            if ".." in path:
                return False, "Path traversal not allowed", None

            for allowed in self.allowed_paths:
                allowed_path = Path(allowed).resolve()
                resolved = (allowed_path / dir_path).resolve()

                # Use is_relative_to() for secure containment check
                try:
                    if resolved.is_relative_to(allowed_path):
                        return True, "", resolved
                except ValueError:
                    continue

            return False, f"Path '{path}' is outside allowed directories", None

        except Exception as e:
            return False, f"Invalid path: {e}", None

    async def execute(
        self,
        path: str = ".",
        pattern: str | None = None,
        recursive: bool = False,
    ) -> str:
        """List directory contents"""
        is_valid, error_msg, resolved_path = self._validate_path(path)
        if not is_valid:
            return f"Error: {error_msg}"

        try:
            if not resolved_path.exists():
                return f"Error: Directory not found: {path}"

            if not resolved_path.is_dir():
                return f"Error: Not a directory: {path}"

            # List files
            if pattern:
                if recursive:
                    files = list(resolved_path.rglob(pattern))
                else:
                    files = list(resolved_path.glob(pattern))
            else:
                if recursive:
                    files = list(resolved_path.rglob("*"))
                else:
                    files = list(resolved_path.iterdir())

            # Format output
            lines = [f"Directory: {path}"]
            lines.append("-" * 40)

            dirs = []
            regular_files = []

            for f in sorted(files):
                rel_path = f.relative_to(resolved_path)
                if f.is_dir():
                    dirs.append(f"  [DIR]  {rel_path}/")
                else:
                    size = f.stat().st_size
                    size_str = (
                        f"{size:,} bytes" if size < 1024 else f"{size / 1024:.1f} KB"
                    )
                    regular_files.append(f"  [FILE] {rel_path} ({size_str})")

            lines.extend(dirs)
            lines.extend(regular_files)
            lines.append(
                f"\nTotal: {len(dirs)} directories, {len(regular_files)} files"
            )

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"File list error: {e}")
            return f"Error listing directory: {e!s}"
