"""
Circuit breaker pattern for preventing cascading failures.

Implements the circuit breaker pattern with three states:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests fail fast
- HALF_OPEN: Testing if the service has recovered

Usage:
    breaker = CircuitBreaker(name="my_service")

    try:
        result = await breaker.call(async_function, *args, **kwargs)
    except CircuitOpenError:
        # Handle circuit being open
        pass
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Failing fast, not attempting calls
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        circuit_name: str | None = None,
        time_until_recovery: float | None = None,
    ):
        super().__init__(message)
        self.circuit_name = circuit_name
        self.time_until_recovery = time_until_recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    # Failure threshold to trip the circuit
    failure_threshold: int = 5

    # Number of consecutive successes to close circuit from half-open
    success_threshold: int = 2

    # Time in seconds before attempting recovery (moving to half-open)
    recovery_timeout: float = 60.0

    # Window in seconds for counting failures (rolling window)
    failure_window: float = 60.0

    # Maximum concurrent calls in half-open state
    half_open_max_calls: int = 1

    # Exception types that count as failures
    failure_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (Exception,)
    )

    # Exception types that do NOT count as failures
    excluded_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (ValueError, TypeError, KeyError)
    )

    @classmethod
    def for_tools(cls) -> "CircuitBreakerConfig":
        """Config for tool execution."""
        return cls(
            failure_threshold=5,
            recovery_timeout=30.0,
            failure_window=60.0,
        )

    @classmethod
    def for_llm(cls) -> "CircuitBreakerConfig":
        """Config for LLM APIs (more tolerant, longer recovery)."""
        return cls(
            failure_threshold=10,
            recovery_timeout=120.0,
            failure_window=120.0,
        )

    @classmethod
    def for_mcp(cls) -> "CircuitBreakerConfig":
        """Config for MCP servers."""
        return cls(
            failure_threshold=3,
            recovery_timeout=30.0,
            failure_window=30.0,
        )

    @classmethod
    def for_external_api(cls) -> "CircuitBreakerConfig":
        """Config for external APIs (e.g., search APIs)."""
        return cls(
            failure_threshold=5,
            recovery_timeout=60.0,
            failure_window=60.0,
        )


@dataclass
class FailureRecord:
    """Record of a failure event."""

    timestamp: float
    exception_type: str
    message: str


class CircuitBreaker:
    """
    Circuit breaker implementation for preventing cascading failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation. Failures are counted, and if they exceed
              the threshold within the window, the circuit trips to OPEN.
    - OPEN: All calls fail immediately with CircuitOpenError. After the
            recovery timeout, the circuit moves to HALF_OPEN.
    - HALF_OPEN: A limited number of calls are allowed through. If they
                 succeed, the circuit closes. If they fail, it opens again.
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._failures: list[FailureRecord] = []
        self._last_failure_time: float | None = None
        self._last_state_change: float = time.time()
        self._half_open_calls = 0

        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN

    @property
    def failure_count(self) -> int:
        """Number of failures in the current window."""
        self._prune_old_failures()
        return len(self._failures)

    @property
    def time_until_recovery(self) -> float | None:
        """Time in seconds until circuit might recover (None if not open)."""
        if self._state != CircuitState.OPEN:
            return None
        if self._last_failure_time is None:
            return None

        elapsed = time.time() - self._last_failure_time
        remaining = self.config.recovery_timeout - elapsed
        return max(0, remaining)

    def get_stats(self) -> dict[str, Any]:
        """Get current circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self.failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
            "time_until_recovery": self.time_until_recovery,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "failure_window": self.config.failure_window,
            },
        }

    async def call(
        self,
        func: Callable[..., Any],
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            The result of the function call

        Raises:
            CircuitOpenError: If the circuit is open
            Exception: Any exception raised by the function
        """
        async with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    raise CircuitOpenError(
                        message=f"Circuit breaker '{self.name}' is open",
                        circuit_name=self.name,
                        time_until_recovery=self.time_until_recovery,
                    )

            # In HALF_OPEN, limit concurrent calls
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitOpenError(
                        message=f"Circuit breaker '{self.name}' is half-open (max calls reached)",
                        circuit_name=self.name,
                    )
                self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

        finally:
            async with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    self._half_open_calls = max(0, self._half_open_calls - 1)

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        f"Circuit breaker '{self.name}' closed after {self._success_count} successes"
                    )

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0

    async def _on_failure(self, exception: Exception) -> None:
        """Handle failed call."""
        # Check if this exception should be counted
        if not self._should_count_failure(exception):
            return

        async with self._lock:
            now = time.time()
            self._last_failure_time = now

            # Record failure
            self._failures.append(
                FailureRecord(
                    timestamp=now,
                    exception_type=type(exception).__name__,
                    message=str(exception)[:200],
                )
            )

            # Prune old failures
            self._prune_old_failures()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open state opens the circuit
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"Circuit breaker '{self.name}' opened (failure in half-open state)"
                )

            elif self._state == CircuitState.CLOSED:
                if len(self._failures) >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit breaker '{self.name}' opened after {len(self._failures)} failures"
                    )

    def _should_count_failure(self, exception: Exception) -> bool:
        """Determine if an exception should count as a failure."""
        # Don't count excluded exceptions
        if isinstance(exception, self.config.excluded_exceptions):
            return False

        # Count if it matches failure exceptions
        return isinstance(exception, self.config.failure_exceptions)

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True

        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.recovery_timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failures.clear()
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0

        logger.debug(
            f"Circuit breaker '{self.name}' transitioned: {old_state.value} -> {new_state.value}"
        )

    def _prune_old_failures(self) -> None:
        """Remove failures outside the window."""
        cutoff = time.time() - self.config.failure_window
        self._failures = [f for f in self._failures if f.timestamp >= cutoff]

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failures.clear()
        self._success_count = 0
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_state_change = time.time()
        logger.info(f"Circuit breaker '{self.name}' manually reset")

    def force_open(self) -> None:
        """Manually open the circuit breaker."""
        self._transition_to(CircuitState.OPEN)
        self._last_failure_time = time.time()
        logger.info(f"Circuit breaker '{self.name}' manually opened")


