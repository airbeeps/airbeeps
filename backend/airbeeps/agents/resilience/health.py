"""
Health monitoring for agent services.

Provides health checks for:
- MCP servers
- LLM providers
- Database connections
- Tool availability
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check result status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health status for a single service."""

    name: str
    status: HealthStatus
    message: str | None = None
    latency_ms: float | None = None
    last_check: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "last_check": self.last_check,
            "metadata": self.metadata,
        }


@dataclass
class HealthCheckConfig:
    """Configuration for health checks."""

    # Timeout for individual health checks
    check_timeout_seconds: float = 5.0

    # Latency thresholds (ms)
    healthy_latency_threshold: float = 1000.0
    degraded_latency_threshold: float = 5000.0

    # How often to run periodic checks (seconds)
    check_interval: float = 30.0

    # Cache health results for this long (seconds)
    cache_ttl: float = 10.0


class HealthChecker:
    """
    Health checker for monitoring service availability.

    Runs health checks and caches results.
    """

    def __init__(
        self,
        name: str,
        check_func: Callable[[], Any],
        config: HealthCheckConfig | None = None,
    ):
        """
        Initialize a health checker.

        Args:
            name: Service name
            check_func: Async function that raises exception if unhealthy
            config: Health check configuration
        """
        self.name = name
        self.check_func = check_func
        self.config = config or HealthCheckConfig()

        self._last_result: ServiceHealth | None = None
        self._check_in_progress = False
        self._lock = asyncio.Lock()

    @property
    def last_result(self) -> ServiceHealth | None:
        """Get the last health check result."""
        return self._last_result

    @property
    def is_healthy(self) -> bool:
        """Check if the last result was healthy."""
        if self._last_result is None:
            return False
        return self._last_result.status == HealthStatus.HEALTHY

    async def check(self, force: bool = False) -> ServiceHealth:
        """
        Run a health check.

        Args:
            force: If True, bypass cache and run check

        Returns:
            ServiceHealth result
        """
        # Check cache
        if not force and self._last_result is not None:
            age = time.time() - self._last_result.last_check
            if age < self.config.cache_ttl:
                return self._last_result

        # Avoid concurrent checks
        async with self._lock:
            if self._check_in_progress and not force:
                if self._last_result:
                    return self._last_result
                return ServiceHealth(
                    name=self.name,
                    status=HealthStatus.UNKNOWN,
                    message="Check in progress",
                )

            self._check_in_progress = True

        try:
            start_time = time.time()

            try:
                await asyncio.wait_for(
                    self._run_check(),
                    timeout=self.config.check_timeout_seconds,
                )

                latency_ms = (time.time() - start_time) * 1000

                # Determine status based on latency
                if latency_ms <= self.config.healthy_latency_threshold:
                    status = HealthStatus.HEALTHY
                elif latency_ms <= self.config.degraded_latency_threshold:
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.DEGRADED

                result = ServiceHealth(
                    name=self.name,
                    status=status,
                    latency_ms=latency_ms,
                    message="OK" if status == HealthStatus.HEALTHY else "Slow response",
                )

            except asyncio.TimeoutError:
                result = ServiceHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Timeout after {self.config.check_timeout_seconds}s",
                    latency_ms=self.config.check_timeout_seconds * 1000,
                )

            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                result = ServiceHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e)[:200],
                    latency_ms=latency_ms,
                    metadata={"error_type": type(e).__name__},
                )

            self._last_result = result
            return result

        finally:
            self._check_in_progress = False

    async def _run_check(self) -> Any:
        """Run the actual health check function."""
        if asyncio.iscoroutinefunction(self.check_func):
            return await self.check_func()
        else:
            return self.check_func()


