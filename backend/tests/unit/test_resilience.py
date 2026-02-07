"""
Unit tests for Resilience Module.

Tests for CircuitBreaker, retry logic, and health checks.
All tests use mocked dependencies to avoid real external calls.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Circuit Breaker Tests
# ============================================================================


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.recovery_timeout == 60.0

    def test_for_tools_config(self):
        """Should have appropriate tool config."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig.for_tools()

        assert config.failure_threshold == 5
        assert config.recovery_timeout == 30.0

    def test_for_llm_config(self):
        """Should have more tolerant LLM config."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig.for_llm()

        assert config.failure_threshold == 10
        assert config.recovery_timeout == 120.0


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_closed(self):
        """Should start in closed state."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitState,
        )

        breaker = CircuitBreaker(name="test")

        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed
        assert not breaker.is_open

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Should execute successful calls in closed state."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(name="test")

        async def success_func():
            return "success"

        result = await breaker.call(success_func)

        assert result == "success"
        assert breaker.is_closed

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Should open after reaching failure threshold."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(failure_threshold=3, failure_window=60.0)
        breaker = CircuitBreaker(name="test", config=config)

        async def failing_func():
            raise RuntimeError("Connection failed")

        # Cause enough failures to trip the breaker
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open

    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self):
        """Should reject calls immediately when open."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitOpenError,
        )

        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60.0)
        breaker = CircuitBreaker(name="test", config=config)

        async def failing_func():
            raise RuntimeError("fail")

        # Trip the breaker
        with pytest.raises(RuntimeError):
            await breaker.call(failing_func)

        # Now should get CircuitOpenError
        with pytest.raises(CircuitOpenError) as exc_info:
            await breaker.call(failing_func)

        assert exc_info.value.circuit_name == "test"

    @pytest.mark.asyncio
    async def test_excluded_exceptions_dont_count(self):
        """Should not count excluded exceptions as failures."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            excluded_exceptions=(ValueError,),
        )
        breaker = CircuitBreaker(name="test", config=config)

        async def value_error_func():
            raise ValueError("Invalid input")

        # ValueError should not trip the breaker
        for _ in range(5):
            with pytest.raises(ValueError):
                await breaker.call(value_error_func)

        assert breaker.is_closed

    def test_reset(self):
        """Should reset to closed state."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitState,
        )

        breaker = CircuitBreaker(name="test")
        breaker._state = CircuitState.OPEN

        breaker.reset()

        assert breaker.is_closed

    def test_force_open(self):
        """Should force circuit to open."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitState,
        )

        breaker = CircuitBreaker(name="test")

        breaker.force_open()

        assert breaker.state == CircuitState.OPEN

    def test_get_stats(self):
        """Should return statistics."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(name="test_service")

        stats = breaker.get_stats()

        assert stats["name"] == "test_service"
        assert stats["state"] == "CLOSED"
        assert "config" in stats


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry."""

    def test_get_or_create(self):
        """Should create and return circuit breakers."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_or_create("service1")
        breaker2 = registry.get_or_create("service1")

        assert breaker1 is breaker2

    def test_get_nonexistent(self):
        """Should return None for nonexistent breaker."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()

        assert registry.get("nonexistent") is None

    def test_remove(self):
        """Should remove circuit breaker."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()
        registry.get_or_create("service")

        result = registry.remove("service")

        assert result is True
        assert registry.get("service") is None

    def test_get_all_stats(self):
        """Should return stats for all breakers."""
        from airbeeps.agents.resilience.circuit_breaker import CircuitBreakerRegistry

        registry = CircuitBreakerRegistry()
        registry.get_or_create("service1")
        registry.get_or_create("service2")

        stats = registry.get_all_stats()

        assert "service1" in stats
        assert "service2" in stats

    def test_reset_all(self):
        """Should reset all breakers."""
        from airbeeps.agents.resilience.circuit_breaker import (
            CircuitBreakerRegistry,
            CircuitState,
        )

        registry = CircuitBreakerRegistry()
        b1 = registry.get_or_create("service1")
        b2 = registry.get_or_create("service2")

        b1._state = CircuitState.OPEN
        b2._state = CircuitState.OPEN

        registry.reset_all()

        assert b1.is_closed
        assert b2.is_closed


# ============================================================================
# Retry Tests
# ============================================================================


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from airbeeps.agents.resilience.retry import RetryConfig

        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.min_wait_seconds == 1.0
        assert config.use_jitter is True

    def test_for_llm_config(self):
        """Should have longer waits for LLM."""
        from airbeeps.agents.resilience.retry import RetryConfig

        config = RetryConfig.for_llm()

        assert config.max_attempts == 5
        assert config.min_wait_seconds == 2.0


class TestShouldRetry:
    """Tests for retry decision logic."""

    def test_retries_retryable_error(self):
        """Should retry RetryableError."""
        from airbeeps.agents.resilience.retry import (
            RetryConfig,
            RetryableError,
            _should_retry,
        )

        config = RetryConfig()
        assert _should_retry(RetryableError("test"), config) is True

    def test_does_not_retry_non_retryable(self):
        """Should not retry NonRetryableError."""
        from airbeeps.agents.resilience.retry import (
            NonRetryableError,
            RetryConfig,
            _should_retry,
        )

        config = RetryConfig()
        assert _should_retry(NonRetryableError("test"), config) is False

    def test_does_not_retry_value_error(self):
        """Should not retry ValueError."""
        from airbeeps.agents.resilience.retry import RetryConfig, _should_retry

        config = RetryConfig()
        assert _should_retry(ValueError("bad input"), config) is False

    def test_retries_timeout_error(self):
        """Should retry TimeoutError."""
        from airbeeps.agents.resilience.retry import RetryConfig, _should_retry

        config = RetryConfig()
        assert _should_retry(TimeoutError("timed out"), config) is True

    def test_retries_connection_error(self):
        """Should retry ConnectionError."""
        from airbeeps.agents.resilience.retry import RetryConfig, _should_retry

        config = RetryConfig()
        assert _should_retry(ConnectionError("refused"), config) is True


class TestExecuteWithRetry:
    """Tests for execute_with_retry function."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Should return result on success."""
        from airbeeps.agents.resilience.retry import execute_with_retry

        async def success_func():
            return "success"

        result = await execute_with_retry(success_func)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Should retry on retryable failure."""
        from airbeeps.agents.resilience.retry import RetryConfig, execute_with_retry

        call_count = 0

        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"

        config = RetryConfig(
            max_attempts=5, min_wait_seconds=0.01, max_wait_seconds=0.02
        )
        result = await execute_with_retry(failing_then_success, config=config)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Should raise after max attempts exceeded."""
        from airbeeps.agents.resilience.retry import RetryConfig, execute_with_retry

        async def always_fails():
            raise ConnectionError("Always fails")

        config = RetryConfig(
            max_attempts=2, min_wait_seconds=0.01, max_wait_seconds=0.02
        )

        with pytest.raises(ConnectionError):
            await execute_with_retry(always_fails, config=config)


