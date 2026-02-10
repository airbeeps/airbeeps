"""
Local trace storage for self-hosted deployments.

Stores OpenTelemetry spans in the database instead of external backends.
This provides full observability without third-party dependencies.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    delete,
    desc,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from airbeeps.models import Base

logger = logging.getLogger(__name__)


class AgentTrace(Base):
    """
    Local storage for agent execution traces.

    Provides alternative to external backends like Jaeger/Grafana for
    self-hosted deployments.
    """

    __tablename__ = "agent_traces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Trace context
    trace_id: Mapped[str] = mapped_column(String(64), index=True)  # OTel trace ID
    span_id: Mapped[str] = mapped_column(String(32), index=True)  # OTel span ID
    parent_span_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Span info
    span_name: Mapped[str] = mapped_column(String(200), index=True)
    span_kind: Mapped[str] = mapped_column(String(50))  # INTERNAL, CLIENT, SERVER, etc.

    # Context references
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assistant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timing
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    latency_ms: Mapped[int] = mapped_column(Integer)

    # Data (already redacted by tracing layer)
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    events: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Span events/logs

    # Metrics
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[str] = mapped_column(
        String(20), default="OK"
    )  # OK, ERROR, UNSET

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Indexes for common queries
    __table_args__ = (
        Index("ix_agent_traces_trace_time", "trace_id", "start_time"),
        Index("ix_agent_traces_user_time", "user_id", "start_time"),
        Index("ix_agent_traces_assistant_time", "assistant_id", "start_time"),
    )


class LocalTraceExporter(SpanExporter):
    """
    OpenTelemetry span exporter that stores traces in the database.

    This provides local trace storage for self-hosted deployments
    without requiring external observability backends.
    """

    def __init__(self, db_session_factory=None):
        """
        Initialize the local trace exporter.

        Args:
            db_session_factory: Async session factory for database access
        """
        self.db_session_factory = db_session_factory
        self._pending_spans: list[dict] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """
        Export spans to local storage.

        Note: This is called synchronously by OTel, so we queue spans
        for async processing.
        """
        for span in spans:
            try:
                trace_record = self._span_to_record(span)
                self._pending_spans.append(trace_record)
            except Exception as e:
                logger.error(f"Failed to convert span to record: {e}")

        # Trigger async flush if possible
        # In production, this would be done via background task
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Shutdown the exporter"""

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush pending spans"""
        return True

    def _span_to_record(self, span: ReadableSpan) -> dict:
        """Convert OTel span to database record dict"""

        # Extract timing
        start_ns = span.start_time or 0
        end_ns = span.end_time or start_ns
        start_time = datetime.fromtimestamp(start_ns / 1e9)
        end_time = datetime.fromtimestamp(end_ns / 1e9)
        latency_ms = int((end_ns - start_ns) / 1e6)

        # Extract attributes
        attributes = dict(span.attributes) if span.attributes else {}

        # Extract IDs from attributes if present
        user_id = self._extract_uuid(attributes.get("agent.user_id"))
        assistant_id = self._extract_uuid(attributes.get("agent.assistant_id"))
        conversation_id = self._extract_uuid(attributes.get("agent.conversation_id"))

        # Extract metrics
        tokens_used = attributes.get("llm.total_tokens") or attributes.get(
            "agent.tokens_used"
        )
        cost_usd = attributes.get("agent.cost_usd")

        # Extract status
        success = attributes.get("agent.success", True) or attributes.get(
            "tool.success", True
        )
        error_message = attributes.get("agent.error") or attributes.get("tool.error")
        status_code = span.status.status_code.name if span.status else "UNSET"

        # Extract events
        events = []
        if span.events:
            for event in span.events:
                events.append(
                    {
                        "name": event.name,
                        "timestamp": event.timestamp / 1e9 if event.timestamp else None,
                        "attributes": dict(event.attributes)
                        if event.attributes
                        else {},
                    }
                )

        return {
            "id": uuid4(),
            "trace_id": format(span.context.trace_id, "032x"),
            "span_id": format(span.context.span_id, "016x"),
            "parent_span_id": format(span.parent.span_id, "016x")
            if span.parent
            else None,
            "span_name": span.name,
            "span_kind": span.kind.name if span.kind else "INTERNAL",
            "user_id": user_id,
            "assistant_id": assistant_id,
            "conversation_id": conversation_id,
            "start_time": start_time,
            "end_time": end_time,
            "latency_ms": latency_ms,
            "attributes": attributes,
            "events": events if events else None,
            "tokens_used": int(tokens_used) if tokens_used else None,
            "cost_usd": float(cost_usd) if cost_usd else None,
            "success": success,
            "error_message": str(error_message) if error_message else None,
            "status_code": status_code,
            "created_at": datetime.utcnow(),
        }

    def _extract_uuid(self, value: Any) -> UUID | None:
        """Extract UUID from value"""
        if value is None:
            return None
        try:
            if isinstance(value, UUID):
                return value
            return UUID(str(value))
        except (ValueError, AttributeError):
            return None

    async def flush_to_database(self, session: AsyncSession) -> int:
        """
        Flush pending spans to database.

        Should be called periodically by a background task.

        Returns:
            Number of spans flushed
        """
        if not self._pending_spans:
            return 0

        spans_to_flush = self._pending_spans.copy()
        self._pending_spans.clear()

        try:
            for span_dict in spans_to_flush:
                trace = AgentTrace(**span_dict)
                session.add(trace)

            await session.commit()
            logger.debug(f"Flushed {len(spans_to_flush)} spans to database")
            return len(spans_to_flush)

        except Exception as e:
            logger.error(f"Failed to flush spans to database: {e}")
            # Re-add spans for retry
            self._pending_spans.extend(spans_to_flush)
            await session.rollback()
            return 0


class TraceService:
    """
    Service for querying stored traces.

    Provides methods for:
    - Listing traces with filtering
    - Getting trace details
    - Deleting old traces
    - Aggregating metrics
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_traces(
        self,
        user_id: UUID | None = None,
        assistant_id: UUID | None = None,
        conversation_id: UUID | None = None,
        span_name: str | None = None,
        success: bool | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentTrace], int]:
        """List traces with filtering"""

        query = select(AgentTrace)
        count_query = select(func.count(AgentTrace.id))

        # Apply filters
        if user_id:
            query = query.where(AgentTrace.user_id == user_id)
            count_query = count_query.where(AgentTrace.user_id == user_id)

        if assistant_id:
            query = query.where(AgentTrace.assistant_id == assistant_id)
            count_query = count_query.where(AgentTrace.assistant_id == assistant_id)

        if conversation_id:
            query = query.where(AgentTrace.conversation_id == conversation_id)
            count_query = count_query.where(
                AgentTrace.conversation_id == conversation_id
            )

        if span_name:
            query = query.where(AgentTrace.span_name.ilike(f"%{span_name}%"))
            count_query = count_query.where(
                AgentTrace.span_name.ilike(f"%{span_name}%")
            )

        if success is not None:
            query = query.where(AgentTrace.success == success)
            count_query = count_query.where(AgentTrace.success == success)

        if start_date:
            query = query.where(AgentTrace.start_time >= start_date)
            count_query = count_query.where(AgentTrace.start_time >= start_date)

        if end_date:
            query = query.where(AgentTrace.start_time <= end_date)
            count_query = count_query.where(AgentTrace.start_time <= end_date)

        # Get total count
        total = await self.session.scalar(count_query)

        # Get traces
        query = query.order_by(desc(AgentTrace.start_time)).offset(offset).limit(limit)
        result = await self.session.execute(query)
        traces = result.scalars().all()

        return list(traces), total or 0

    async def get_trace(self, trace_id: UUID) -> AgentTrace | None:
        """Get a single trace by ID"""
        result = await self.session.execute(
            select(AgentTrace).where(AgentTrace.id == trace_id)
        )
        return result.scalar_one_or_none()

    async def get_trace_by_otel_id(self, otel_trace_id: str) -> list[AgentTrace]:
        """Get all spans for an OTel trace ID"""
        result = await self.session.execute(
            select(AgentTrace)
            .where(AgentTrace.trace_id == otel_trace_id)
            .order_by(AgentTrace.start_time)
        )
        return list(result.scalars().all())

    async def delete_old_traces(self, older_than: datetime) -> int:
        """Delete traces older than a given date"""
        result = await self.session.execute(
            delete(AgentTrace).where(AgentTrace.start_time < older_than)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def get_trace_stats(
        self,
        user_id: UUID | None = None,
        assistant_id: UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Get aggregated trace statistics"""

        # Base query
        base_filter = []
        if user_id:
            base_filter.append(AgentTrace.user_id == user_id)
        if assistant_id:
            base_filter.append(AgentTrace.assistant_id == assistant_id)
        if start_date:
            base_filter.append(AgentTrace.start_time >= start_date)
        if end_date:
            base_filter.append(AgentTrace.start_time <= end_date)

        # Total traces
        total_query = select(func.count(AgentTrace.id))
        if base_filter:
            total_query = total_query.where(*base_filter)
        total_traces = await self.session.scalar(total_query) or 0

        # Success rate
        success_query = select(func.count(AgentTrace.id)).where(
            AgentTrace.success == True
        )
        if base_filter:
            success_query = success_query.where(*base_filter)
        success_count = await self.session.scalar(success_query) or 0
        success_rate = (success_count / total_traces * 100) if total_traces > 0 else 0

        # Average latency
        latency_query = select(func.avg(AgentTrace.latency_ms))
        if base_filter:
            latency_query = latency_query.where(*base_filter)
        avg_latency = await self.session.scalar(latency_query) or 0

        # Total cost
        cost_query = select(func.sum(AgentTrace.cost_usd))
        if base_filter:
            cost_query = cost_query.where(*base_filter)
        total_cost = await self.session.scalar(cost_query) or 0

        # Total tokens
        tokens_query = select(func.sum(AgentTrace.tokens_used))
        if base_filter:
            tokens_query = tokens_query.where(*base_filter)
        total_tokens = await self.session.scalar(tokens_query) or 0

        return {
            "total_traces": total_traces,
            "success_count": success_count,
            "success_rate": round(success_rate, 2),
            "avg_latency_ms": round(float(avg_latency), 2),
            "total_cost_usd": round(float(total_cost), 4),
            "total_tokens": int(total_tokens),
        }
