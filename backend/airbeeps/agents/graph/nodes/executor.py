"""
Executor Node for LangGraph.

Responsible for:
- Executing tool calls (with security layer)
- Handling parallel tool execution with concurrency limits
- Tool-specific timeouts and retry logic
- Tracking tool usage and costs
- Priority-based execution ordering
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ToolPriority(int, Enum):
    """Priority levels for tool execution."""

    CRITICAL = 0  # Execute first (e.g., security checks)
    HIGH = 1  # Execute early (e.g., data retrieval)
    NORMAL = 2  # Default priority
    LOW = 3  # Execute last (e.g., logging)


@dataclass
class ToolExecutionConfig:
    """Configuration for tool execution."""

    max_concurrent: int = 3
    default_timeout_seconds: int = 30
    max_retries: int = 2
    retry_delay_seconds: float = 1.0
    per_conversation_cost_limit: float = 0.50
    max_tool_calls_per_turn: int = 10
    max_tool_calls_total: int = 20

    # Tool-specific timeouts (tool_name -> timeout_seconds)
    tool_timeouts: dict[str, int] = field(default_factory=dict)

    # Tool priorities (tool_name -> priority)
    tool_priorities: dict[str, ToolPriority] = field(default_factory=dict)

    # Retryable error patterns
    retryable_errors: list[str] = field(
        default_factory=lambda: [
            "timeout",
            "rate limit",
            "connection",
            "temporary",
            "retry",
            "503",
            "429",
        ]
    )


@dataclass
class ToolExecutionResult:
    """Result from a tool execution."""

    tool_name: str
    tool_input: dict[str, Any]
    result: Any
    success: bool
    duration_ms: int
    attempts: int = 1
    error_type: str | None = None
    cost_usd: float = 0.0

    def __post_init__(self):
        """Calculate cost if not provided."""
        if self.cost_usd == 0.0:
            try:
                from ..cost_estimator import estimate_tool_cost

                self.cost_usd = estimate_tool_cost(self.tool_name, self.tool_input)
            except ImportError:
                pass

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "result": str(self.result) if self.result else None,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "error_type": self.error_type,
            "cost_usd": self.cost_usd,
        }


async def executor_node(
    state: dict[str, Any],
    tool_executor: Any = None,
    max_parallel: int = 3,
    config: ToolExecutionConfig | None = None,
) -> dict[str, Any]:
    """
    Execute pending tool calls.

    This node:
    1. Gets pending tool calls from state
    2. Prioritizes and orders tool calls
    3. Executes them in parallel with limits
    4. Records results and updates state
    5. Routes to reflector for quality check

    Args:
        state: Current agent state
        tool_executor: Function to execute tools (tool_name, input) -> result
        max_parallel: Maximum parallel tool calls
        config: Execution configuration

    Returns:
        Updated state with tool results
    """
    if config is None:
        config = ToolExecutionConfig(max_concurrent=max_parallel)

    pending_calls = state.get("pending_tool_calls", [])

    if not pending_calls:
        logger.warning("No pending tool calls in executor node")
        state["next_action"] = "reflect"
        return state

    if not tool_executor:
        logger.error("No tool executor provided")
        state["next_action"] = "reflect"
        return state

    # Track tools used
    tools_used = state.get("tools_used", [])
    max_tool_calls = state.get("max_tool_calls", config.max_tool_calls_total)

    # Check if we've hit the tool limit
    if len(tools_used) >= max_tool_calls:
        logger.warning("Tool call limit reached")
        state["pending_tool_calls"] = []
        state["next_action"] = "reflect"
        return state

    # Calculate how many tools we can still call
    remaining_calls = min(
        max_tool_calls - len(tools_used),
        config.max_tool_calls_per_turn,
    )
    calls_to_execute = pending_calls[:remaining_calls]

    # Sort by priority
    calls_to_execute = _sort_by_priority(calls_to_execute, config)

    # Create parallel executor with retry support
    executor = ParallelExecutor(
        max_concurrent=config.max_concurrent,
        default_timeout=config.default_timeout_seconds,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay_seconds,
        tool_timeouts=config.tool_timeouts,
        retryable_errors=config.retryable_errors,
    )

    # Execute all calls
    results = await executor.execute_batch(tool_executor, calls_to_execute)

    # Update state with results
    for result in results:
        tools_used.append(result.to_dict())

    state["tools_used"] = tools_used
    state["pending_tool_calls"] = []  # Clear pending calls

    # Track execution stats
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    total_cost = sum(r.cost_usd for r in results)
    total_duration = sum(r.duration_ms for r in results)

    state["cost_spent_usd"] = state.get("cost_spent_usd", 0) + total_cost

    # Check cost limit
    if state.get("cost_spent_usd", 0) >= state.get(
        "cost_limit_usd", config.per_conversation_cost_limit
    ):
        logger.warning("Cost limit reached during tool execution")
        state["budget_exceeded"] = True

    # Add tool results to messages
    messages = state.get("messages", [])
    for result in results:
        status = "success" if result.success else "failed"
        retry_info = f" (attempts: {result.attempts})" if result.attempts > 1 else ""

        messages.append(
            {
                "role": "assistant",
                "content": f"[Tool Call: {result.tool_name}] Status: {status}{retry_info}\nResult: {result.result}",
            }
        )

    state["messages"] = messages

    # Store execution stats
    state["last_execution_stats"] = {
        "total_calls": len(results),
        "successful": successful,
        "failed": failed,
        "total_duration_ms": total_duration,
        "total_cost_usd": total_cost,
    }

    # Route to reflector
    state["next_action"] = "reflect"

    logger.info(
        f"Executed {len(results)} tool calls: {successful} succeeded, {failed} failed, "
        f"duration={total_duration}ms, cost=${total_cost:.4f}"
    )

    return state


def _sort_by_priority(
    calls: list[dict[str, Any]],
    config: ToolExecutionConfig,
) -> list[dict[str, Any]]:
    """Sort tool calls by priority."""

    def get_priority(call: dict) -> int:
        tool_name = call.get("tool", call.get("name", ""))
        priority = config.tool_priorities.get(tool_name, ToolPriority.NORMAL)
        return priority.value if isinstance(priority, ToolPriority) else int(priority)

    return sorted(calls, key=get_priority)


async def _execute_single_tool(
    tool_executor: Any,
    tool_name: str,
    tool_input: dict[str, Any],
    timeout_seconds: int = 30,
) -> ToolExecutionResult:
    """Execute a single tool and return result record."""
    start_time = time.time()

    try:
        result = await asyncio.wait_for(
            tool_executor(tool_name, tool_input),
            timeout=timeout_seconds,
        )
        duration_ms = int((time.time() - start_time) * 1000)

        return ToolExecutionResult(
            tool_name=tool_name,
            tool_input=tool_input,
            result=result,
            success=True,
            duration_ms=duration_ms,
        )

    except TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning(f"Tool {tool_name} timed out after {timeout_seconds}s")

        return ToolExecutionResult(
            tool_name=tool_name,
            tool_input=tool_input,
            result=f"Error: Tool execution timed out after {timeout_seconds}s",
            success=False,
            duration_ms=duration_ms,
            error_type="timeout",
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Tool {tool_name} execution failed: {e}")

        return ToolExecutionResult(
            tool_name=tool_name,
            tool_input=tool_input,
            result=f"Error: {e}",
            success=False,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
        )


class ParallelExecutor:
    """
    Advanced parallel tool execution with:
    - Concurrency limits via semaphore
    - Tool-specific timeouts
    - Retry logic for transient failures
    - Cost tracking
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        default_timeout: int = 30,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        tool_timeouts: dict[str, int] | None = None,
        retryable_errors: list[str] | None = None,
    ):
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.tool_timeouts = tool_timeouts or {}
        self.retryable_errors = retryable_errors or [
            "timeout",
            "rate limit",
            "connection",
        ]
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def _get_timeout(self, tool_name: str) -> int:
        """Get timeout for a specific tool."""
        return self.tool_timeouts.get(tool_name, self.default_timeout)

    def _is_retryable(self, error_type: str | None, result: str) -> bool:
        """Check if an error is retryable."""
        if error_type == "timeout":
            return True

        result_lower = result.lower() if result else ""
        return any(pattern in result_lower for pattern in self.retryable_errors)

    async def _execute_with_retry(
        self,
        tool_executor: Any,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute a tool with retry logic."""
        timeout = self._get_timeout(tool_name)
        last_result: ToolExecutionResult | None = None

        for attempt in range(1, self.max_retries + 2):  # +1 for initial attempt
            result = await _execute_single_tool(
                tool_executor,
                tool_name,
                tool_input,
                timeout_seconds=timeout,
            )
            result.attempts = attempt

            if result.success:
                return result

            last_result = result

            # Check if we should retry
            if attempt <= self.max_retries:
                if self._is_retryable(result.error_type, str(result.result)):
                    logger.info(
                        f"Retrying tool {tool_name} (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(
                        self.retry_delay * attempt
                    )  # Exponential backoff
                    continue

            # Not retryable or max retries reached
            break

        return last_result or ToolExecutionResult(
            tool_name=tool_name,
            tool_input=tool_input,
            result="Error: Unknown execution failure",
            success=False,
            duration_ms=0,
        )

    async def execute_batch(
        self,
        tool_executor: Any,
        tool_calls: list[dict[str, Any]],
    ) -> list[ToolExecutionResult]:
        """
        Execute a batch of tool calls with concurrency limit and retry.

        Args:
            tool_executor: Function to execute tools
            tool_calls: List of tool call dictionaries

        Returns:
            List of execution results
        """

        async def execute_with_semaphore(call: dict) -> ToolExecutionResult:
            async with self.semaphore:
                tool_name = call.get("tool", call.get("name", ""))
                tool_input = call.get("input", call.get("arguments", {}))

                return await self._execute_with_retry(
                    tool_executor,
                    tool_name,
                    tool_input,
                )

        tasks = [execute_with_semaphore(call) for call in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions that weren't caught
        processed_results = []
        for call, result in zip(tool_calls, results):
            if isinstance(result, Exception):
                tool_name = call.get("tool", call.get("name", ""))
                processed_results.append(
                    ToolExecutionResult(
                        tool_name=tool_name,
                        tool_input=call.get("input", {}),
                        result=f"Error: {result}",
                        success=False,
                        duration_ms=0,
                        error_type=type(result).__name__,
                    )
                )
            else:
                processed_results.append(result)

        return processed_results


# Factory function for creating executor with config
def create_parallel_executor(
    max_concurrent: int = 3,
    default_timeout: int = 30,
    max_retries: int = 2,
    tool_timeouts: dict[str, int] | None = None,
) -> ParallelExecutor:
    """
    Create a configured parallel executor.

    Args:
        max_concurrent: Maximum concurrent tool calls
        default_timeout: Default timeout in seconds
        max_retries: Maximum retry attempts
        tool_timeouts: Tool-specific timeouts

    Returns:
        Configured ParallelExecutor
    """
    return ParallelExecutor(
        max_concurrent=max_concurrent,
        default_timeout=default_timeout,
        max_retries=max_retries,
        tool_timeouts=tool_timeouts or {},
    )