# ============================================================================
# Circuit Breaker Registry
# ============================================================================


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Usage:
        registry = CircuitBreakerRegistry()

        # Get or create a circuit breaker
        breaker = registry.get_or_create("my_service", config=my_config)

        # Execute through the breaker
        result = await breaker.call(my_function, *args)
    """

    _instance: "CircuitBreakerRegistry | None" = None

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "CircuitBreakerRegistry":
        """Get the singleton instance of the registry."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """
        Get an existing circuit breaker or create a new one.

        Args:
            name: Unique name for the circuit breaker
            config: Configuration (only used if creating new)

        Returns:
            CircuitBreaker instance
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name=name, config=config)
            logger.debug(f"Created circuit breaker: {name}")
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get a circuit breaker by name, or None if not found."""
        return self._breakers.get(name)

    def remove(self, name: str) -> bool:
        """Remove a circuit breaker from the registry."""
        if name in self._breakers:
            del self._breakers[name]
            return True
        return False

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {name: breaker.get_stats() for name, breaker in self._breakers.items()}

    def get_open_circuits(self) -> list[str]:
        """Get names of all currently open circuits."""
        return [name for name, breaker in self._breakers.items() if breaker.is_open]

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

    def clear(self) -> None:
        """Remove all circuit breakers from the registry."""
        self._breakers.clear()


# ============================================================================
# Convenience Functions
# ============================================================================


def get_circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
) -> CircuitBreaker:
    """
    Get or create a circuit breaker from the global registry.

    Args:
        name: Unique name for the circuit breaker
        config: Configuration (only used if creating new)

    Returns:
        CircuitBreaker instance
    """
    registry = CircuitBreakerRegistry.get_instance()
    return registry.get_or_create(name, config)


# ============================================================================
# Decorator
# ============================================================================


def circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
):
    """
    Decorator to wrap a function with a circuit breaker.

    Usage:
        @circuit_breaker("my_service")
        async def my_function():
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        breaker = get_circuit_breaker(name, config)

        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator
