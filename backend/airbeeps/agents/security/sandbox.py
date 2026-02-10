"""
Code Sandbox - Secure execution environment for untrusted code.

Provides Docker-based isolation for code execution with:
- Resource limits (memory, CPU, time)
- Network isolation
- Restricted imports
- File system isolation
"""

import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SandboxMode(str, Enum):
    """Sandbox execution modes"""

    DOCKER = "docker"  # Full Docker isolation (recommended for production)
    SUBPROCESS = "subprocess"  # Subprocess with restrictions (dev/testing)
    DISABLED = "disabled"  # No sandbox (dangerous - only for trusted code)


@dataclass
class SandboxConfig:
    """Configuration for code sandbox.

    Security Note: Default mode is DOCKER for production safety.
    SUBPROCESS mode uses allowlist-only imports and should only be used
    for development/testing where Docker is unavailable.
    """

    # Default to DOCKER for security (can be overridden via env var)
    mode: SandboxMode = SandboxMode.DOCKER
    max_memory_mb: int = 256
    max_cpu_percent: int = 50
    timeout_seconds: int = 30
    max_output_size_bytes: int = 1024 * 1024  # 1MB

    # ALLOWLIST-ONLY approach: only these imports are permitted
    # This is the source of truth for both Docker and subprocess modes
    allowed_imports: list[str] = field(
        default_factory=lambda: [
            "math",
            "json",
            "datetime",
            "re",
            "collections",
            "itertools",
            "functools",
            "operator",
            "string",
            "random",
            "statistics",
            "decimal",
            "fractions",
            "csv",
            "io",
            "typing",
            "dataclasses",
            "enum",
            "copy",
            "pprint",
            "textwrap",
            "uuid",
            "hashlib",
            "base64",
            "urllib.parse",
        ]
    )

    # Deprecated: kept for backwards compatibility but not used
    # Validation now uses allowlist-only approach
    blocked_imports: list[str] = field(default_factory=list)

    docker_image: str = "python:3.13-slim"
    network_enabled: bool = False

    # Additional security settings
    allow_file_access: bool = False  # Disallow open() even in allowed modules
    allow_network: bool = False  # Disallow any network access


