"""
API endpoints for agent tracing and observability.

Provides endpoints for:
- Listing and viewing traces
- Trace statistics
- Trace management (delete old traces)
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.tracing.storage import AgentTrace, TraceService
from airbeeps.auth import current_superuser
from airbeeps.config import settings
from airbeeps.database import get_async_session
from airbeeps.users.models import User

router = APIRouter(prefix="/traces", tags=["Agent Traces"])


# === Schemas ===


class TraceListItem(BaseModel):
    """Trace list item schema"""

    id: UUID
    trace_id: str
    span_id: str
    span_name: str
    span_kind: str
    user_id: UUID | None
    assistant_id: UUID | None
    conversation_id: UUID | None
    start_time: datetime
    end_time: datetime
    latency_ms: int
    tokens_used: int | None
    cost_usd: float | None
    success: bool
    status_code: str
    created_at: datetime

    class Config:
        from_attributes = True


class TraceDetail(TraceListItem):
    """Trace detail schema with full attributes"""

    parent_span_id: str | None
    message_id: UUID | None
    attributes: dict | None
    events: list | None
    error_message: str | None


class TraceListResponse(BaseModel):
    """Paginated trace list response"""

    items: list[TraceListItem]
    total: int
    limit: int
    offset: int


class TraceStatsResponse(BaseModel):
    """Trace statistics response"""

    total_traces: int
    success_count: int
    success_rate: float
    avg_latency_ms: float
    total_cost_usd: float
    total_tokens: int


class TraceDeleteResponse(BaseModel):
    """Trace deletion response"""

    deleted_count: int
    message: str


# === Endpoints ===


@router.get("", response_model=TraceListResponse)
async def list_traces(
    user_id: UUID | None = Query(None, description="Filter by user ID"),
    assistant_id: UUID | None = Query(None, description="Filter by assistant ID"),
    conversation_id: UUID | None = Query(None, description="Filter by conversation ID"),
    span_name: str | None = Query(
        None, description="Filter by span name (partial match)"
    ),
    success: bool | None = Query(None, description="Filter by success status"),
    start_date: datetime | None = Query(None, description="Filter from start date"),
    end_date: datetime | None = Query(None, description="Filter until end date"),
    limit: int = Query(50, ge=1, le=500, description="Number of traces to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List agent traces with optional filtering.

    Requires admin access (configurable via TRACING_ADMIN_ONLY).
    """
    try:
        service = TraceService(session)

        traces, total = await service.list_traces(
            user_id=user_id,
            assistant_id=assistant_id,
            conversation_id=conversation_id,
            span_name=span_name,
            success=success,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        return TraceListResponse(
            items=[TraceListItem.model_validate(t) for t in traces],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        # Handle database schema errors gracefully
        error_msg = str(e)
        if (
            "no such column" in error_msg.lower()
            or "unknown column" in error_msg.lower()
        ):
            raise HTTPException(
                status_code=500,
                detail="Database schema is out of date. Please run database migrations: 'alembic upgrade head'",
            )
        raise


@router.get("/stats", response_model=TraceStatsResponse)
async def get_trace_stats(
    user_id: UUID | None = Query(None, description="Filter by user ID"),
    assistant_id: UUID | None = Query(None, description="Filter by assistant ID"),
    start_date: datetime | None = Query(None, description="Filter from start date"),
    end_date: datetime | None = Query(None, description="Filter until end date"),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get aggregated trace statistics.

    Returns success rates, average latency, cost, and token usage.
    """
    service = TraceService(session)

    stats = await service.get_trace_stats(
        user_id=user_id,
        assistant_id=assistant_id,
        start_date=start_date,
        end_date=end_date,
    )

    return TraceStatsResponse(**stats)


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace(
    trace_id: UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get a single trace by ID.

    Returns full trace details including attributes and events.
    """
    service = TraceService(session)

    trace = await service.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return TraceDetail.model_validate(trace)


@router.get("/otel/{otel_trace_id}", response_model=list[TraceDetail])
async def get_trace_by_otel_id(
    otel_trace_id: str,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get all spans for an OpenTelemetry trace ID.

    Returns all spans in the trace, ordered by start time.
    This is useful for viewing the full trace timeline.
    """
    service = TraceService(session)

    traces = await service.get_trace_by_otel_id(otel_trace_id)
    if not traces:
        raise HTTPException(status_code=404, detail="Trace not found")

    return [TraceDetail.model_validate(t) for t in traces]


@router.delete("/old", response_model=TraceDeleteResponse)
async def delete_old_traces(
    days: int = Query(
        default=None,
        ge=1,
        le=365,
        description="Delete traces older than N days. Defaults to TRACING_RETENTION_DAYS setting.",
    ),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Delete traces older than specified days.

    Uses TRACING_RETENTION_DAYS from settings if days not specified.
    """
    retention_days = days or settings.TRACING_RETENTION_DAYS
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    service = TraceService(session)
    deleted_count = await service.delete_old_traces(cutoff_date)

    return TraceDeleteResponse(
        deleted_count=deleted_count,
        message=f"Deleted {deleted_count} traces older than {retention_days} days",
    )


# === Analytics Endpoints ===


@router.get("/analytics/tools", response_model=dict[str, Any])
async def get_tool_analytics(
    assistant_id: UUID | None = Query(None, description="Filter by assistant ID"),
    start_date: datetime | None = Query(None, description="Start date for analysis"),
    end_date: datetime | None = Query(None, description="End date for analysis"),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get tool usage analytics.

    Returns:
    - Most used tools
    - Success rates per tool
    - Average latency per tool
    """
    import sqlalchemy as sa
    from sqlalchemy import func, select

    # Build base query for tool spans
    query = (
        select(
            AgentTrace.span_name,
            func.count(AgentTrace.id).label("call_count"),
            func.avg(AgentTrace.latency_ms).label("avg_latency_ms"),
            func.sum(func.cast(AgentTrace.success, sa.Integer)).label("success_count"),
        )
        .where(AgentTrace.span_name.like("tool_%"))
        .group_by(AgentTrace.span_name)
    )

    if assistant_id:
        query = query.where(AgentTrace.assistant_id == assistant_id)
    if start_date:
        query = query.where(AgentTrace.start_time >= start_date)
    if end_date:
        query = query.where(AgentTrace.start_time <= end_date)

    result = await session.execute(query)
    rows = result.all()

    tools = []
    for row in rows:
        tool_name = row.span_name.replace("tool_", "")
        call_count = row.call_count or 0
        success_count = row.success_count or 0
        success_rate = (success_count / call_count * 100) if call_count > 0 else 0

        tools.append(
            {
                "tool_name": tool_name,
                "call_count": call_count,
                "success_rate": round(success_rate, 2),
                "avg_latency_ms": round(row.avg_latency_ms or 0, 2),
            }
        )

    # Sort by call count
    tools.sort(key=lambda x: x["call_count"], reverse=True)

    return {
        "tools": tools,
        "total_tool_calls": sum(t["call_count"] for t in tools),
    }


@router.get("/analytics/cost", response_model=dict[str, Any])
async def get_cost_analytics(
    assistant_id: UUID | None = Query(None, description="Filter by assistant ID"),
    user_id: UUID | None = Query(None, description="Filter by user ID"),
    start_date: datetime | None = Query(None, description="Start date for analysis"),
    end_date: datetime | None = Query(None, description="End date for analysis"),
    group_by: str = Query(
        "day", enum=["day", "week", "month"], description="Time grouping"
    ),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get cost analytics over time.

    Returns cost breakdown by time period.
    """
    from sqlalchemy import func, select

    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Build query with date grouping
    if group_by == "day":
        date_trunc = func.date(AgentTrace.start_time)
    elif group_by == "week":
        # SQLite doesn't have date_trunc, so we use strftime
        date_trunc = func.strftime("%Y-%W", AgentTrace.start_time)
    else:  # month
        date_trunc = func.strftime("%Y-%m", AgentTrace.start_time)

    query = (
        select(
            date_trunc.label("period"),
            func.sum(AgentTrace.cost_usd).label("total_cost"),
            func.sum(AgentTrace.tokens_used).label("total_tokens"),
            func.count(AgentTrace.id).label("trace_count"),
        )
        .where(
            AgentTrace.start_time >= start_date,
            AgentTrace.start_time <= end_date,
        )
        .group_by(date_trunc)
        .order_by(date_trunc)
    )

    if assistant_id:
        query = query.where(AgentTrace.assistant_id == assistant_id)
    if user_id:
        query = query.where(AgentTrace.user_id == user_id)

    result = await session.execute(query)
    rows = result.all()

    periods = []
    for row in rows:
        periods.append(
            {
                "period": str(row.period),
                "total_cost_usd": round(float(row.total_cost or 0), 4),
                "total_tokens": int(row.total_tokens or 0),
                "trace_count": row.trace_count,
            }
        )

    total_cost = sum(p["total_cost_usd"] for p in periods)
    total_tokens = sum(p["total_tokens"] for p in periods)

    return {
        "periods": periods,
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "group_by": group_by,
    }
