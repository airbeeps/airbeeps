"""
Audit logging service for tracking administrative operations.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.audit.models import AuditAction, AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """
    Service for creating and querying audit logs.
    """

    @staticmethod
    async def log(
        session: AsyncSession,
        action: AuditAction,
        entity_type: str,
        entity_id: str | UUID | None = None,
        entity_name: str | None = None,
        user_id: UUID | None = None,
        user_email: str | None = None,
        description: str | None = None,
        changes: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> AuditLog:
        """
        Create an audit log entry.

        Args:
            session: Database session
            action: Type of action performed
            entity_type: Type of entity affected (e.g., "assistant", "user")
            entity_id: ID of the affected entity
            entity_name: Display name of the entity
            user_id: ID of the user who performed the action
            user_email: Email of the user
            description: Human-readable description
            changes: Dict with "before" and "after" for update actions
            ip_address: Client IP address
            user_agent: Client user agent string
            metadata: Additional metadata
            request: FastAPI request object (to extract IP/user agent)

        Returns:
            Created AuditLog instance
        """
        # Extract request info if provided
        if request:
            if not ip_address:
                # Get real IP, considering proxies
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    ip_address = forwarded.split(",")[0].strip()
                else:
                    ip_address = request.client.host if request.client else None

            if not user_agent:
                user_agent = request.headers.get("User-Agent", "")[:500]

        # Convert UUID to string if needed
        entity_id_str = str(entity_id) if entity_id else None

        audit_log = AuditLog(
            user_id=user_id,
            user_email=user_email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id_str,
            entity_name=entity_name,
            description=description,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )

        session.add(audit_log)
        await session.flush()

        logger.info(
            f"Audit log created: {action.value} on {entity_type} "
            f"(id={entity_id_str}) by user {user_email or user_id}"
        )

        return audit_log

    @staticmethod
    async def get_logs(
        session: AsyncSession,
        entity_type: str | None = None,
        entity_id: str | None = None,
        user_id: UUID | None = None,
        action: AuditAction | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """
        Query audit logs with filters.

        Returns:
            Tuple of (logs, total_count)
        """
        conditions = []

        if entity_type:
            conditions.append(AuditLog.entity_type == entity_type)

        if entity_id:
            conditions.append(AuditLog.entity_id == entity_id)

        if user_id:
            conditions.append(AuditLog.user_id == user_id)

        if action:
            conditions.append(AuditLog.action == action)

        if start_date:
            conditions.append(AuditLog.created_at >= start_date)

        if end_date:
            conditions.append(AuditLog.created_at <= end_date)

        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    AuditLog.entity_name.ilike(search_pattern),
                    AuditLog.description.ilike(search_pattern),
                    AuditLog.user_email.ilike(search_pattern),
                )
            )

        # Build query
        base_query = select(AuditLog)
        if conditions:
            base_query = base_query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = await session.scalar(count_query) or 0

        # Get paginated results
        query = (
            base_query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
        )

        result = await session.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    @staticmethod
    async def get_stats(
        session: AsyncSession,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Get audit log statistics.

        Returns:
            Dict with stats like actions by type, by entity, by day
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        # Count by action type
        action_counts_query = (
            select(AuditLog.action, func.count(AuditLog.id))
            .where(AuditLog.created_at >= start_date)
            .group_by(AuditLog.action)
        )
        action_result = await session.execute(action_counts_query)
        actions_by_type = {action.value: count for action, count in action_result.all()}

        # Count by entity type
        entity_counts_query = (
            select(AuditLog.entity_type, func.count(AuditLog.id))
            .where(AuditLog.created_at >= start_date)
            .group_by(AuditLog.entity_type)
        )
        entity_result = await session.execute(entity_counts_query)
        actions_by_entity = dict(entity_result.all())

        # Total count
        total_query = select(func.count(AuditLog.id)).where(
            AuditLog.created_at >= start_date
        )
        total = await session.scalar(total_query) or 0

        return {
            "total_logs": total,
            "period_days": days,
            "actions_by_type": actions_by_type,
            "actions_by_entity": actions_by_entity,
        }
