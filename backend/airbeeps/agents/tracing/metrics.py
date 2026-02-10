"""
OpenTelemetry Metrics Collection for Agents.

Provides metrics for:
- Tool call counts and success rates
- Agent execution iterations
- Cost tracking
- Latency histograms
"""

import logging

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and records agent-related metrics.

    Provides counters, histograms, and gauges for:
    - Tool usage
    - Agent performance
    - Cost tracking
    """

    def __init__(self, service_name: str = "airbeeps-agents"):
        self.service_name = service_name
        self._meter = metrics.get_meter(service_name)
        self._setup_metrics()

    def _setup_metrics(self):
        """Initialize all metric instruments"""

        # === Counters ===

        # Tool call counter
        self.tool_call_counter = self._meter.create_counter(
            name="agent.tool_calls.total",
            description="Total number of tool calls",
            unit="1",
        )

        # Agent execution counter
        self.agent_execution_counter = self._meter.create_counter(
            name="agent.executions.total",
            description="Total number of agent executions",
            unit="1",
        )

        # LLM call counter
        self.llm_call_counter = self._meter.create_counter(
            name="agent.llm_calls.total",
            description="Total number of LLM API calls",
            unit="1",
        )

        # Retrieval counter
        self.retrieval_counter = self._meter.create_counter(
            name="agent.retrievals.total",
            description="Total number of retrieval operations",
            unit="1",
        )

        # Error counter
        self.error_counter = self._meter.create_counter(
            name="agent.errors.total",
            description="Total number of errors",
            unit="1",
        )

        # === Histograms ===

        # Tool latency histogram
        self.tool_latency_histogram = self._meter.create_histogram(
            name="agent.tool_calls.latency",
            description="Latency of tool calls in milliseconds",
            unit="ms",
        )

        # Agent execution latency
        self.agent_latency_histogram = self._meter.create_histogram(
            name="agent.executions.latency",
            description="Latency of agent executions in milliseconds",
            unit="ms",
        )

        # LLM latency histogram
        self.llm_latency_histogram = self._meter.create_histogram(
            name="agent.llm_calls.latency",
            description="Latency of LLM calls in milliseconds",
            unit="ms",
        )

        # Iteration histogram
        self.iteration_histogram = self._meter.create_histogram(
            name="agent.iterations.count",
            description="Number of iterations per agent execution",
            unit="1",
        )

        # Token usage histogram
        self.token_histogram = self._meter.create_histogram(
            name="agent.tokens.used",
            description="Tokens used per operation",
            unit="1",
        )

        # Cost histogram
        self.cost_histogram = self._meter.create_histogram(
            name="agent.cost.usd",
            description="Cost per operation in USD",
            unit="$",
        )

        # Retrieval result count histogram
        self.retrieval_results_histogram = self._meter.create_histogram(
            name="agent.retrievals.result_count",
            description="Number of results per retrieval",
            unit="1",
        )

    # === Recording Methods ===

    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float,
        assistant_id: str | None = None,
    ):
        """Record a tool call metric"""
        attributes = {
            "tool.name": tool_name,
            "tool.success": str(success),
        }
        if assistant_id:
            attributes["assistant.id"] = assistant_id

        self.tool_call_counter.add(1, attributes)
        self.tool_latency_histogram.record(latency_ms, attributes)

        if not success:
            self.error_counter.add(
                1,
                {
                    "error.type": "tool_failure",
                    "tool.name": tool_name,
                },
            )

    def record_agent_execution(
        self,
        success: bool,
        latency_ms: float,
        iterations: int,
        cost_usd: float = 0.0,
        tokens_used: int = 0,
        assistant_id: str | None = None,
    ):
        """Record an agent execution metric"""
        attributes = {
            "agent.success": str(success),
        }
        if assistant_id:
            attributes["assistant.id"] = assistant_id

        self.agent_execution_counter.add(1, attributes)
        self.agent_latency_histogram.record(latency_ms, attributes)
        self.iteration_histogram.record(iterations, attributes)

        if cost_usd > 0:
            self.cost_histogram.record(cost_usd, attributes)

        if tokens_used > 0:
            self.token_histogram.record(tokens_used, attributes)

        if not success:
            self.error_counter.add(
                1,
                {
                    "error.type": "agent_failure",
                    **attributes,
                },
            )

    def record_llm_call(
        self,
        model: str,
        success: bool,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ):
        """Record an LLM API call metric"""
        attributes = {
            "llm.model": model,
            "llm.success": str(success),
        }

        self.llm_call_counter.add(1, attributes)
        self.llm_latency_histogram.record(latency_ms, attributes)

        total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 0:
            self.token_histogram.record(
                total_tokens,
                {
                    **attributes,
                    "token.type": "total",
                },
            )

        if cost_usd > 0:
            self.cost_histogram.record(cost_usd, attributes)

        if not success:
            self.error_counter.add(
                1,
                {
                    "error.type": "llm_failure",
                    "llm.model": model,
                },
            )

    def record_retrieval(
        self,
        source: str,
        success: bool,
        latency_ms: float,
        result_count: int = 0,
        kb_id: str | None = None,
    ):
        """Record a retrieval operation metric"""
        attributes = {
            "retrieval.source": source,
            "retrieval.success": str(success),
        }
        if kb_id:
            attributes["kb.id"] = kb_id

        self.retrieval_counter.add(1, attributes)

        if success:
            self.retrieval_results_histogram.record(result_count, attributes)

        # Latency is tracked in the main histogram
        self.tool_latency_histogram.record(
            latency_ms,
            {
                "tool.name": f"retrieval_{source}",
                "tool.success": str(success),
            },
        )

        if not success:
            self.error_counter.add(
                1,
                {
                    "error.type": "retrieval_failure",
                    "retrieval.source": source,
                },
            )

    def record_error(
        self,
        error_type: str,
        error_message: str,
        context: dict[str, str] | None = None,
    ):
        """Record a generic error metric"""
        attributes = {
            "error.type": error_type,
        }
        if context:
            attributes.update(context)

        self.error_counter.add(1, attributes)


# Global metrics collector instance
_metrics_collector: MetricsCollector | None = None


def setup_metrics(
    service_name: str = "airbeeps-agents", enable_console: bool = False
) -> MetricsCollector:
    """
    Setup global metrics collection.

    Args:
        service_name: Name of the service for metrics
        enable_console: Whether to enable console export (for debugging)

    Returns:
        MetricsCollector instance
    """
    global _metrics_collector

    # Setup meter provider
    if enable_console:
        reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(),
            export_interval_millis=60000,  # Export every minute
        )
        provider = MeterProvider(metric_readers=[reader])
    else:
        provider = MeterProvider()

    metrics.set_meter_provider(provider)

    _metrics_collector = MetricsCollector(service_name)
    logger.info(f"Metrics collection initialized for service: {service_name}")

    return _metrics_collector


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
