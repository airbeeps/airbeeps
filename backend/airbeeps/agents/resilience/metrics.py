"""
Prometheus metrics for agent resilience monitoring.

Provides metrics for:
- Circuit breaker states
- Retry attempts
- Health check status
- Error rates
"""

import logging

logger = logging.getLogger(__name__)

# Attempt to import prometheus_client, gracefully handle if not installed
try:
    from prometheus_client import Counter, Gauge, Histogram, Info

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.info("prometheus_client not installed, metrics will be no-ops")


# ============================================================================
# Metric Definitions
# ============================================================================

if PROMETHEUS_AVAILABLE:
    # Circuit breaker metrics
    CIRCUIT_BREAKER_STATE = Gauge(
        "airbeeps_circuit_breaker_state",
        "Current state of circuit breaker (0=closed, 1=open, 2=half_open)",
        ["circuit_name"],
    )

    CIRCUIT_BREAKER_FAILURES = Counter(
        "airbeeps_circuit_breaker_failures_total",
        "Total number of failures recorded by circuit breaker",
        ["circuit_name"],
    )

    CIRCUIT_BREAKER_SUCCESSES = Counter(
        "airbeeps_circuit_breaker_successes_total",
        "Total number of successes recorded by circuit breaker",
        ["circuit_name"],
    )

    CIRCUIT_BREAKER_OPENS = Counter(
        "airbeeps_circuit_breaker_opens_total",
        "Total number of times circuit breaker opened",
        ["circuit_name"],
    )

    # Retry metrics
    RETRY_ATTEMPTS = Counter(
        "airbeeps_retry_attempts_total",
        "Total number of retry attempts",
        ["operation", "success"],
    )

    RETRY_EXHAUSTED = Counter(
        "airbeeps_retry_exhausted_total",
        "Total number of times retries were exhausted",
        ["operation"],
    )

    # Health check metrics
    HEALTH_CHECK_STATUS = Gauge(
        "airbeeps_health_check_status",
        "Health check status (0=unhealthy, 1=degraded, 2=healthy)",
        ["service"],
    )

    HEALTH_CHECK_LATENCY = Histogram(
        "airbeeps_health_check_latency_seconds",
        "Health check latency in seconds",
        ["service"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    # Agent execution metrics
    AGENT_EXECUTION_TOTAL = Counter(
        "airbeeps_agent_executions_total",
        "Total number of agent executions",
        ["assistant_id", "status"],
    )

    AGENT_EXECUTION_DURATION = Histogram(
        "airbeeps_agent_execution_duration_seconds",
        "Agent execution duration in seconds",
        ["assistant_id"],
        buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    )

    AGENT_ITERATIONS = Histogram(
        "airbeeps_agent_iterations",
        "Number of iterations per agent execution",
        ["assistant_id"],
        buckets=(1, 2, 3, 5, 7, 10, 15, 20),
    )

    AGENT_COST = Histogram(
        "airbeeps_agent_cost_usd",
        "Cost per agent execution in USD",
        ["assistant_id"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    )

    # Tool execution metrics
    TOOL_EXECUTION_TOTAL = Counter(
        "airbeeps_tool_executions_total",
        "Total number of tool executions",
        ["tool_name", "status"],
    )

    TOOL_EXECUTION_DURATION = Histogram(
        "airbeeps_tool_execution_duration_seconds",
        "Tool execution duration in seconds",
        ["tool_name"],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    )

    # Multi-agent metrics
    MULTIAGENT_HANDOFFS = Counter(
        "airbeeps_multiagent_handoffs_total",
        "Total number of multi-agent handoffs",
        ["from_specialist", "to_specialist"],
    )

    MULTIAGENT_LOOPS_DETECTED = Counter(
        "airbeeps_multiagent_loops_detected_total",
        "Total number of detected loops in multi-agent execution",
    )


# ============================================================================
# Metric Recording Functions
# ============================================================================


class MetricsRecorder:
    """Records metrics for resilience monitoring."""

    def __init__(self):
        self.enabled = PROMETHEUS_AVAILABLE

    def record_circuit_breaker_state(
        self,
        circuit_name: str,
        state: str,
    ) -> None:
        """Record circuit breaker state change."""
        if not self.enabled:
            return

        state_value = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}.get(state, -1)
        CIRCUIT_BREAKER_STATE.labels(circuit_name=circuit_name).set(state_value)

        if state == "OPEN":
            CIRCUIT_BREAKER_OPENS.labels(circuit_name=circuit_name).inc()

    def record_circuit_breaker_result(
        self,
        circuit_name: str,
        success: bool,
    ) -> None:
        """Record circuit breaker call result."""
        if not self.enabled:
            return

        if success:
            CIRCUIT_BREAKER_SUCCESSES.labels(circuit_name=circuit_name).inc()
        else:
            CIRCUIT_BREAKER_FAILURES.labels(circuit_name=circuit_name).inc()

    def record_retry_attempt(
        self,
        operation: str,
        attempt: int,
        success: bool,
    ) -> None:
        """Record a retry attempt."""
        if not self.enabled:
            return

        RETRY_ATTEMPTS.labels(
            operation=operation,
            success=str(success).lower(),
        ).inc()

    def record_retry_exhausted(self, operation: str) -> None:
        """Record when retries are exhausted."""
        if not self.enabled:
            return

        RETRY_EXHAUSTED.labels(operation=operation).inc()

    def record_health_check(
        self,
        service: str,
        status: str,
        latency_seconds: float,
    ) -> None:
        """Record health check result."""
        if not self.enabled:
            return

        status_value = {"healthy": 2, "degraded": 1, "unhealthy": 0}.get(status, -1)
        HEALTH_CHECK_STATUS.labels(service=service).set(status_value)
        HEALTH_CHECK_LATENCY.labels(service=service).observe(latency_seconds)

    def record_agent_execution(
        self,
        assistant_id: str,
        status: str,
        duration_seconds: float,
        iterations: int,
        cost_usd: float,
    ) -> None:
        """Record agent execution metrics."""
        if not self.enabled:
            return

        AGENT_EXECUTION_TOTAL.labels(
            assistant_id=assistant_id,
            status=status,
        ).inc()
        AGENT_EXECUTION_DURATION.labels(assistant_id=assistant_id).observe(
            duration_seconds
        )
        AGENT_ITERATIONS.labels(assistant_id=assistant_id).observe(iterations)
        AGENT_COST.labels(assistant_id=assistant_id).observe(cost_usd)

    def record_tool_execution(
        self,
        tool_name: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        """Record tool execution metrics."""
        if not self.enabled:
            return

        TOOL_EXECUTION_TOTAL.labels(tool_name=tool_name, status=status).inc()
        TOOL_EXECUTION_DURATION.labels(tool_name=tool_name).observe(duration_seconds)

    def record_multiagent_handoff(
        self,
        from_specialist: str,
        to_specialist: str,
    ) -> None:
        """Record multi-agent handoff."""
        if not self.enabled:
            return

        MULTIAGENT_HANDOFFS.labels(
            from_specialist=from_specialist,
            to_specialist=to_specialist,
        ).inc()

    def record_multiagent_loop(self) -> None:
        """Record detected multi-agent loop."""
        if not self.enabled:
            return

        MULTIAGENT_LOOPS_DETECTED.inc()


# Global instance
_metrics_recorder: MetricsRecorder | None = None


def get_metrics_recorder() -> MetricsRecorder:
    """Get the global metrics recorder instance."""
    global _metrics_recorder
    if _metrics_recorder is None:
        _metrics_recorder = MetricsRecorder()
    return _metrics_recorder


# ============================================================================
# FastAPI Integration
# ============================================================================


def create_metrics_endpoint():
    """
    Create a FastAPI route for Prometheus metrics.

    Usage:
        from airbeeps.agents.resilience.metrics import create_metrics_endpoint

        app = FastAPI()
        metrics_router = create_metrics_endpoint()
        app.include_router(metrics_router, prefix="/metrics")
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("prometheus_client not available, /metrics endpoint disabled")
        return None

    from fastapi import APIRouter, Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    router = APIRouter()

    @router.get("")
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return router
