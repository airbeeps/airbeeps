"""
Audit log API endpoints.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.audit.models import AuditAction, AuditLog
from airbeeps.audit.service import AuditService
from airbeeps.database import get_async_session
from airbeeps.users.models import User
from airbeeps.auth import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


class AuditLogResponse(BaseModel):
    """Response model for a single audit log entry"""

    id: UUID
    user_id: UUID | None
    user_email: str | None
    action: str
    entity_type: str
    entity_id: str | None
    entity_name: str | None
    description: str | None
    changes: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Response model for paginated audit log list"""

    items: list[AuditLogResponse]
    total: int
    offset: int
    limit: int


class AuditStatsResponse(BaseModel):
    """Response model for audit statistics"""

    total_logs: int
    period_days: int
    actions_by_type: dict[str, int]
    actions_by_entity: dict[str, int]


def require_admin(current_user: User = Depends(current_active_user)) -> User:
    """Dependency to require admin/superuser access"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="List audit logs",
)
async def list_audit_logs(
    entity_type: str | None = Query(None, description="Filter by entity type"),
    entity_id: str | None = Query(None, description="Filter by entity ID"),
    user_id: UUID | None = Query(None, description="Filter by user ID"),
    action: AuditAction | None = Query(None, description="Filter by action type"),
    start_date: datetime | None = Query(None, description="Start date filter"),
    end_date: datetime | None = Query(None, description="End date filter"),
    search: str | None = Query(None, description="Search in entity name/description"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_admin),
):
    """
    List audit logs with optional filters.

    Requires admin/superuser access.
    """
    logs, total = await AuditService.get_logs(
        session=session,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
        search=search,
        offset=offset,
        limit=limit,
    )

    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                user_email=log.user_email,
                action=log.action.value,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                entity_name=log.entity_name,
                description=log.description,
                changes=log.changes,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/stats",
    response_model=AuditStatsResponse,
    summary="Get audit log statistics",
)
async def get_audit_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_admin),
):
    """
    Get audit log statistics for the specified period.

    Requires admin/superuser access.
    """
    stats = await AuditService.get_stats(session=session, days=days)
    return AuditStatsResponse(**stats)


@router.get(
    "/actions",
    summary="Get available audit action types",
)
async def get_audit_actions(
    current_user: User = Depends(require_admin),
):
    """Get list of available audit action types for filtering."""
    return {
        "actions": [action.value for action in AuditAction],
    }


@router.get(
    "/entity-types",
    summary="Get entity types with audit logs",
)
async def get_entity_types(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_admin),
):
    """Get list of entity types that have audit logs."""
    from sqlalchemy import distinct, select

    query = select(distinct(AuditLog.entity_type)).order_by(AuditLog.entity_type)
    result = await session.execute(query)
    entity_types = [row[0] for row in result.all()]

    return {"entity_types": entity_types}