class TestGetRetryDelay:
    """Tests for retry delay calculation."""

    def test_exponential_growth(self):
        """Should use exponential backoff."""
        from airbeeps.agents.resilience.retry import RetryConfig, get_retry_delay

        config = RetryConfig(
            min_wait_seconds=1.0,
            max_wait_seconds=100.0,
            multiplier=2.0,
            use_jitter=False,
        )

        delay1 = get_retry_delay(1, config)
        delay2 = get_retry_delay(2, config)
        delay3 = get_retry_delay(3, config)

        assert delay1 == 1.0
        assert delay2 == 2.0
        assert delay3 == 4.0

    def test_respects_max_wait(self):
        """Should cap at max_wait_seconds."""
        from airbeeps.agents.resilience.retry import RetryConfig, get_retry_delay

        config = RetryConfig(
            min_wait_seconds=1.0,
            max_wait_seconds=5.0,
            multiplier=10.0,
            use_jitter=False,
        )

        delay = get_retry_delay(3, config)

        assert delay == 5.0


class TestToolExecutionError:
    """Tests for ToolExecutionError."""

    def test_contains_tool_info(self):
        """Should contain tool name and attempts."""
        from airbeeps.agents.resilience.retry import ToolExecutionError

        error = ToolExecutionError(
            message="Failed to execute",
            tool_name="web_search",
            attempts=3,
        )

        assert error.tool_name == "web_search"
        assert error.attempts == 3


