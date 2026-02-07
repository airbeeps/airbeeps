"""
Tool Approval Service.

Manages approval workflows for high-risk tool usage.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.models import (
    ApprovalStatusEnum,
    ToolApprovalRequest,
    ToolApprovalPolicy,
)

logger = logging.getLogger(__name__)


class ApprovalService:
    """
    Service for managing tool approval requests and policies.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize approval service.

        Args:
            session: Database session
        """
        self.session = session

    # =========================================================================
    # Approval Requests
    # =========================================================================

    async def request_approval(
        self,
        user_id: uuid.UUID,
        tool_name: str,
        reason: str,
        parameters: dict[str, Any] | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> ToolApprovalRequest:
        """
        Request approval for using a tool.

        Args:
            user_id: User requesting approval
            tool_name: Name of the tool
            reason: Justification for the request
            parameters: Parameters the user wants to use
            conversation_id: Optional conversation context

        Returns:
            Created approval request
        """
        # Check if there's already a valid approval
        existing = await self.check_approval(user_id, tool_name)
        if existing:
            return existing

        # Check for auto-approval
        policy = await self.get_policy(tool_name)
        auto_status = await self._check_auto_approve(user_id, tool_name, policy)

        # Determine expiration
        expires_at = None
        max_uses = None
        if policy:
            if policy.default_expiration_hours:
                expires_at = datetime.utcnow() + timedelta(
                    hours=policy.default_expiration_hours
                )
            max_uses = policy.default_max_uses

        request = ToolApprovalRequest(
            user_id=user_id,
            tool_name=tool_name,
            reason=reason,
            requested_parameters=parameters or {},
            conversation_id=conversation_id,
            status=auto_status if auto_status else ApprovalStatusEnum.PENDING,
            expires_at=expires_at,
            max_uses=max_uses,
        )

        # If auto-approved, set review info
        if auto_status == ApprovalStatusEnum.APPROVED:
            request.reviewed_at = datetime.utcnow()
            request.reviewer_notes = "Auto-approved by policy"

        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)

        logger.info(
            f"Approval request created: user={user_id}, tool={tool_name}, "
            f"status={request.status.value}"
        )
        return request

    async def check_approval(
        self,
        user_id: uuid.UUID,
        tool_name: str,
    ) -> ToolApprovalRequest | None:
        """
        Check if user has a valid approval for a tool.

        Args:
            user_id: User ID
            tool_name: Tool name

        Returns:
            Valid approval if exists, None otherwise
        """
        now = datetime.utcnow()

        stmt = select(ToolApprovalRequest).where(
            ToolApprovalRequest.user_id == user_id,
            ToolApprovalRequest.tool_name == tool_name,
            ToolApprovalRequest.status == ApprovalStatusEnum.APPROVED,
            or_(
                ToolApprovalRequest.expires_at.is_(None),
                ToolApprovalRequest.expires_at > now,
            ),
        )

        result = await self.session.execute(stmt)
        approval = result.scalars().first()

        if approval and approval.is_valid():
            return approval

        return None

    async def approve_request(
        self,
        request_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        notes: str | None = None,
        expires_at: datetime | None = None,
        max_uses: int | None = None,
    ) -> ToolApprovalRequest | None:
        """
        Approve a tool approval request.

        Args:
            request_id: Request ID
            reviewer_id: Reviewer user ID
            notes: Reviewer notes
            expires_at: Override expiration
            max_uses: Override max uses

        Returns:
            Updated request or None if not found
        """
        stmt = select(ToolApprovalRequest).where(
            ToolApprovalRequest.id == request_id,
            ToolApprovalRequest.status == ApprovalStatusEnum.PENDING,
        )
        result = await self.session.execute(stmt)
        request = result.scalars().first()

        if not request:
            return None

        request.status = ApprovalStatusEnum.APPROVED
        request.reviewed_by_id = reviewer_id
        request.reviewed_at = datetime.utcnow()
        request.reviewer_notes = notes

        if expires_at:
            request.expires_at = expires_at
        if max_uses is not None:
            request.max_uses = max_uses

        await self.session.commit()
        await self.session.refresh(request)

        logger.info(
            f"Approval request approved: id={request_id}, "
            f"reviewer={reviewer_id}, tool={request.tool_name}"
        )
        return request

    async def reject_request(
        self,
        request_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        notes: str | None = None,
    ) -> ToolApprovalRequest | None:
        """
        Reject a tool approval request.

        Args:
            request_id: Request ID
            reviewer_id: Reviewer user ID
            notes: Rejection reason

        Returns:
            Updated request or None if not found
        """
        stmt = select(ToolApprovalRequest).where(
            ToolApprovalRequest.id == request_id,
            ToolApprovalRequest.status == ApprovalStatusEnum.PENDING,
        )
        result = await self.session.execute(stmt)
        request = result.scalars().first()

        if not request:
            return None

        request.status = ApprovalStatusEnum.REJECTED
        request.reviewed_by_id = reviewer_id
        request.reviewed_at = datetime.utcnow()
        request.reviewer_notes = notes

        await self.session.commit()
        await self.session.refresh(request)

        logger.info(
            f"Approval request rejected: id={request_id}, "
            f"reviewer={reviewer_id}, tool={request.tool_name}"
        )
        return request

    async def use_approval(
        self,
        user_id: uuid.UUID,
        tool_name: str,
    ) -> bool:
        """
        Record usage of an approval.

        Args:
            user_id: User ID
            tool_name: Tool name

        Returns:
            True if approval was valid and incremented, False otherwise
        """
        approval = await self.check_approval(user_id, tool_name)
        if not approval:
            return False

        approval.uses_count += 1
        await self.session.commit()

        return True

    async def get_pending_requests(
        self,
        tool_name: str | None = None,
        limit: int = 50,
    ) -> list[ToolApprovalRequest]:
        """Get all pending approval requests."""
        stmt = (
            select(ToolApprovalRequest)
            .where(ToolApprovalRequest.status == ApprovalStatusEnum.PENDING)
            .order_by(ToolApprovalRequest.created_at)
            .limit(limit)
        )

        if tool_name:
            stmt = stmt.where(ToolApprovalRequest.tool_name == tool_name)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_requests(
        self,
        user_id: uuid.UUID,
        status: ApprovalStatusEnum | None = None,
        limit: int = 50,
    ) -> list[ToolApprovalRequest]:
        """Get approval requests for a user."""
        stmt = (
            select(ToolApprovalRequest)
            .where(ToolApprovalRequest.user_id == user_id)
            .order_by(ToolApprovalRequest.created_at.desc())
            .limit(limit)
        )

        if status:
            stmt = stmt.where(ToolApprovalRequest.status == status)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def expire_old_requests(self, days: int = 7) -> int:
        """Expire old pending requests."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = select(ToolApprovalRequest).where(
            ToolApprovalRequest.status == ApprovalStatusEnum.PENDING,
            ToolApprovalRequest.created_at < cutoff,
        )
        result = await self.session.execute(stmt)
        old_requests = result.scalars().all()

        count = 0
        for request in old_requests:
            request.status = ApprovalStatusEnum.EXPIRED
            count += 1

        await self.session.commit()

        if count > 0:
            logger.info(f"Expired {count} old approval requests")

        return count

    # =========================================================================
    # Approval Policies
    # =========================================================================

    async def get_policy(self, tool_name: str) -> ToolApprovalPolicy | None:
        """Get approval policy for a tool."""
        # First check for tool-specific policy
        stmt = select(ToolApprovalPolicy).where(
            ToolApprovalPolicy.tool_name == tool_name
        )
        result = await self.session.execute(stmt)
        policy = result.scalars().first()

        if policy:
            return policy

        # Fall back to default policy
        stmt = select(ToolApprovalPolicy).where(ToolApprovalPolicy.tool_name == "*")
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_policy(
        self,
        tool_name: str,
        auto_approve_enabled: bool = False,
        auto_approve_conditions: dict[str, Any] | None = None,
        default_expiration_hours: int | None = None,
        default_max_uses: int | None = None,
        notify_on_request: bool = True,
    ) -> ToolApprovalPolicy:
        """Create or update an approval policy."""
        stmt = select(ToolApprovalPolicy).where(
            ToolApprovalPolicy.tool_name == tool_name
        )
        result = await self.session.execute(stmt)
        policy = result.scalars().first()

        if policy:
            policy.auto_approve_enabled = auto_approve_enabled
            policy.auto_approve_conditions = auto_approve_conditions or {}
            policy.default_expiration_hours = default_expiration_hours
            policy.default_max_uses = default_max_uses
            policy.notify_on_request = notify_on_request
        else:
            policy = ToolApprovalPolicy(
                tool_name=tool_name,
                auto_approve_enabled=auto_approve_enabled,
                auto_approve_conditions=auto_approve_conditions or {},
                default_expiration_hours=default_expiration_hours,
                default_max_uses=default_max_uses,
                notify_on_request=notify_on_request,
            )
            self.session.add(policy)

        await self.session.commit()
        await self.session.refresh(policy)
        return policy

    async def list_policies(self) -> list[ToolApprovalPolicy]:
        """List all approval policies."""
        stmt = select(ToolApprovalPolicy).order_by(ToolApprovalPolicy.tool_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_policy(self, tool_name: str) -> bool:
        """Delete an approval policy."""
        stmt = select(ToolApprovalPolicy).where(
            ToolApprovalPolicy.tool_name == tool_name
        )
        result = await self.session.execute(stmt)
        policy = result.scalars().first()

        if not policy:
            return False

        await self.session.delete(policy)
        await self.session.commit()
        return True

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _check_auto_approve(
        self,
        user_id: uuid.UUID,
        tool_name: str,
        policy: ToolApprovalPolicy | None,
    ) -> ApprovalStatusEnum | None:
        """Check if request should be auto-approved based on policy."""
        if not policy or not policy.auto_approve_enabled:
            return None

        conditions = policy.auto_approve_conditions

        # Check allowed users
        allowed_users = conditions.get("allowed_users", [])
        if allowed_users and str(user_id) not in allowed_users:
            return None

        # Check daily limit
        max_daily_uses = conditions.get("max_daily_uses")
        if max_daily_uses:
            today_start = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            stmt = select(ToolApprovalRequest).where(
                ToolApprovalRequest.user_id == user_id,
                ToolApprovalRequest.tool_name == tool_name,
                ToolApprovalRequest.created_at >= today_start,
            )
            result = await self.session.execute(stmt)
            today_count = len(result.scalars().all())

            if today_count >= max_daily_uses:
                return None

        return ApprovalStatusEnum.APPROVED


async def create_approval_service(session: AsyncSession) -> ApprovalService:
    """Create an approval service instance with given session."""
    return ApprovalService(session=session)