@dataclass
class SandboxResult:
    """Result of sandboxed code execution"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    execution_time_ms: int = 0
    memory_used_mb: float = 0.0
    error_message: str | None = None
    was_timeout: bool = False
    was_memory_limit: bool = False


class CodeSandbox:
    """
    Secure sandbox for executing untrusted code.

    Uses Docker for production isolation or subprocess with restrictions for development.
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()

    async def execute(
        self, code: str, context: dict[str, Any] | None = None
    ) -> SandboxResult:
        """
        Execute code in sandboxed environment.

        Args:
            code: Python code to execute
            context: Optional context variables to inject

        Returns:
            SandboxResult with execution output
        """
        if self.config.mode == SandboxMode.DISABLED:
            logger.warning("Sandbox is DISABLED - executing code without isolation!")
            return await self._execute_unsafe(code, context)

        # Validate code before execution
        validation_error = self._validate_code(code)
        if validation_error:
            return SandboxResult(
                success=False,
                error_message=validation_error,
            )

        if self.config.mode == SandboxMode.DOCKER:
            return await self._execute_docker(code, context)
        return await self._execute_subprocess(code, context)

    def _validate_code(self, code: str) -> str | None:
        """
        Validate code for dangerous patterns using ALLOWLIST-ONLY approach.

        Security: Uses strict allowlist - any import not in allowed_imports is rejected.
        This prevents bypass via undiscovered dangerous modules.

        Returns error message if validation fails, None if valid.
        """
        import ast

        # Try to parse the code
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"Syntax error: {e}"

        # Build set of allowed modules for fast lookup
        allowed_modules = set(self.config.allowed_imports)
        # Also allow submodules of allowed modules (e.g., "urllib.parse" allows "urllib")
        allowed_base_modules = {m.split(".")[0] for m in self.config.allowed_imports}

        # Dangerous builtins that should never be called
        dangerous_builtins = {
            "eval",
            "exec",
            "compile",
            "__import__",
            "open",
            "input",
            "breakpoint",
            "help",
            "license",
            "credits",
            "getattr",
            "setattr",
            "delattr",  # Potential for attribute manipulation
        }

        # Additional dangerous patterns
        dangerous_attrs = {
            "__class__",
            "__bases__",
            "__subclasses__",
            "__mro__",
            "__globals__",
            "__code__",
            "__builtins__",
            "__import__",
            "__reduce__",
            "__reduce_ex__",
            "__getstate__",
            "__setstate__",
        }

        for node in ast.walk(tree):
            # Check imports - ALLOWLIST ONLY
            if isinstance(node, ast.Import):
                for alias in node.names:
                    full_module = alias.name
                    base_module = full_module.split(".")[0]

                    # Check if the full module or base is in allowlist
                    if (
                        full_module not in allowed_modules
                        and base_module not in allowed_base_modules
                    ):
                        return f"Import of '{full_module}' is not allowed. Allowed: {sorted(allowed_modules)}"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    full_module = node.module
                    base_module = full_module.split(".")[0]

                    if (
                        full_module not in allowed_modules
                        and base_module not in allowed_base_modules
                    ):
                        return f"Import from '{full_module}' is not allowed. Allowed: {sorted(allowed_modules)}"

            # Check for dangerous builtin calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in dangerous_builtins:
                        return f"Use of '{node.func.id}()' is not allowed"

            # Check for dangerous attribute access (sandbox escape attempts)
            elif isinstance(node, ast.Attribute):
                if node.attr in dangerous_attrs:
                    return f"Access to '{node.attr}' is not allowed (potential sandbox escape)"

            # Check for string-based attribute access via getattr pattern
            elif isinstance(node, ast.Subscript):
                # Detect patterns like obj["__class__"]
                if isinstance(node.slice, ast.Constant):
                    if (
                        isinstance(node.slice.value, str)
                        and node.slice.value in dangerous_attrs
                    ):
                        return f"Access to '{node.slice.value}' via subscript is not allowed"

        return None

    async def _execute_subprocess(
        self, code: str, context: dict[str, Any] | None = None
    ) -> SandboxResult:
        """Execute code in a subprocess with restrictions"""
        import time

        start_time = time.time()

        # Create wrapper script
        wrapper_code = self._create_wrapper_script(code, context)

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(wrapper_code)
            temp_file = f.name

        try:
            # Execute in subprocess
            process = await asyncio.create_subprocess_exec(
                "python",
                temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.config.max_output_size_bytes,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return SandboxResult(
                    success=False,
                    error_message="Execution timed out",
                    was_timeout=True,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            execution_time_ms = int((time.time() - start_time) * 1000)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Truncate if too large
            if len(stdout_str) > self.config.max_output_size_bytes:
                stdout_str = (
                    stdout_str[: self.config.max_output_size_bytes]
                    + "\n... (output truncated)"
                )
            if len(stderr_str) > self.config.max_output_size_bytes:
                stderr_str = (
                    stderr_str[: self.config.max_output_size_bytes]
                    + "\n... (output truncated)"
                )

            success = process.returncode == 0

            return SandboxResult(
                success=success,
                stdout=stdout_str,
                stderr=stderr_str,
                execution_time_ms=execution_time_ms,
                error_message=stderr_str if not success else None,
            )

        finally:
            # Clean up temp file
            try:
                Path(temp_file).unlink()
            except Exception:
                pass

    async def _execute_docker(
        self, code: str, context: dict[str, Any] | None = None
    ) -> SandboxResult:
        """Execute code in Docker container with full isolation"""
        import time

        start_time = time.time()

        # Create wrapper script
        wrapper_code = self._create_wrapper_script(code, context)

        # Create temp directory for mounting
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir) / "script.py"
            script_path.write_text(wrapper_code)

            container_name = f"sandbox_{uuid.uuid4().hex[:8]}"

            # Docker command with resource limits
            docker_cmd = [
                "docker",
                "run",
                "--rm",
                "--name",
                container_name,
                "--memory",
                f"{self.config.max_memory_mb}m",
                "--cpus",
                str(self.config.max_cpu_percent / 100),
                "--network",
                "none" if not self.config.network_enabled else "bridge",
                "--read-only",
                "--tmpfs",
                "/tmp:size=10m",
                "-v",
                f"{script_path}:/app/script.py:ro",
                "-w",
                "/app",
                self.config.docker_image,
                "python",
                "/app/script.py",
            ]

            try:
                process = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self.config.timeout_seconds
                        + 5,  # Extra time for container overhead
                    )
                except TimeoutError:
                    # Kill the container
                    kill_process = await asyncio.create_subprocess_exec(
                        "docker",
                        "kill",
                        container_name,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await kill_process.wait()

                    return SandboxResult(
                        success=False,
                        error_message="Execution timed out",
                        was_timeout=True,
                        execution_time_ms=int((time.time() - start_time) * 1000),
                    )

                execution_time_ms = int((time.time() - start_time) * 1000)

                stdout_str = stdout.decode("utf-8", errors="replace")
                stderr_str = stderr.decode("utf-8", errors="replace")

                # Check for OOM
                if "Killed" in stderr_str or process.returncode == 137:
                    return SandboxResult(
                        success=False,
                        stdout=stdout_str,
                        stderr=stderr_str,
                        error_message="Memory limit exceeded",
                        was_memory_limit=True,
                        execution_time_ms=execution_time_ms,
                    )

                success = process.returncode == 0

                return SandboxResult(
                    success=success,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    execution_time_ms=execution_time_ms,
                    error_message=stderr_str if not success else None,
                )

            except FileNotFoundError:
                return SandboxResult(
                    success=False,
                    error_message="Docker is not available. Please install Docker or switch to subprocess mode.",
                )

    async def _execute_unsafe(
        self, code: str, context: dict[str, Any] | None = None
    ) -> SandboxResult:
        """Execute code without sandbox (DANGEROUS - only for trusted code)"""
        import time

        start_time = time.time()
        local_vars = context.copy() if context else {}

        try:
            exec(code, {"__builtins__": __builtins__}, local_vars)
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Capture any result variable
            result = local_vars.get("result", local_vars.get("output", None))

            return SandboxResult(
                success=True,
                return_value=result,
                execution_time_ms=execution_time_ms,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

    def _create_wrapper_script(
        self, code: str, context: dict[str, Any] | None = None
    ) -> str:
        """Create a wrapper script that safely executes the user code"""
        context_code = ""
        if context:
            import json as json_module

            # Serialize context safely
            try:
                context_json = json_module.dumps(context)
                context_code = f"""
import json
_context = json.loads('''{context_json}''')
globals().update(_context)
"""
            except (TypeError, ValueError):
                # Can't serialize context, skip it
                pass

        return f"""
import sys
import io

# Redirect stdout/stderr
_stdout = io.StringIO()
_stderr = io.StringIO()
sys.stdout = _stdout
sys.stderr = _stderr

try:
{context_code}
    # User code (indented)
{self._indent_code(code, 4)}

    # Print captured output
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    print(_stdout.getvalue(), end="")
    if _stderr.getvalue():
        print(_stderr.getvalue(), end="", file=sys.stderr)
except Exception as e:
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by given number of spaces"""
        indent = " " * spaces
        lines = code.split("\n")
        return "\n".join(indent + line for line in lines)