# ============================================================================
# Health Check Tests
# ============================================================================


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Should have expected status values."""
        from airbeeps.agents.resilience.health import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestServiceHealth:
    """Tests for ServiceHealth dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        from airbeeps.agents.resilience.health import HealthStatus, ServiceHealth

        health = ServiceHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message="OK",
            latency_ms=50.0,
        )

        data = health.to_dict()

        assert data["name"] == "database"
        assert data["status"] == "healthy"
        assert data["latency_ms"] == 50.0


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.mark.asyncio
    async def test_healthy_check(self):
        """Should return healthy for successful check."""
        from airbeeps.agents.resilience.health import (
            HealthChecker,
            HealthCheckConfig,
            HealthStatus,
        )

        async def healthy_check():
            return True

        config = HealthCheckConfig(check_timeout_seconds=1.0)
        checker = HealthChecker(name="test", check_func=healthy_check, config=config)

        result = await checker.check()

        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(self):
        """Should return unhealthy on exception."""
        from airbeeps.agents.resilience.health import (
            HealthChecker,
            HealthCheckConfig,
            HealthStatus,
        )

        async def failing_check():
            raise ConnectionError("Connection refused")

        config = HealthCheckConfig(check_timeout_seconds=1.0)
        checker = HealthChecker(name="test", check_func=failing_check, config=config)

        result = await checker.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_unhealthy_on_timeout(self):
        """Should return unhealthy on timeout."""
        from airbeeps.agents.resilience.health import (
            HealthChecker,
            HealthCheckConfig,
            HealthStatus,
        )

        async def slow_check():
            await asyncio.sleep(10)

        config = HealthCheckConfig(check_timeout_seconds=0.1)
        checker = HealthChecker(name="test", check_func=slow_check, config=config)

        result = await checker.check()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Timeout" in result.message

    @pytest.mark.asyncio
    async def test_caching(self):
        """Should cache results within TTL."""
        from airbeeps.agents.resilience.health import HealthChecker, HealthCheckConfig

        call_count = 0

        async def counting_check():
            nonlocal call_count
            call_count += 1
            return True

        config = HealthCheckConfig(cache_ttl=10.0)
        checker = HealthChecker(name="test", check_func=counting_check, config=config)

        await checker.check()
        await checker.check()
        await checker.check()

        assert call_count == 1  # Only called once due to caching

    @pytest.mark.asyncio
    async def test_force_bypasses_cache(self):
        """Should bypass cache when force=True."""
        from airbeeps.agents.resilience.health import HealthChecker, HealthCheckConfig

        call_count = 0

        async def counting_check():
            nonlocal call_count
            call_count += 1
            return True

        config = HealthCheckConfig(cache_ttl=10.0)
        checker = HealthChecker(name="test", check_func=counting_check, config=config)

        await checker.check()
        await checker.check(force=True)

        assert call_count == 2


class TestHealthRegistry:
    """Tests for HealthRegistry."""

    @pytest.mark.asyncio
    async def test_register_and_check(self):
        """Should register and run health checks."""
        from airbeeps.agents.resilience.health import HealthRegistry, HealthStatus

        registry = HealthRegistry()

        async def test_check():
            return True

        registry.register("test_service", test_check)

        result = await registry.check("test_service")

        assert result is not None
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_all(self):
        """Should check all registered services."""
        from airbeeps.agents.resilience.health import HealthRegistry

        registry = HealthRegistry()

        async def check1():
            return True

        async def check2():
            return True

        registry.register("service1", check1)
        registry.register("service2", check2)

        results = await registry.check_all()

        assert "service1" in results
        assert "service2" in results

    def test_get_overall_status_healthy(self):
        """Should return healthy when all healthy."""
        from airbeeps.agents.resilience.health import (
            HealthRegistry,
            HealthStatus,
            ServiceHealth,
        )

        registry = HealthRegistry()

        async def healthy():
            return True

        checker = registry.register("service", healthy)
        checker._last_result = ServiceHealth(
            name="service", status=HealthStatus.HEALTHY
        )

        assert registry.get_overall_status() == HealthStatus.HEALTHY

    def test_get_overall_status_unhealthy(self):
        """Should return unhealthy if any unhealthy."""
        from airbeeps.agents.resilience.health import (
            HealthRegistry,
            HealthStatus,
            ServiceHealth,
        )

        registry = HealthRegistry()

        async def check():
            return True

        checker1 = registry.register("service1", check)
        checker2 = registry.register("service2", check)

        checker1._last_result = ServiceHealth(
            name="service1", status=HealthStatus.HEALTHY
        )
        checker2._last_result = ServiceHealth(
            name="service2", status=HealthStatus.UNHEALTHY
        )

        assert registry.get_overall_status() == HealthStatus.UNHEALTHY

    def test_get_summary(self):
        """Should return summary of all checks."""
        from airbeeps.agents.resilience.health import HealthRegistry

        registry = HealthRegistry()

        async def check():
            return True

        registry.register("service", check)

        summary = registry.get_summary()

        assert "overall_status" in summary
        assert "services" in summary
        assert "total_services" in summary

    def test_unregister(self):
        """Should unregister health checker."""
        from airbeeps.agents.resilience.health import HealthRegistry

        registry = HealthRegistry()

        async def check():
            return True

        registry.register("service", check)
        result = registry.unregister("service")

        assert result is True
        assert registry.get("service") is None

    def test_clear(self):
        """Should clear all checkers."""
        from airbeeps.agents.resilience.health import HealthRegistry

        registry = HealthRegistry()

        async def check():
            return True

        registry.register("service1", check)
        registry.register("service2", check)

        registry.clear()

        assert registry.get("service1") is None
        assert registry.get("service2") is None
