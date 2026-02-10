"""
Tool Approval API Endpoints.

Provides endpoints for:
- Requesting tool approvals
- Approving/rejecting requests (admin)
- Managing approval policies (admin)
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.models import ApprovalStatusEnum
from airbeeps.agents.security.approval_service import ApprovalService
from airbeeps.auth import current_active_user, current_superuser
from airbeeps.database import get_async_session
from airbeeps.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["Tool Approvals"])
admin_router = APIRouter(prefix="/approvals", tags=["Tool Approvals Admin"])


# =============================================================================
# Schemas
# =============================================================================


class ApprovalRequestCreate(BaseModel):
    """Request to create a tool approval request."""

    tool_name: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(..., min_length=1, max_length=2000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None


class ApprovalRequestResponse(BaseModel):
    """Response for approval request."""

    id: str
    user_id: str
    tool_name: str
    reason: str
    requested_parameters: dict[str, Any]
    conversation_id: str | None
    status: str
    reviewed_by_id: str | None
    reviewed_at: str | None
    reviewer_notes: str | None
    expires_at: str | None
    max_uses: int | None
    uses_count: int
    created_at: str | None


class ApprovalDecision(BaseModel):
    """Decision for approving/rejecting a request."""

    notes: str | None = None
    expires_at: str | None = Field(
        default=None,
        description="ISO format datetime for expiration (for approval only)",
    )
    max_uses: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of uses (for approval only)",
    )


class ApprovalPolicyCreate(BaseModel):
    """Request to create/update an approval policy."""

    tool_name: str = Field(..., min_length=1, max_length=100)
    auto_approve_enabled: bool = False
    auto_approve_conditions: dict[str, Any] = Field(default_factory=dict)
    default_expiration_hours: int | None = Field(default=None, ge=1)
    default_max_uses: int | None = Field(default=None, ge=1)
    notify_on_request: bool = True


class ApprovalPolicyResponse(BaseModel):
    """Response for approval policy."""

    id: str
    tool_name: str
    auto_approve_enabled: bool
    auto_approve_conditions: dict[str, Any]
    default_expiration_hours: int | None
    default_max_uses: int | None
    notify_on_request: bool


class ApprovalStats(BaseModel):
    """Statistics about approval requests."""

    pending_count: int
    approved_count: int
    rejected_count: int
    expired_count: int
    by_tool: dict[str, int]


# =============================================================================
# Helper Functions
# =============================================================================


async def get_approval_service(
    session: AsyncSession = Depends(get_async_session),
) -> ApprovalService:
    """Get approval service for request."""
    return ApprovalService(session=session)


def format_request(request: Any) -> ApprovalRequestResponse:
    """Format an approval request for response."""
    return ApprovalRequestResponse(
        id=str(request.id),
        user_id=str(request.user_id),
        tool_name=request.tool_name,
        reason=request.reason,
        requested_parameters=request.requested_parameters,
        conversation_id=str(request.conversation_id)
        if request.conversation_id
        else None,
        status=request.status.value,
        reviewed_by_id=str(request.reviewed_by_id) if request.reviewed_by_id else None,
        reviewed_at=request.reviewed_at.isoformat() if request.reviewed_at else None,
        reviewer_notes=request.reviewer_notes,
        expires_at=request.expires_at.isoformat() if request.expires_at else None,
        max_uses=request.max_uses,
        uses_count=request.uses_count,
        created_at=request.created_at.isoformat() if request.created_at else None,
    )


# =============================================================================
# User Endpoints
# =============================================================================


@router.post("", response_model=ApprovalRequestResponse)
async def request_approval(
    body: ApprovalRequestCreate,
    current_user: User = Depends(current_active_user),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalRequestResponse:
    """
    Request approval for using a tool.

    Creates a new approval request that will be reviewed by an admin.
    """
    conversation_id = uuid.UUID(body.conversation_id) if body.conversation_id else None

    request = await service.request_approval(
        user_id=current_user.id,
        tool_name=body.tool_name,
        reason=body.reason,
        parameters=body.parameters,
        conversation_id=conversation_id,
    )

    return format_request(request)


@router.get("/check/{tool_name}")
async def check_approval_status(
    tool_name: str,
    current_user: User = Depends(current_active_user),
    service: ApprovalService = Depends(get_approval_service),
) -> dict[str, Any]:
    """
    Check if user has a valid approval for a tool.

    Returns approval status and remaining uses if approved.
    """
    approval = await service.check_approval(current_user.id, tool_name)

    if approval:
        remaining = None
        if approval.max_uses is not None:
            remaining = approval.max_uses - approval.uses_count

        return {
            "has_approval": True,
            "approval_id": str(approval.id),
            "expires_at": approval.expires_at.isoformat()
            if approval.expires_at
            else None,
            "remaining_uses": remaining,
        }

    return {"has_approval": False}


@router.get("/my-requests", response_model=list[ApprovalRequestResponse])
async def list_my_requests(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(current_active_user),
    service: ApprovalService = Depends(get_approval_service),
) -> list[ApprovalRequestResponse]:
    """List the current user's approval requests."""
    status_enum = None
    if status:
        try:
            status_enum = ApprovalStatusEnum(status.upper())
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    requests = await service.get_user_requests(
        user_id=current_user.id,
        status=status_enum,
        limit=limit,
    )

    return [format_request(r) for r in requests]


