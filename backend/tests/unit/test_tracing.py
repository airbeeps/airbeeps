"""
Unit tests for Tracing Module.

Tests for tracing instrumentation and PII redaction.
Note: These tests mock OpenTelemetry to avoid real span creation.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestTracingPIIRedactor:
    """Tests for tracing-specific PII redaction."""

    def test_pii_redactor_import(self):
        """Should be able to import PII redactor from tracing module."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()
        assert redactor is not None

    def test_redact_basic_pii(self):
        """Should redact basic PII patterns."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        # Test email redaction
        text = "Contact: user@example.com"
        result = redactor.redact(text)
        assert "user@example.com" not in result
        assert "[REDACTED" in result

    def test_redact_in_trace_attributes(self):
        """Should redact PII in trace attribute values."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        attributes = {
            "user_query": "My email is john@example.com",
            "tool_input": {"email": "test@test.com", "name": "John"},
        }

        # Redact string values
        redacted_query = redactor.redact(attributes["user_query"])
        assert "john@example.com" not in redacted_query


class TestTracingConfig:
    """Tests for tracing configuration."""

    def test_tracing_config_defaults(self):
        """Should have sensible defaults."""
        from airbeeps.agents.tracing.config import TracingConfig

        config = TracingConfig()

        assert config.service_name == "airbeeps-agents"
        assert config.enable_pii_redaction is True
        assert config.sample_rate == 1.0

    def test_tracing_backends(self):
        """Should support multiple backends."""
        from airbeeps.agents.tracing.config import TracingBackend

        assert TracingBackend.CONSOLE is not None
        assert TracingBackend.OTLP is not None
        assert TracingBackend.JAEGER is not None
        assert TracingBackend.LOCAL is not None


class TestTraceStorage:
    """Tests for local trace storage."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        from unittest.mock import AsyncMock

        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_trace_service_list(self, mock_session):
        """Should list traces from database."""
        from airbeeps.agents.tracing.storage import TraceService

        service = TraceService(session=mock_session)

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await service.list_traces()

        # list_traces returns a tuple (traces, count) or similar
        assert result is not None
        mock_session.execute.assert_called()


class TestTracingDecorators:
    """Tests for tracing decorators (with mocked OpenTelemetry)."""

    def test_trace_agent_execution_decorator_exists(self):
        """Should be able to import tracing decorators."""
        from airbeeps.agents.tracing.instrumentation import (
            trace_agent_execution,
            trace_tool_call,
            trace_llm_call,
        )

        assert callable(trace_agent_execution)
        assert callable(trace_tool_call)
        assert callable(trace_llm_call)

    @pytest.mark.asyncio
    async def test_trace_agent_execution_passthrough(self):
        """Decorator should pass through function execution."""
        from airbeeps.agents.tracing.instrumentation import trace_agent_execution

        @trace_agent_execution(name="test_agent")
        async def my_agent_func(x):
            return x * 2

        # Should execute and return result
        result = await my_agent_func(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_trace_tool_call_passthrough(self):
        """Decorator should pass through function execution."""
        from airbeeps.agents.tracing.instrumentation import trace_tool_call

        @trace_tool_call(tool_name="test_tool")
        async def my_tool_func(query):
            return f"Result: {query}"

        result = await my_tool_func("test")
        assert result == "Result: test"

    @pytest.mark.asyncio
    async def test_trace_llm_call_passthrough(self):
        """Decorator should pass through function execution."""
        from airbeeps.agents.tracing.instrumentation import trace_llm_call

        @trace_llm_call(model_name="test-model")
        async def my_llm_func(messages):
            return {"content": "response"}

        result = await my_llm_func([{"role": "user", "content": "hi"}])
        assert result["content"] == "response"


class TestMetricsCollector:
    """Tests for metrics collection."""

    def test_metrics_collector_creation(self):
        """Should create metrics collector."""
        from airbeeps.agents.tracing.metrics import MetricsCollector

        collector = MetricsCollector()
        assert collector is not None

    def test_record_llm_call(self):
        """Should record LLM call metrics."""
        from airbeeps.agents.tracing.metrics import MetricsCollector

        collector = MetricsCollector()

        # Should not raise
        collector.record_llm_call(
            model="gpt-4",
            success=True,
            latency_ms=500,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
        )

    def test_record_tool_call(self):
        """Should record tool call metrics."""
        from airbeeps.agents.tracing.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.record_tool_call(
            tool_name="web_search",
            success=True,
            latency_ms=200,
        )

    def test_record_agent_execution(self):
        """Should record agent execution metrics."""
        from airbeeps.agents.tracing.metrics import MetricsCollector

        collector = MetricsCollector()

        collector.record_agent_execution(
            success=True,
            latency_ms=5000,
            iterations=3,
            cost_usd=0.05,
            tokens_used=1000,
        )
