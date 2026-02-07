"""
OpenTelemetry tracing configuration - vendor-agnostic.

Supports multiple backends:
- local: Store traces in database (default for self-hosted)
- otlp: Export to any OTLP-compatible backend
- jaeger: Export to Jaeger
- console: Print to console (development)
- none: Disable tracing
"""

import logging
from enum import Enum
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TracingBackend(str, Enum):
    """Supported tracing backends"""

    NONE = "none"
    LOCAL = "local"
    OTLP = "otlp"
    JAEGER = "jaeger"
    CONSOLE = "console"


class TracingConfig:
    """Vendor-agnostic tracing configuration"""

    def __init__(
        self,
        backend: TracingBackend = TracingBackend.LOCAL,
        endpoint: str | None = None,
        service_name: str = "airbeeps-agents",
        enable_pii_redaction: bool = True,
        sample_rate: float = 1.0,
        admin_only: bool = True,
    ):
        self.backend = backend
        self.endpoint = endpoint
        self.service_name = service_name
        self.enable_pii_redaction = enable_pii_redaction
        self.sample_rate = sample_rate
        self.admin_only = admin_only
        self._tracer_provider: TracerProvider | None = None
        self._local_exporter = None

    def setup_tracing(self, db_session_factory=None) -> trace.Tracer:
        """Configure OpenTelemetry based on backend choice"""

        # Create resource with service name
        resource = Resource.create(
            {
                SERVICE_NAME: self.service_name,
                "service.version": "1.0.0",
                "deployment.environment": "production",
            }
        )

        # Create provider
        provider = TracerProvider(resource=resource)

        # Create exporter based on backend
        exporter = self._create_exporter(db_session_factory)

        if exporter is not None:
            # Use BatchSpanProcessor for production, SimpleSpanProcessor for console
            if self.backend == TracingBackend.CONSOLE:
                processor = SimpleSpanProcessor(exporter)
            else:
                processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)

        # Set as global provider
        trace.set_tracer_provider(provider)
        self._tracer_provider = provider

        logger.info(
            f"OpenTelemetry tracing configured with backend: {self.backend.value}"
        )

        return trace.get_tracer(self.service_name)

    def _create_exporter(self, db_session_factory=None):
        """Create exporter based on backend configuration"""

        if self.backend == TracingBackend.NONE:
            logger.info("Tracing disabled")
            return None

        elif self.backend == TracingBackend.OTLP:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            if not self.endpoint:
                logger.warning("OTLP endpoint not configured, falling back to console")
                return ConsoleSpanExporter()

            logger.info(f"Exporting traces to OTLP endpoint: {self.endpoint}")
            return OTLPSpanExporter(endpoint=self.endpoint)

        elif self.backend == TracingBackend.JAEGER:
            try:
                from opentelemetry.exporter.jaeger.thrift import JaegerExporter

                # Parse endpoint for Jaeger (expects host:port format)
                if self.endpoint:
                    parts = (
                        self.endpoint.replace("http://", "")
                        .replace("https://", "")
                        .split(":")
                    )
                    host = parts[0]
                    port = int(parts[1]) if len(parts) > 1 else 6831
                else:
                    host = "localhost"
                    port = 6831

                logger.info(f"Exporting traces to Jaeger: {host}:{port}")
                return JaegerExporter(
                    agent_host_name=host,
                    agent_port=port,
                )
            except ImportError:
                logger.warning("Jaeger exporter not installed, falling back to console")
                return ConsoleSpanExporter()

        elif self.backend == TracingBackend.CONSOLE:
            logger.info("Exporting traces to console")
            return ConsoleSpanExporter()

        elif self.backend == TracingBackend.LOCAL:
            # Import here to avoid circular imports
            from airbeeps.agents.tracing.storage import LocalTraceExporter

            logger.info("Storing traces in local database")
            self._local_exporter = LocalTraceExporter(db_session_factory)
            return self._local_exporter

        else:
            logger.warning(f"Unknown tracing backend: {self.backend}, disabling")
            return None

    def shutdown(self):
        """Shutdown tracing provider"""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")


# Global tracer instance
_tracer: trace.Tracer | None = None
_config: TracingConfig | None = None


def setup_global_tracing(
    config: TracingConfig, db_session_factory=None
) -> trace.Tracer:
    """Setup global tracing with given configuration"""
    global _tracer, _config
    _config = config
    _tracer = config.setup_tracing(db_session_factory)
    return _tracer


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance"""
    global _tracer
    if _tracer is None:
        # Return a no-op tracer if not configured
        return trace.get_tracer("airbeeps-agents")
    return _tracer


def get_tracing_config() -> TracingConfig | None:
    """Get the global tracing configuration"""
    return _config
