"""
Retry logic with exponential backoff for agent operations.

Uses tenacity for robust retry handling with:
- Configurable retry attempts
- Exponential backoff with jitter
- Specific exception handling
- Logging and metrics integration
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    after_log,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ============================================================================
# Custom Exceptions
# ============================================================================


class RetryableError(Exception):
    """Base class for errors that should be retried."""


class ToolExecutionError(RetryableError):
    """Raised when tool execution fails and should be retried."""

    def __init__(self, message: str, tool_name: str | None = None, attempts: int = 0):
        super().__init__(message)
        self.tool_name = tool_name
        self.attempts = attempts


class LLMExecutionError(RetryableError):
    """Raised when LLM API call fails and should be retried."""

    def __init__(
        self,
        message: str,
        model: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.model = model
        self.status_code = status_code


class MCPConnectionError(RetryableError):
    """Raised when MCP server connection fails and should be retried."""

    def __init__(self, message: str, server_name: str | None = None):
        super().__init__(message)
        self.server_name = server_name


class NonRetryableError(Exception):
    """Errors that should NOT be retried (e.g., permission denied, invalid input)."""


# ============================================================================
# Retry Configuration
# ============================================================================


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    # Number of retry attempts
    max_attempts: int = 3

    # Exponential backoff settings
    min_wait_seconds: float = 1.0
    max_wait_seconds: float = 30.0
    multiplier: float = 2.0

    # Jitter settings
    use_jitter: bool = True
    jitter_factor: float = 0.5

    # Exception types to retry
    retry_on: tuple[type[Exception], ...] = field(
        default_factory=lambda: (
            RetryableError,
            ToolExecutionError,
            LLMExecutionError,
            MCPConnectionError,
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
        )
    )

    # Exception types to NOT retry
    do_not_retry_on: tuple[type[Exception], ...] = field(
        default_factory=lambda: (
            NonRetryableError,
            PermissionError,
            ValueError,
            TypeError,
            KeyError,
        )
    )

    # Logging
    log_retries: bool = True
    log_level: int = logging.WARNING

    @classmethod
    def for_tools(cls) -> "RetryConfig":
        """Default config for tool execution."""
        return cls(
            max_attempts=3,
            min_wait_seconds=1.0,
            max_wait_seconds=10.0,
        )

    @classmethod
    def for_llm(cls) -> "RetryConfig":
        """Default config for LLM calls (longer waits for rate limits)."""
        return cls(
            max_attempts=5,
            min_wait_seconds=2.0,
            max_wait_seconds=60.0,
            multiplier=2.5,
        )

    @classmethod
    def for_mcp(cls) -> "RetryConfig":
        """Default config for MCP server connections."""
        return cls(
            max_attempts=3,
            min_wait_seconds=0.5,
            max_wait_seconds=5.0,
        )

    @classmethod
    def for_database(cls) -> "RetryConfig":
        """Default config for database operations."""
        return cls(
            max_attempts=3,
            min_wait_seconds=0.1,
            max_wait_seconds=2.0,
        )


# ============================================================================
# Retry Decorators
# ============================================================================


def _should_retry(exception: BaseException, config: RetryConfig) -> bool:
    """Determine if an exception should trigger a retry."""
    # Never retry these
    if isinstance(exception, config.do_not_retry_on):
        return False

    # Always retry these
    if isinstance(exception, config.retry_on):
        return True

    # Check for specific HTTP status codes in LLM errors
    if hasattr(exception, "status_code"):
        status_code = exception.status_code
        # Retry on rate limit (429) and server errors (5xx)
        if status_code in (429, 500, 502, 503, 504):
            return True
        # Don't retry on client errors (4xx except 429)
        if 400 <= status_code < 500:
            return False

    # Check for common error messages that indicate transient failures
    error_msg = str(exception).lower()
    transient_patterns = [
        "timeout",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "service unavailable",
        "internal server error",
        "bad gateway",
        "gateway timeout",
    ]
    return any(pattern in error_msg for pattern in transient_patterns)


def create_retry_decorator(config: RetryConfig | None = None):
    """
    Create a retry decorator with the given configuration.

    Usage:
        @create_retry_decorator(RetryConfig(max_attempts=5))
        async def my_function():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            wait_strategy = (
                wait_random_exponential(
                    multiplier=config.multiplier,
                    min=config.min_wait_seconds,
                    max=config.max_wait_seconds,
                )
                if config.use_jitter
                else wait_exponential(
                    multiplier=config.multiplier,
                    min=config.min_wait_seconds,
                    max=config.max_wait_seconds,
                )
            )

            retrying = AsyncRetrying(
                stop=stop_after_attempt(config.max_attempts),
                wait=wait_strategy,
                retry=retry_if_exception(lambda e: _should_retry(e, config)),
                before_sleep=before_sleep_log(logger, config.log_level)
                if config.log_retries
                else None,
                after=after_log(logger, logging.DEBUG) if config.log_retries else None,
                reraise=True,
            )

            try:
                async for attempt in retrying:
                    with attempt:
                        return await func(*args, **kwargs)
            except RetryError as e:
                # Re-raise the last exception
                raise e.last_attempt.exception() from None

        return wrapper  # type: ignore

    return decorator


