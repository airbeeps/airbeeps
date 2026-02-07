"""
Code Executor tool for agents.

Provides safe Python code execution in a sandboxed environment.
"""

import logging
from typing import Any

from ..security.sandbox import CodeSandbox, SandboxConfig, SandboxMode
from .base import AgentTool, AgentToolConfig, ToolSecurityLevel
from .registry import tool_registry

logger = logging.getLogger(__name__)


@tool_registry.register
class CodeExecutorTool(AgentTool):
    """
    Execute Python code in a sandboxed environment.

    This tool allows the agent to run Python code safely with:
    - Resource limits (memory, CPU, time)
    - Restricted imports (allowlist-only: math, json, datetime, etc.)
    - Isolated execution environment (Docker by default)

    Security Note: Defaults to Docker mode for production. Set
    AIRBEEPS_SANDBOX_MODE=subprocess only for development without Docker.
    """

    def __init__(self, config: AgentToolConfig | None = None):
        import os

        super().__init__(config)

        # Get sandbox config from parameters, with env var override
        # Priority: env var > config parameter > default (docker)
        env_mode = os.environ.get("AIRBEEPS_SANDBOX_MODE", "").lower()
        config_mode = self.config.parameters.get("sandbox_mode", "docker")

        if env_mode in ("docker", "subprocess", "disabled"):
            sandbox_mode = env_mode
        else:
            sandbox_mode = config_mode

        timeout = self.config.parameters.get("timeout_seconds", 30)
        max_memory = self.config.parameters.get("max_memory_mb", 256)

        # Log warning if not using Docker in production
        if sandbox_mode != "docker":
            logger.warning(
                f"CodeSandbox using '{sandbox_mode}' mode. "
                "Docker mode is recommended for production security."
            )

        self.sandbox = CodeSandbox(
            SandboxConfig(
                mode=SandboxMode(sandbox_mode),
                timeout_seconds=timeout,
                max_memory_mb=max_memory,
            )
        )

    @property
    def name(self) -> str:
        return "execute_python"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a sandboxed environment. "
            "The code runs with limited imports (math, json, datetime, re, collections, etc.) "
            "and restricted system access. Use this for calculations, data processing, "
            "or algorithm execution. Output is captured from print statements."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.DANGEROUS

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code to execute. Use print() to output results. "
                        "Available imports: math, json, datetime, re, collections, itertools, "
                        "functools, statistics, decimal, csv. "
                        "Avoid: os, subprocess, open(), eval(), exec()."
                    ),
                },
                "context": {
                    "type": "object",
                    "description": "Optional variables to inject into the execution context",
                    "additionalProperties": True,
                },
            },
            "required": ["code"],
        }

    async def execute(self, code: str, context: dict[str, Any] | None = None) -> str:
        """Execute Python code in sandbox"""
        logger.info(f"Executing code ({len(code)} chars)")

        result = await self.sandbox.execute(code, context)

        if result.success:
            output_parts = []

            if result.stdout:
                output_parts.append(f"Output:\n{result.stdout}")

            if result.return_value is not None:
                output_parts.append(f"Return value: {result.return_value}")

            if not output_parts:
                output_parts.append("Code executed successfully (no output)")

            output_parts.append(f"\n[Execution time: {result.execution_time_ms}ms]")

            return "\n".join(output_parts)
        else:
            error_msg = "Execution failed"

            if result.was_timeout:
                error_msg = "Execution timed out"
            elif result.was_memory_limit:
                error_msg = "Memory limit exceeded"
            elif result.error_message:
                error_msg = f"Error: {result.error_message}"

            if result.stderr:
                error_msg += f"\n\nStderr:\n{result.stderr}"

            return error_msg


# Note: DataAnalysisTool is defined in data_analysis.py
# Do not duplicate here to avoid registry conflicts