# =============================================================================
# Admin Endpoints
# =============================================================================


@admin_router.get("/pending", response_model=list[ApprovalRequestResponse])
async def list_pending_requests(
    tool_name: str | None = Query(None, description="Filter by tool"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> list[ApprovalRequestResponse]:
    """List all pending approval requests (admin only)."""
    requests = await service.get_pending_requests(
        tool_name=tool_name,
        limit=limit,
    )
    return [format_request(r) for r in requests]


@admin_router.post("/{request_id}/approve", response_model=ApprovalRequestResponse)
async def approve_request(
    request_id: str,
    body: ApprovalDecision,
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalRequestResponse:
    """Approve a tool approval request (admin only)."""
    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(400, "Invalid request ID")

    expires_at = None
    if body.expires_at:
        try:
            expires_at = datetime.fromisoformat(body.expires_at)
        except ValueError:
            raise HTTPException(400, "Invalid expiration date format")

    request = await service.approve_request(
        request_id=request_uuid,
        reviewer_id=current_user.id,
        notes=body.notes,
        expires_at=expires_at,
        max_uses=body.max_uses,
    )

    if not request:
        raise HTTPException(404, "Request not found or already processed")

    return format_request(request)


@admin_router.post("/{request_id}/reject", response_model=ApprovalRequestResponse)
async def reject_request(
    request_id: str,
    body: ApprovalDecision,
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalRequestResponse:
    """Reject a tool approval request (admin only)."""
    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(400, "Invalid request ID")

    request = await service.reject_request(
        request_id=request_uuid,
        reviewer_id=current_user.id,
        notes=body.notes,
    )

    if not request:
        raise HTTPException(404, "Request not found or already processed")

    return format_request(request)


@admin_router.post("/expire-old")
async def expire_old_requests(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> dict[str, Any]:
    """Expire old pending requests (admin only)."""
    count = await service.expire_old_requests(days=days)
    return {"status": "success", "expired_count": count}


# =============================================================================
# Policy Endpoints (Admin)
# =============================================================================


@admin_router.get("/policies", response_model=list[ApprovalPolicyResponse])
async def list_policies(
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> list[ApprovalPolicyResponse]:
    """List all approval policies (admin only)."""
    policies = await service.list_policies()
    return [
        ApprovalPolicyResponse(
            id=str(p.id),
            tool_name=p.tool_name,
            auto_approve_enabled=p.auto_approve_enabled,
            auto_approve_conditions=p.auto_approve_conditions,
            default_expiration_hours=p.default_expiration_hours,
            default_max_uses=p.default_max_uses,
            notify_on_request=p.notify_on_request,
        )
        for p in policies
    ]


@admin_router.post("/policies", response_model=ApprovalPolicyResponse)
async def create_or_update_policy(
    body: ApprovalPolicyCreate,
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalPolicyResponse:
    """Create or update an approval policy (admin only)."""
    policy = await service.create_policy(
        tool_name=body.tool_name,
        auto_approve_enabled=body.auto_approve_enabled,
        auto_approve_conditions=body.auto_approve_conditions,
        default_expiration_hours=body.default_expiration_hours,
        default_max_uses=body.default_max_uses,
        notify_on_request=body.notify_on_request,
    )

    return ApprovalPolicyResponse(
        id=str(policy.id),
        tool_name=policy.tool_name,
        auto_approve_enabled=policy.auto_approve_enabled,
        auto_approve_conditions=policy.auto_approve_conditions,
        default_expiration_hours=policy.default_expiration_hours,
        default_max_uses=policy.default_max_uses,
        notify_on_request=policy.notify_on_request,
    )


@admin_router.delete("/policies/{tool_name}")
async def delete_policy(
    tool_name: str,
    current_user: User = Depends(current_superuser),
    service: ApprovalService = Depends(get_approval_service),
) -> dict[str, str]:
    """Delete an approval policy (admin only)."""
    deleted = await service.delete_policy(tool_name)
    if not deleted:
        raise HTTPException(404, "Policy not found")
    return {"status": "deleted"}


@admin_router.get("/stats", response_model=ApprovalStats)
async def get_approval_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> ApprovalStats:
    """Get approval statistics (admin only)."""
    from datetime import timedelta

    from sqlalchemy import select

    from airbeeps.agents.models import ToolApprovalRequest

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Count by status
    result = await session.execute(
        select(ToolApprovalRequest).where(ToolApprovalRequest.created_at >= cutoff_date)
    )
    requests = result.scalars().all()

    pending = sum(1 for r in requests if r.status == ApprovalStatusEnum.PENDING)
    approved = sum(1 for r in requests if r.status == ApprovalStatusEnum.APPROVED)
    rejected = sum(1 for r in requests if r.status == ApprovalStatusEnum.REJECTED)
    expired = sum(1 for r in requests if r.status == ApprovalStatusEnum.EXPIRED)

    # Count by tool
    by_tool: dict[str, int] = {}
    for r in requests:
        by_tool[r.tool_name] = by_tool.get(r.tool_name, 0) + 1

    return ApprovalStats(
        pending_count=pending,
        approved_count=approved,
        rejected_count=rejected,
        expired_count=expired,
        by_tool=by_tool,
    )
