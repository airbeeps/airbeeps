"""
Vendor-agnostic observability module using OpenTelemetry.

Supports multiple backends:
- local: Store traces in database
- otlp: Export to any OTLP-compatible backend (Grafana, Honeycomb, etc.)
- jaeger: Export to Jaeger
- console: Print to console (development)
"""

from airbeeps.agents.tracing.config import TracingConfig, TracingBackend
from airbeeps.agents.tracing.pii_redactor import PIIRedactor
from airbeeps.agents.tracing.instrumentation import (
    trace_agent_execution,
    trace_tool_call,
    trace_llm_call,
    trace_retrieval,
    get_tracer,
)
from airbeeps.agents.tracing.metrics import MetricsCollector, get_metrics_collector
from airbeeps.agents.tracing.storage import LocalTraceExporter

__all__ = [
    "TracingConfig",
    "TracingBackend",
    "PIIRedactor",
    "trace_agent_execution",
    "trace_tool_call",
    "trace_llm_call",
    "trace_retrieval",
    "get_tracer",
    "MetricsCollector",
    "get_metrics_collector",
    "LocalTraceExporter",
]