class HealthRegistry:
    """
    Registry for managing multiple health checkers.

    Usage:
        registry = HealthRegistry()

        # Register a checker
        registry.register(
            name="database",
            check_func=check_database,
        )

        # Run all checks
        results = await registry.check_all()
    """

    _instance: "HealthRegistry | None" = None

    def __init__(self):
        self._checkers: dict[str, HealthChecker] = {}
        self._background_task: asyncio.Task | None = None
        self._config = HealthCheckConfig()

    @classmethod
    def get_instance(cls) -> "HealthRegistry":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        name: str,
        check_func: Callable[[], Any],
        config: HealthCheckConfig | None = None,
    ) -> HealthChecker:
        """
        Register a health checker.

        Args:
            name: Service name
            check_func: Async function that raises if unhealthy
            config: Health check configuration

        Returns:
            HealthChecker instance
        """
        checker = HealthChecker(name, check_func, config or self._config)
        self._checkers[name] = checker
        logger.debug(f"Registered health checker: {name}")
        return checker

    def unregister(self, name: str) -> bool:
        """Unregister a health checker."""
        if name in self._checkers:
            del self._checkers[name]
            return True
        return False

    def get(self, name: str) -> HealthChecker | None:
        """Get a health checker by name."""
        return self._checkers.get(name)

    async def check(self, name: str, force: bool = False) -> ServiceHealth | None:
        """
        Run a health check for a specific service.

        Args:
            name: Service name
            force: Bypass cache

        Returns:
            ServiceHealth or None if not found
        """
        checker = self._checkers.get(name)
        if checker is None:
            return None
        return await checker.check(force=force)

    async def check_all(self, force: bool = False) -> dict[str, ServiceHealth]:
        """
        Run health checks for all registered services.

        Args:
            force: Bypass cache for all checks

        Returns:
            Dict of service name to ServiceHealth
        """
        tasks = []
        names = []
        for name, checker in self._checkers.items():
            names.append(name)
            tasks.append(checker.check(force=force))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_results = {}
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                health_results[name] = ServiceHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(result),
                )
            else:
                health_results[name] = result

        return health_results

    def get_overall_status(self) -> HealthStatus:
        """
        Get overall health status based on all checkers.

        Returns:
            HEALTHY if all healthy
            DEGRADED if any degraded
            UNHEALTHY if any unhealthy
            UNKNOWN if no checkers or no results
        """
        if not self._checkers:
            return HealthStatus.UNKNOWN

        statuses = []
        for checker in self._checkers.values():
            if checker.last_result:
                statuses.append(checker.last_result.status)

        if not statuses:
            return HealthStatus.UNKNOWN

        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY

        return HealthStatus.UNKNOWN

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all health check results."""
        results = {}
        for name, checker in self._checkers.items():
            if checker.last_result:
                results[name] = checker.last_result.to_dict()
            else:
                results[name] = {
                    "name": name,
                    "status": "unknown",
                    "message": "No health check run yet",
                }

        return {
            "overall_status": self.get_overall_status().value,
            "services": results,
            "total_services": len(self._checkers),
            "healthy_count": sum(1 for c in self._checkers.values() if c.is_healthy),
        }

    async def start_background_checks(self, interval: float | None = None) -> None:
        """
        Start periodic background health checks.

        Args:
            interval: Check interval in seconds (default from config)
        """
        if self._background_task is not None:
            return

        interval = interval or self._config.check_interval

        async def _run_periodic():
            while True:
                try:
                    await self.check_all()
                except Exception as e:
                    logger.error(f"Background health check error: {e}")
                await asyncio.sleep(interval)

        self._background_task = asyncio.create_task(_run_periodic())
        logger.info(f"Started background health checks (interval: {interval}s)")

    async def stop_background_checks(self) -> None:
        """Stop periodic background health checks."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
            logger.info("Stopped background health checks")

    def clear(self) -> None:
        """Clear all registered health checkers."""
        self._checkers.clear()


# ============================================================================
# Pre-built Health Check Functions
# ============================================================================


async def check_database_health(session_factory) -> None:
    """
    Health check for database connection.

    Raises:
        Exception: If database is unreachable
    """
    from sqlalchemy import text

    async with session_factory() as session:
        await session.execute(text("SELECT 1"))


async def check_mcp_server_health(mcp_client, server_name: str) -> None:
    """
    Health check for MCP server.

    Raises:
        Exception: If server is unreachable
    """
    tools = await mcp_client.list_tools(server_name)
    if tools is None:
        raise ConnectionError(f"MCP server '{server_name}' unreachable")


async def check_llm_provider_health(litellm_client, model: str) -> None:
    """
    Health check for LLM provider.

    Raises:
        Exception: If provider is unreachable
    """
    # Simple completion test
    await litellm_client.acompletion(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
    )


# ============================================================================
# Convenience Functions
# ============================================================================


def get_health_registry() -> HealthRegistry:
    """Get the singleton health registry."""
    return HealthRegistry.get_instance()


def register_health_check(
    name: str,
    check_func: Callable[[], Any],
    config: HealthCheckConfig | None = None,
) -> HealthChecker:
    """
    Register a health check with the global registry.

    Args:
        name: Service name
        check_func: Health check function
        config: Configuration

    Returns:
        HealthChecker instance
    """
    return get_health_registry().register(name, check_func, config)
