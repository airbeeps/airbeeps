"""
Instrumentation decorators and utilities for tracing agent execution.

Provides decorators and context managers for:
- Agent execution spans
- Tool call spans
- LLM call spans
- Retrieval spans
"""

import functools
import json
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, ParamSpec, TypeVar

from opentelemetry.trace import SpanKind, Status, StatusCode

from airbeeps.agents.tracing.config import get_tracer
from airbeeps.agents.tracing.pii_redactor import get_redactor

P = ParamSpec("P")
R = TypeVar("R")


def _safe_json(data: Any, max_length: int = 1000) -> str:
    """Safely convert data to JSON string with length limit"""
    try:
        result = json.dumps(data, default=str)
        if len(result) > max_length:
            return result[:max_length] + "...[truncated]"
        return result
    except Exception:
        return str(data)[:max_length]


def trace_agent_execution(
    name: str = "agent_execution",
    include_input: bool = True,
    include_output: bool = True,
):
    """
    Decorator to trace agent execution.

    Args:
        name: Span name
        include_input: Whether to include input in span attributes
        include_output: Whether to include output in span attributes
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = get_tracer()
            redactor = get_redactor()

            with tracer.start_as_current_span(
                name,
                kind=SpanKind.INTERNAL,
            ) as span:
                start_time = time.time()

                # Set common attributes
                span.set_attribute("agent.trace_id", str(uuid.uuid4()))

                # Extract and set input attributes
                if include_input and kwargs:
                    user_input = kwargs.get("user_input", "")
                    if user_input:
                        redacted_input = redactor.redact(str(user_input))
                        span.set_attribute("agent.input", redacted_input[:500])
                        span.set_attribute("agent.input_length", len(str(user_input)))

                    # Set context attributes
                    if "assistant_id" in kwargs:
                        span.set_attribute(
                            "agent.assistant_id", str(kwargs["assistant_id"])
                        )
                    if "user_id" in kwargs:
                        span.set_attribute("agent.user_id", str(kwargs["user_id"]))
                    if "conversation_id" in kwargs:
                        span.set_attribute(
                            "agent.conversation_id", str(kwargs["conversation_id"])
                        )

                try:
                    result = await func(*args, **kwargs)

                    # Set success attributes
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("agent.latency_ms", latency_ms)
                    span.set_attribute("agent.success", True)

                    # Set output attributes
                    if include_output and isinstance(result, dict):
                        if "iterations" in result:
                            span.set_attribute("agent.iterations", result["iterations"])
                        if "token_usage" in result:
                            span.set_attribute(
                                "agent.token_usage", _safe_json(result["token_usage"])
                            )
                        if "cost_spent" in result:
                            span.set_attribute("agent.cost_usd", result["cost_spent"])
                        if "output" in result:
                            redacted_output = redactor.redact(str(result["output"]))
                            span.set_attribute(
                                "agent.output_preview", redacted_output[:500]
                            )

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("agent.latency_ms", latency_ms)
                    span.set_attribute("agent.success", False)
                    span.set_attribute("agent.error", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator


def trace_tool_call(
    tool_name: str | None = None,
    include_input: bool = True,
    include_output: bool = True,
):
    """
    Decorator to trace tool execution.

    Args:
        tool_name: Override tool name (defaults to function name)
        include_input: Whether to include input in span attributes
        include_output: Whether to include output in span attributes
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = get_tracer()
            redactor = get_redactor()

            span_name = f"tool_{tool_name or func.__name__}"

            with tracer.start_as_current_span(
                span_name,
                kind=SpanKind.INTERNAL,
            ) as span:
                start_time = time.time()

                span.set_attribute("tool.name", tool_name or func.__name__)

                # Set input attributes
                if include_input and kwargs:
                    redacted_input = redactor.redact_dict(dict(kwargs))
                    span.set_attribute("tool.input", _safe_json(redacted_input))

                try:
                    result = await func(*args, **kwargs)

                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("tool.latency_ms", latency_ms)
                    span.set_attribute("tool.success", True)

                    if include_output:
                        redacted_output = redactor.redact(str(result))
                        span.set_attribute("tool.output_preview", redacted_output[:500])

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("tool.latency_ms", latency_ms)
                    span.set_attribute("tool.success", False)
                    span.set_attribute("tool.error", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator


def trace_llm_call(
    model_name: str | None = None,
    include_prompt: bool = False,  # Default False for privacy
    include_response: bool = True,
):
    """
    Decorator to trace LLM API calls.

    Args:
        model_name: Override model name
        include_prompt: Whether to include prompt in span (privacy concern)
        include_response: Whether to include response preview
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = get_tracer()
            redactor = get_redactor()

            with tracer.start_as_current_span(
                "llm_call",
                kind=SpanKind.CLIENT,
            ) as span:
                start_time = time.time()

                span.set_attribute(
                    "llm.model", model_name or kwargs.get("model", "unknown")
                )

                if include_prompt:
                    messages = kwargs.get("messages", [])
                    if messages:
                        redacted_messages = redactor.redact_value(messages)
                        span.set_attribute(
                            "llm.prompt_preview", _safe_json(redacted_messages, 500)
                        )

                try:
                    result = await func(*args, **kwargs)

                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("llm.latency_ms", latency_ms)
                    span.set_attribute("llm.success", True)

                    # Extract token usage if available
                    if hasattr(result, "usage"):
                        span.set_attribute(
                            "llm.prompt_tokens",
                            getattr(result.usage, "prompt_tokens", 0),
                        )
                        span.set_attribute(
                            "llm.completion_tokens",
                            getattr(result.usage, "completion_tokens", 0),
                        )
                        span.set_attribute(
                            "llm.total_tokens", getattr(result.usage, "total_tokens", 0)
                        )

                    if include_response and hasattr(result, "content"):
                        redacted_response = redactor.redact(str(result.content))
                        span.set_attribute(
                            "llm.response_preview", redacted_response[:500]
                        )

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("llm.latency_ms", latency_ms)
                    span.set_attribute("llm.success", False)
                    span.set_attribute("llm.error", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator


def trace_retrieval(
    source: str = "knowledge_base",
    include_query: bool = True,
    include_results: bool = True,
):
    """
    Decorator to trace RAG retrieval operations.

    Args:
        source: Retrieval source name
        include_query: Whether to include query
        include_results: Whether to include result previews
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = get_tracer()
            redactor = get_redactor()

            with tracer.start_as_current_span(
                f"retrieval_{source}",
                kind=SpanKind.CLIENT,
            ) as span:
                start_time = time.time()

                span.set_attribute("retrieval.source", source)

                if include_query:
                    query = kwargs.get("query", "")
                    if query:
                        redacted_query = redactor.redact(str(query))
                        span.set_attribute("retrieval.query", redacted_query[:200])

                if "kb_id" in kwargs:
                    span.set_attribute("retrieval.kb_id", str(kwargs["kb_id"]))
                if "top_k" in kwargs:
                    span.set_attribute("retrieval.top_k", kwargs["top_k"])

                try:
                    result = await func(*args, **kwargs)

                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("retrieval.latency_ms", latency_ms)
                    span.set_attribute("retrieval.success", True)

                    # Record result count
                    if isinstance(result, list):
                        span.set_attribute("retrieval.result_count", len(result))

                        if include_results and result:
                            # Include first result preview
                            first_result = result[0]
                            if hasattr(first_result, "text"):
                                redacted = redactor.redact(str(first_result.text))
                                span.set_attribute(
                                    "retrieval.first_result_preview", redacted[:300]
                                )
                            elif (
                                isinstance(first_result, dict)
                                and "text" in first_result
                            ):
                                redacted = redactor.redact(str(first_result["text"]))
                                span.set_attribute(
                                    "retrieval.first_result_preview", redacted[:300]
                                )

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("retrieval.latency_ms", latency_ms)
                    span.set_attribute("retrieval.success", False)
                    span.set_attribute("retrieval.error", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator


@asynccontextmanager
async def trace_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
):
    """
    Async context manager for creating trace spans.

    Args:
        name: Span name
        kind: Span kind
        attributes: Initial span attributes

    Usage:
        async with trace_span("my_operation", attributes={"key": "value"}) as span:
            # Do work
            span.set_attribute("result", "success")
    """
    tracer = get_tracer()

    with tracer.start_as_current_span(name, kind=kind) as span:
        start_time = time.time()

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        try:
            yield span
            latency_ms = (time.time() - start_time) * 1000
            span.set_attribute("latency_ms", latency_ms)
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            span.set_attribute("latency_ms", latency_ms)
            span.set_attribute("error", str(e))
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


class TracedAgentExecutor:
    """
    Wrapper to add tracing to an agent executor.

    Wraps execute and stream_execute methods with OpenTelemetry tracing.
    """

    def __init__(
        self, executor, assistant_id: str | None = None, user_id: str | None = None
    ):
        self.executor = executor
        self.assistant_id = assistant_id
        self.user_id = user_id

    async def execute(self, user_input: str, **kwargs) -> dict[str, Any]:
        """Execute with tracing"""
        tracer = get_tracer()
        redactor = get_redactor()

        with tracer.start_as_current_span("agent_execution") as span:
            start_time = time.time()

            # Set context
            span.set_attribute(
                "agent.assistant_id",
                str(self.assistant_id or kwargs.get("assistant_id", "")),
            )
            span.set_attribute(
                "agent.user_id", str(self.user_id or kwargs.get("user_id", ""))
            )
            span.set_attribute("agent.input_length", len(user_input))

            # Redacted input preview
            redacted_input = redactor.redact(user_input)
            span.set_attribute("agent.input_preview", redacted_input[:500])

            try:
                result = await self.executor.execute(user_input, **kwargs)

                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("agent.latency_ms", latency_ms)
                span.set_attribute("agent.success", True)

                # Set result attributes
                if isinstance(result, dict):
                    span.set_attribute("agent.iterations", result.get("iterations", 0))
                    span.set_attribute("agent.cost_usd", result.get("cost_spent", 0.0))

                    if "output" in result:
                        redacted_output = redactor.redact(str(result["output"]))
                        span.set_attribute(
                            "agent.output_preview", redacted_output[:500]
                        )

                span.set_status(Status(StatusCode.OK))
                return result

            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("agent.latency_ms", latency_ms)
                span.set_attribute("agent.success", False)
                span.set_attribute("agent.error", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def stream_execute(self, user_input: str, **kwargs):
        """Stream execute with tracing"""
        tracer = get_tracer()
        redactor = get_redactor()

        with tracer.start_as_current_span("agent_stream_execution") as span:
            start_time = time.time()

            span.set_attribute(
                "agent.assistant_id",
                str(self.assistant_id or kwargs.get("assistant_id", "")),
            )
            span.set_attribute(
                "agent.user_id", str(self.user_id or kwargs.get("user_id", ""))
            )
            span.set_attribute("agent.input_length", len(user_input))

            redacted_input = redactor.redact(user_input)
            span.set_attribute("agent.input_preview", redacted_input[:500])

            try:
                event_count = 0
                async for event in self.executor.stream_execute(user_input, **kwargs):
                    event_count += 1
                    yield event

                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("agent.latency_ms", latency_ms)
                span.set_attribute("agent.success", True)
                span.set_attribute("agent.event_count", event_count)
                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("agent.latency_ms", latency_ms)
                span.set_attribute("agent.success", False)
                span.set_attribute("agent.error", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