# ============================================================================
# Pre-configured Retry Functions
# ============================================================================


async def execute_with_retry(
    func: Callable[..., Any],
    *args,
    config: RetryConfig | None = None,
    **kwargs,
) -> Any:
    """
    Execute a function with retry logic.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        config: Retry configuration (defaults to RetryConfig())
        **kwargs: Keyword arguments for func

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries fail
    """
    if config is None:
        config = RetryConfig()

    @create_retry_decorator(config)
    async def _execute():
        return await func(*args, **kwargs)

    return await _execute()


async def execute_tool_with_retry(
    tool_func: Callable[..., Any],
    tool_name: str,
    *args,
    config: RetryConfig | None = None,
    **kwargs,
) -> Any:
    """
    Execute a tool with retry logic, wrapping errors appropriately.

    Args:
        tool_func: Tool's execute function
        tool_name: Name of the tool (for error messages)
        *args: Positional arguments for tool
        config: Retry configuration
        **kwargs: Keyword arguments for tool

    Returns:
        Tool execution result

    Raises:
        ToolExecutionError: If all retries fail
    """
    if config is None:
        config = RetryConfig.for_tools()

    attempts = 0

    async def _execute_with_tracking():
        nonlocal attempts
        attempts += 1
        try:
            return await tool_func(*args, **kwargs)
        except Exception as e:
            # Wrap in ToolExecutionError for consistent handling
            if not isinstance(e, (ToolExecutionError, NonRetryableError)):
                raise ToolExecutionError(
                    message=str(e),
                    tool_name=tool_name,
                    attempts=attempts,
                ) from e
            raise

    try:
        return await execute_with_retry(_execute_with_tracking, config=config)
    except ToolExecutionError:
        raise
    except Exception as e:
        raise ToolExecutionError(
            message=str(e),
            tool_name=tool_name,
            attempts=attempts,
        ) from e


async def execute_llm_with_retry(
    llm_func: Callable[..., Any],
    model: str | None = None,
    *args,
    config: RetryConfig | None = None,
    **kwargs,
) -> Any:
    """
    Execute an LLM API call with retry logic.

    Specifically handles:
    - Rate limiting (429)
    - Server errors (5xx)
    - Timeout errors

    Args:
        llm_func: LLM invoke function
        model: Model name (for error messages)
        *args: Positional arguments
        config: Retry configuration
        **kwargs: Keyword arguments

    Returns:
        LLM response

    Raises:
        LLMExecutionError: If all retries fail
    """
    if config is None:
        config = RetryConfig.for_llm()

    async def _execute():
        try:
            return await llm_func(*args, **kwargs)
        except Exception as e:
            # Extract status code if available
            status_code = getattr(e, "status_code", None)
            if status_code is None and hasattr(e, "response"):
                response = e.response
                status_code = getattr(response, "status_code", None)

            raise LLMExecutionError(
                message=str(e),
                model=model,
                status_code=status_code,
            ) from e

    return await execute_with_retry(_execute, config=config)


async def execute_mcp_with_retry(
    mcp_func: Callable[..., Any],
    server_name: str | None = None,
    *args,
    config: RetryConfig | None = None,
    **kwargs,
) -> Any:
    """
    Execute an MCP server operation with retry logic.

    Args:
        mcp_func: MCP operation function
        server_name: Server name (for error messages)
        *args: Positional arguments
        config: Retry configuration
        **kwargs: Keyword arguments

    Returns:
        MCP operation result

    Raises:
        MCPConnectionError: If all retries fail
    """
    if config is None:
        config = RetryConfig.for_mcp()

    async def _execute():
        try:
            return await mcp_func(*args, **kwargs)
        except Exception as e:
            raise MCPConnectionError(
                message=str(e),
                server_name=server_name,
            ) from e

    return await execute_with_retry(_execute, config=config)


# ============================================================================
# Utility Functions
# ============================================================================


def is_retryable_exception(
    exception: Exception, config: RetryConfig | None = None
) -> bool:
    """Check if an exception should be retried."""
    if config is None:
        config = RetryConfig()
    return _should_retry(exception, config)


def get_retry_delay(attempt: int, config: RetryConfig | None = None) -> float:
    """Calculate the delay before the next retry attempt."""
    if config is None:
        config = RetryConfig()

    delay = config.min_wait_seconds * (config.multiplier ** (attempt - 1))
    delay = min(delay, config.max_wait_seconds)

    if config.use_jitter:
        import random

        jitter = delay * config.jitter_factor * random.random()
        delay = delay + jitter

    return delay
