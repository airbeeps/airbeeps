"""
Resilience patterns for agent execution.

This module provides production-ready resilience patterns:
- Retry logic with exponential backoff
- Circuit breakers for failing services
- Health monitoring
- Prometheus metrics

Usage:
    from airbeeps.agents.resilience import (
        execute_with_retry,
        CircuitBreaker,
        get_health_registry,
        get_metrics_recorder,
    )
"""

from airbeeps.agents.resilience.retry import (
    RetryConfig,
    ToolExecutionError,
    LLMExecutionError,
    MCPConnectionError,
    RetryableError,
    NonRetryableError,
    execute_with_retry,
    execute_tool_with_retry,
    execute_llm_with_retry,
    execute_mcp_with_retry,
    create_retry_decorator,
    is_retryable_exception,
    get_retry_delay,
)

from airbeeps.agents.resilience.circuit_breaker import (
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreaker,
    CircuitOpenError,
    CircuitBreakerRegistry,
    get_circuit_breaker,
    circuit_breaker,
)

from airbeeps.agents.resilience.health import (
    HealthStatus,
    ServiceHealth,
    HealthChecker,
    HealthRegistry,
    HealthCheckConfig,
    get_health_registry,
    register_health_check,
)

from airbeeps.agents.resilience.metrics import (
    MetricsRecorder,
    get_metrics_recorder,
    create_metrics_endpoint,
    PROMETHEUS_AVAILABLE,
)

from airbeeps.agents.resilience.api import router as health_router

__all__ = [
    # Retry
    "RetryConfig",
    "ToolExecutionError",
    "LLMExecutionError",
    "MCPConnectionError",
    "RetryableError",
    "NonRetryableError",
    "execute_with_retry",
    "execute_tool_with_retry",
    "execute_llm_with_retry",
    "execute_mcp_with_retry",
    "create_retry_decorator",
    "is_retryable_exception",
    "get_retry_delay",
    # Circuit Breaker
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitBreakerRegistry",
    "get_circuit_breaker",
    "circuit_breaker",
    # Health
    "HealthStatus",
    "ServiceHealth",
    "HealthChecker",
    "HealthRegistry",
    "HealthCheckConfig",
    "get_health_registry",
    "register_health_check",
    # Metrics
    "MetricsRecorder",
    "get_metrics_recorder",
    "create_metrics_endpoint",
    "PROMETHEUS_AVAILABLE",
    # API
    "health_router",
]
