"""
Agent Memory API Endpoints.

Provides endpoints for:
- Memory consent management (GDPR)
- Memory export (data portability)
- Memory deletion (right to be forgotten)
- Memory browsing (admin)
- Memory compaction and summarization
- Shared memory pools
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.memory.compaction import MemoryCompactionService
from airbeeps.agents.memory.models import (
    CompactionStrategyEnum,
    MemoryTypeEnum,
    PoolAccessLevelEnum,
    PoolTypeEnum,
)
from airbeeps.agents.memory.pool_service import SharedPoolService
from airbeeps.agents.memory.service import MemoryService
from airbeeps.auth import current_active_user, current_superuser
from airbeeps.database import get_async_session
from airbeeps.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])
admin_router = APIRouter(prefix="/memory", tags=["Memory Admin"])
pool_router = APIRouter(prefix="/memory/pools", tags=["Memory Pools"])


# =============================================================================
# Schemas
# =============================================================================


class ConsentGrantRequest(BaseModel):
    """Request to grant memory consent."""

    allowed_types: list[str] | None = Field(
        default=None,
        description="Memory types to allow (all if None)",
    )
    preferred_ttl_days: int | None = Field(
        default=None,
        description="Preferred retention period in days",
    )


class ConsentRevokeRequest(BaseModel):
    """Request to revoke memory consent."""

    delete_existing: bool = Field(
        default=False,
        description="Whether to delete existing memories",
    )


class ConsentStatusResponse(BaseModel):
    """Response with consent status."""

    has_consent: bool
    allowed_types: list[str]
    consent_date: str | None
    preferred_ttl_days: int | None


class MemoryStatsResponse(BaseModel):
    """Response with memory statistics."""

    total_memories: int
    by_type: dict[str, int]
    average_importance: float
    has_consent: bool
    allowed_types: list[str]


class MemoryResponse(BaseModel):
    """Single memory response."""

    id: str
    content: str
    type: str
    importance: float
    metadata: dict[str, Any]
    created_at: str | None
    expires_at: str | None = None
    access_count: int = 0


class MemoryExportResponse(BaseModel):
    """Memory export response."""

    user_id: str
    exported_at: str
    memory_count: int
    memories: list[dict[str, Any]]


class StoreMemoryRequest(BaseModel):
    """Request to store a memory (admin)."""

    assistant_id: str
    user_id: str
    content: str
    memory_type: str = Field(default="SEMANTIC")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetentionPolicyCreate(BaseModel):
    """Request to create a retention policy."""

    name: str
    description: str | None = None
    ttl_days: int = Field(default=90, ge=0)
    max_memories_per_user: int = Field(default=1000, ge=1)
    auto_prune_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    applies_to_types: list[str] | None = None
    is_default: bool = False


class RetentionPolicyResponse(BaseModel):
    """Retention policy response."""

    id: str
    name: str
    description: str | None
    ttl_days: int
    max_memories_per_user: int
    auto_prune_threshold: float
    applies_to_types: list[str]
    is_default: bool
    is_active: bool


# =============================================================================
# Compaction Schemas
# =============================================================================


class CompactionRequest(BaseModel):
    """Request for memory compaction."""

    strategy: str = Field(
        default="HYBRID",
        description="Compaction strategy: AGE, SIMILARITY, IMPORTANCE, or HYBRID",
    )
    assistant_id: str | None = Field(
        default=None,
        description="Optional assistant filter",
    )
    days_old: int = Field(
        default=30,
        ge=1,
        description="For AGE strategy: minimum age in days",
    )
    similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="For SIMILARITY strategy: minimum similarity",
    )
    importance_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="For IMPORTANCE strategy: maximum importance",
    )
    embedding_model_id: str | None = Field(
        default=None,
        description="Embedding model for generating new embeddings",
    )


class CompactionResponse(BaseModel):
    """Response from memory compaction."""

    strategy: str
    compacted: bool
    memories_before: int = 0
    memories_after: int = 0
    memories_merged: int = 0
    duration_ms: int | None = None
    reason: str | None = None


class CompactionStatsResponse(BaseModel):
    """Statistics about memory compaction."""

    total_compactions: int
    total_memories_merged: int
    by_strategy: dict[str, Any]
    last_compaction: str | None


# =============================================================================
# Shared Pool Schemas
# =============================================================================


class PoolCreateRequest(BaseModel):
    """Request to create a shared memory pool."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    pool_type: str = Field(default="TEAM", description="TEAM, ORGANIZATION, or PUBLIC")
    access_level: str = Field(
        default="READ_ONLY", description="READ_ONLY or READ_WRITE"
    )
    assistant_id: str | None = None
    max_memories: int = Field(default=1000, ge=1, le=10000)
    auto_share_enabled: bool = False


class PoolUpdateRequest(BaseModel):
    """Request to update a shared memory pool."""

    name: str | None = None
    description: str | None = None
    access_level: str | None = None
    max_memories: int | None = Field(default=None, ge=1, le=10000)
    auto_share_enabled: bool | None = None


class PoolResponse(BaseModel):
    """Shared memory pool response."""

    id: str
    name: str
    description: str | None
    pool_type: str
    access_level: str
    owner_id: str
    assistant_id: str | None
    max_memories: int
    auto_share_enabled: bool
    is_active: bool
    created_at: str | None


class PoolStatsResponse(BaseModel):
    """Pool statistics response."""

    pool_id: str
    name: str
    pool_type: str
    access_level: str
    memory_count: int
    member_count: int
    max_memories: int
    capacity_used_percent: float
    auto_share_enabled: bool


class PoolMemberRequest(BaseModel):
    """Request to add a member to a pool."""

    user_id: str
    access_level: str | None = Field(
        default=None,
        description="Override access level for this member",
    )


class PoolMemberResponse(BaseModel):
    """Pool member response."""

    pool_id: str
    user_id: str
    access_level: str | None
    joined_at: str


class ShareMemoryRequest(BaseModel):
    """Request to share a memory to a pool."""

    memory_id: str


class PoolMemoryResponse(BaseModel):
    """Memory from a shared pool."""

    id: str
    content: str
    type: str
    importance: float
    metadata: dict[str, Any]
    created_at: str | None
    pool_id: str


# =============================================================================
# Helper Functions
# =============================================================================


async def get_memory_service(
    session: AsyncSession = Depends(get_async_session),
) -> MemoryService:
    """Get memory service for request."""
    return MemoryService(session=session)


async def get_compaction_service(
    session: AsyncSession = Depends(get_async_session),
) -> MemoryCompactionService:
    """Get compaction service for request."""
    return MemoryCompactionService(session=session)


async def get_pool_service(
    session: AsyncSession = Depends(get_async_session),
) -> SharedPoolService:
    """Get shared pool service for request."""
    return SharedPoolService(session=session)


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def get_user_agent(request: Request) -> str | None:
    """Extract user agent from request."""
    return request.headers.get("User-Agent")


# =============================================================================
# User Endpoints (Self-Service)
# =============================================================================


@router.get("/consent", response_model=ConsentStatusResponse)
async def get_consent_status(
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> ConsentStatusResponse:
    """Get current consent status for the authenticated user."""
    consent = await service._get_user_consent(current_user.id)

    return ConsentStatusResponse(
        has_consent=consent.has_consented if consent else False,
        allowed_types=consent.allowed_memory_types if consent else [],
        consent_date=consent.consent_date.isoformat()
        if consent and consent.consent_date
        else None,
        preferred_ttl_days=consent.preferred_ttl_days if consent else None,
    )


@router.post("/consent", response_model=ConsentStatusResponse)
async def grant_consent(
    body: ConsentGrantRequest,
    request: Request,
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> ConsentStatusResponse:
    """Grant consent for memory storage."""
    allowed_types = None
    if body.allowed_types:
        try:
            allowed_types = [MemoryTypeEnum(t) for t in body.allowed_types]
        except ValueError as e:
            raise HTTPException(400, f"Invalid memory type: {e}")

    consent = await service.grant_consent(
        user_id=current_user.id,
        allowed_types=allowed_types,
        preferred_ttl_days=body.preferred_ttl_days,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return ConsentStatusResponse(
        has_consent=consent.has_consented,
        allowed_types=consent.allowed_memory_types,
        consent_date=consent.consent_date.isoformat() if consent.consent_date else None,
        preferred_ttl_days=consent.preferred_ttl_days,
    )


@router.delete("/consent")
async def revoke_consent(
    body: ConsentRevokeRequest,
    request: Request,
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, str]:
    """Revoke consent for memory storage."""
    await service.revoke_consent(
        user_id=current_user.id,
        delete_existing=body.delete_existing,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return {"status": "consent_revoked"}


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryStatsResponse:
    """Get memory statistics for the authenticated user."""
    stats = await service.get_user_memory_stats(current_user.id)
    return MemoryStatsResponse(**stats)


@router.get("/export", response_model=MemoryExportResponse)
async def export_memories(
    request: Request,
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryExportResponse:
    """
    Export all user memories (GDPR data portability).

    Returns all memories in a portable format.
    """
    export = await service.export_user_memories(
        user_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return MemoryExportResponse(**export)


@router.delete("/all")
async def delete_all_memories(
    request: Request,
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, Any]:
    """
    Delete all user memories (GDPR right to be forgotten).

    This action cannot be undone.
    """
    count = await service.forget_user(
        user_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return {"status": "deleted", "memories_deleted": count}


@router.get("", response_model=list[MemoryResponse])
async def list_my_memories(
    assistant_id: str | None = Query(None, description="Filter by assistant"),
    memory_type: str | None = Query(None, description="Filter by memory type"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> list[MemoryResponse]:
    """List user's own memories."""
    # Build filter
    memory_types = None
    if memory_type:
        try:
            memory_types = [MemoryTypeEnum(memory_type)]
        except ValueError:
            raise HTTPException(400, f"Invalid memory type: {memory_type}")

    # Use recall without query to get recent memories
    memories = await service.recall_memories(
        query="",
        assistant_id=uuid.UUID(assistant_id) if assistant_id else uuid.UUID(int=0),
        user_id=current_user.id,
        top_k=limit,
        memory_types=memory_types,
    )

    return [MemoryResponse(**m) for m in memories]


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    current_user: User = Depends(current_active_user),
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, str]:
    """Delete a specific memory."""
    try:
        memory_uuid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(400, "Invalid memory ID")

    deleted = await service.delete_memory(memory_uuid, current_user.id)
    if not deleted:
        raise HTTPException(404, "Memory not found")

    return {"status": "deleted"}


# =============================================================================
# Admin Endpoints
# =============================================================================


@admin_router.get("/users/{user_id}/stats", response_model=MemoryStatsResponse)
async def get_user_memory_stats_admin(
    user_id: str,
    current_user: User = Depends(current_superuser),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryStatsResponse:
    """Get memory statistics for any user (admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    stats = await service.get_user_memory_stats(user_uuid)
    return MemoryStatsResponse(**stats)


@admin_router.post("/store", response_model=MemoryResponse)
async def store_memory_admin(
    body: StoreMemoryRequest,
    current_user: User = Depends(current_superuser),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    """Store a memory (admin only)."""
    try:
        memory_type = MemoryTypeEnum(body.memory_type)
    except ValueError:
        raise HTTPException(400, f"Invalid memory type: {body.memory_type}")

    try:
        memory = await service.store_memory(
            assistant_id=uuid.UUID(body.assistant_id),
            user_id=uuid.UUID(body.user_id),
            content=body.content,
            memory_type=memory_type,
            importance=body.importance,
            metadata=body.metadata,
            require_consent=False,  # Admin can bypass consent
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Get decrypted memory for response
    mem_dict = await service.get_memory_by_id(memory.id, uuid.UUID(body.user_id))
    return MemoryResponse(**mem_dict)


@admin_router.delete("/users/{user_id}/all")
async def delete_user_memories_admin(
    user_id: str,
    request: Request,
    current_user: User = Depends(current_superuser),
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, Any]:
    """Delete all memories for a user (admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    count = await service.forget_user(
        user_id=user_uuid,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return {"status": "deleted", "memories_deleted": count}


@admin_router.post("/prune/expired")
async def prune_expired_memories(
    current_user: User = Depends(current_superuser),
    service: MemoryService = Depends(get_memory_service),
) -> dict[str, Any]:
    """Prune all expired memories (admin only)."""
    count = await service.prune_expired_memories()
    return {"status": "pruned", "memories_pruned": count}


# =============================================================================
# Retention Policy Endpoints (Admin)
# =============================================================================


@admin_router.get("/policies", response_model=list[RetentionPolicyResponse])
async def list_retention_policies(
    current_user: User = Depends(current_superuser),
    service: MemoryService = Depends(get_memory_service),
) -> list[RetentionPolicyResponse]:
    """List all retention policies."""
    policies = await service.get_retention_policies()
    return [
        RetentionPolicyResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            ttl_days=p.ttl_days,
            max_memories_per_user=p.max_memories_per_user,
            auto_prune_threshold=p.auto_prune_threshold,
            applies_to_types=p.applies_to_types,
            is_default=p.is_default,
            is_active=p.is_active,
        )
        for p in policies
    ]


@admin_router.post("/policies", response_model=RetentionPolicyResponse)
async def create_retention_policy(
    body: RetentionPolicyCreate,
    current_user: User = Depends(current_superuser),
    service: MemoryService = Depends(get_memory_service),
) -> RetentionPolicyResponse:
    """Create a new retention policy."""
    policy = await service.create_retention_policy(
        name=body.name,
        description=body.description,
        ttl_days=body.ttl_days,
        max_memories_per_user=body.max_memories_per_user,
        auto_prune_threshold=body.auto_prune_threshold,
        applies_to_types=body.applies_to_types,
        is_default=body.is_default,
    )

    return RetentionPolicyResponse(
        id=str(policy.id),
        name=policy.name,
        description=policy.description,
        ttl_days=policy.ttl_days,
        max_memories_per_user=policy.max_memories_per_user,
        auto_prune_threshold=policy.auto_prune_threshold,
        applies_to_types=policy.applies_to_types,
        is_default=policy.is_default,
        is_active=policy.is_active,
    )


# =============================================================================
# Compaction Endpoints
# =============================================================================


@router.post("/compact", response_model=CompactionResponse)
async def compact_memories(
    body: CompactionRequest,
    current_user: User = Depends(current_active_user),
    service: MemoryCompactionService = Depends(get_compaction_service),
) -> CompactionResponse:
    """
    Compact user's memories using specified strategy.

    This reduces memory storage by merging similar or old memories.
    """
    try:
        strategy = CompactionStrategyEnum(body.strategy)
    except ValueError:
        raise HTTPException(400, f"Invalid strategy: {body.strategy}")

    assistant_id = uuid.UUID(body.assistant_id) if body.assistant_id else None

    if strategy == CompactionStrategyEnum.AGE:
        result = await service.compact_by_age(
            user_id=current_user.id,
            assistant_id=assistant_id,
            days_old=body.days_old,
            embedding_model_id=body.embedding_model_id,
        )
    elif strategy == CompactionStrategyEnum.SIMILARITY:
        result = await service.compact_by_similarity(
            user_id=current_user.id,
            assistant_id=assistant_id,
            similarity_threshold=body.similarity_threshold,
            embedding_model_id=body.embedding_model_id,
        )
    elif strategy == CompactionStrategyEnum.IMPORTANCE:
        result = await service.compact_by_importance(
            user_id=current_user.id,
            assistant_id=assistant_id,
            importance_threshold=body.importance_threshold,
            embedding_model_id=body.embedding_model_id,
        )
    else:  # HYBRID
        result = await service.run_hybrid_compaction(
            user_id=current_user.id,
            assistant_id=assistant_id,
            embedding_model_id=body.embedding_model_id,
        )

    return CompactionResponse(**result)


@router.get("/compact/stats", response_model=CompactionStatsResponse)
async def get_compaction_stats(
    assistant_id: str | None = Query(None),
    current_user: User = Depends(current_active_user),
    service: MemoryCompactionService = Depends(get_compaction_service),
) -> CompactionStatsResponse:
    """Get memory compaction statistics for the user."""
    aid = uuid.UUID(assistant_id) if assistant_id else None
    stats = await service.get_compaction_stats(current_user.id, aid)
    return CompactionStatsResponse(**stats)


@admin_router.post("/compact/user/{user_id}", response_model=CompactionResponse)
async def compact_user_memories_admin(
    user_id: str,
    body: CompactionRequest,
    current_user: User = Depends(current_superuser),
    service: MemoryCompactionService = Depends(get_compaction_service),
) -> CompactionResponse:
    """Compact a user's memories (admin only)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    try:
        strategy = CompactionStrategyEnum(body.strategy)
    except ValueError:
        raise HTTPException(400, f"Invalid strategy: {body.strategy}")

    assistant_id = uuid.UUID(body.assistant_id) if body.assistant_id else None

    if strategy == CompactionStrategyEnum.HYBRID:
        result = await service.run_hybrid_compaction(
            user_id=user_uuid,
            assistant_id=assistant_id,
            embedding_model_id=body.embedding_model_id,
        )
    else:
        result = await service.compact_by_age(
            user_id=user_uuid,
            assistant_id=assistant_id,
            days_old=body.days_old,
            embedding_model_id=body.embedding_model_id,
        )

    return CompactionResponse(**result)


# =============================================================================
# Shared Pool Endpoints
# =============================================================================


@pool_router.get("", response_model=list[PoolResponse])
async def list_pools(
    pool_type: str | None = Query(None, description="Filter by pool type"),
    include_public: bool = Query(True, description="Include public pools"),
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> list[PoolResponse]:
    """List shared memory pools accessible to the user."""
    ptype = None
    if pool_type:
        try:
            ptype = PoolTypeEnum(pool_type)
        except ValueError:
            raise HTTPException(400, f"Invalid pool type: {pool_type}")

    pools = await service.list_pools(
        user_id=current_user.id,
        pool_type=ptype,
        include_public=include_public,
    )

    return [
        PoolResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            pool_type=p.pool_type.value,
            access_level=p.access_level.value,
            owner_id=str(p.owner_id),
            assistant_id=str(p.assistant_id) if p.assistant_id else None,
            max_memories=p.max_memories,
            auto_share_enabled=p.auto_share_enabled,
            is_active=p.is_active,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in pools
    ]


@pool_router.post("", response_model=PoolResponse)
async def create_pool(
    body: PoolCreateRequest,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> PoolResponse:
    """Create a new shared memory pool."""
    try:
        pool_type = PoolTypeEnum(body.pool_type)
    except ValueError:
        raise HTTPException(400, f"Invalid pool type: {body.pool_type}")

    try:
        access_level = PoolAccessLevelEnum(body.access_level)
    except ValueError:
        raise HTTPException(400, f"Invalid access level: {body.access_level}")

    assistant_id = uuid.UUID(body.assistant_id) if body.assistant_id else None

    pool = await service.create_pool(
        name=body.name,
        owner_id=current_user.id,
        pool_type=pool_type,
        access_level=access_level,
        description=body.description,
        assistant_id=assistant_id,
        max_memories=body.max_memories,
        auto_share_enabled=body.auto_share_enabled,
    )

    return PoolResponse(
        id=str(pool.id),
        name=pool.name,
        description=pool.description,
        pool_type=pool.pool_type.value,
        access_level=pool.access_level.value,
        owner_id=str(pool.owner_id),
        assistant_id=str(pool.assistant_id) if pool.assistant_id else None,
        max_memories=pool.max_memories,
        auto_share_enabled=pool.auto_share_enabled,
        is_active=pool.is_active,
        created_at=pool.created_at.isoformat() if pool.created_at else None,
    )


@pool_router.get("/{pool_id}", response_model=PoolResponse)
async def get_pool(
    pool_id: str,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> PoolResponse:
    """Get a shared memory pool by ID."""
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(400, "Invalid pool ID")

    pool = await service.get_pool(pool_uuid, current_user.id)
    if not pool:
        raise HTTPException(404, "Pool not found")

    return PoolResponse(
        id=str(pool.id),
        name=pool.name,
        description=pool.description,
        pool_type=pool.pool_type.value,
        access_level=pool.access_level.value,
        owner_id=str(pool.owner_id),
        assistant_id=str(pool.assistant_id) if pool.assistant_id else None,
        max_memories=pool.max_memories,
        auto_share_enabled=pool.auto_share_enabled,
        is_active=pool.is_active,
        created_at=pool.created_at.isoformat() if pool.created_at else None,
    )


@pool_router.patch("/{pool_id}", response_model=PoolResponse)
async def update_pool(
    pool_id: str,
    body: PoolUpdateRequest,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> PoolResponse:
    """Update a shared memory pool (owner only)."""
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(400, "Invalid pool ID")

    access_level = None
    if body.access_level:
        try:
            access_level = PoolAccessLevelEnum(body.access_level)
        except ValueError:
            raise HTTPException(400, f"Invalid access level: {body.access_level}")

    pool = await service.update_pool(
        pool_id=pool_uuid,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        access_level=access_level,
        max_memories=body.max_memories,
        auto_share_enabled=body.auto_share_enabled,
    )

    if not pool:
        raise HTTPException(404, "Pool not found or not authorized")

    return PoolResponse(
        id=str(pool.id),
        name=pool.name,
        description=pool.description,
        pool_type=pool.pool_type.value,
        access_level=pool.access_level.value,
        owner_id=str(pool.owner_id),
        assistant_id=str(pool.assistant_id) if pool.assistant_id else None,
        max_memories=pool.max_memories,
        auto_share_enabled=pool.auto_share_enabled,
        is_active=pool.is_active,
        created_at=pool.created_at.isoformat() if pool.created_at else None,
    )


@pool_router.delete("/{pool_id}")
async def delete_pool(
    pool_id: str,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> dict[str, str]:
    """Delete a shared memory pool (owner only)."""
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(400, "Invalid pool ID")

    deleted = await service.delete_pool(pool_uuid, current_user.id)
    if not deleted:
        raise HTTPException(404, "Pool not found or not authorized")

    return {"status": "deleted"}


@pool_router.get("/{pool_id}/stats", response_model=PoolStatsResponse)
async def get_pool_stats(
    pool_id: str,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> PoolStatsResponse:
    """Get statistics for a shared memory pool."""
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(400, "Invalid pool ID")

    stats = await service.get_pool_stats(pool_uuid, current_user.id)
    if not stats:
        raise HTTPException(404, "Pool not found or not authorized")

    return PoolStatsResponse(**stats)


# Pool Members
@pool_router.get("/{pool_id}/members", response_model=list[PoolMemberResponse])
async def list_pool_members(
    pool_id: str,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> list[PoolMemberResponse]:
    """List members of a shared memory pool."""
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(400, "Invalid pool ID")

    # Check access
    pool = await service.get_pool(pool_uuid, current_user.id)
    if not pool:
        raise HTTPException(404, "Pool not found or not authorized")

    members = await service.list_members(pool_uuid)
    return [
        PoolMemberResponse(
            pool_id=str(m.pool_id),
            user_id=str(m.user_id),
            access_level=m.access_level.value if m.access_level else None,
            joined_at=m.joined_at.isoformat() if m.joined_at else None,
        )
        for m in members
    ]


@pool_router.post("/{pool_id}/members", response_model=PoolMemberResponse)
async def add_pool_member(
    pool_id: str,
    body: PoolMemberRequest,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> PoolMemberResponse:
    """Add a member to a shared memory pool (owner only)."""
    try:
        pool_uuid = uuid.UUID(pool_id)
        user_uuid = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID")

    access_level = None
    if body.access_level:
        try:
            access_level = PoolAccessLevelEnum(body.access_level)
        except ValueError:
            raise HTTPException(400, f"Invalid access level: {body.access_level}")

    member = await service.add_member(
        pool_id=pool_uuid,
        user_id=user_uuid,
        added_by_id=current_user.id,
        access_level=access_level,
    )

    if not member:
        raise HTTPException(404, "Pool not found or not authorized")

    return PoolMemberResponse(
        pool_id=str(member.pool_id),
        user_id=str(member.user_id),
        access_level=member.access_level.value if member.access_level else None,
        joined_at=member.joined_at.isoformat() if member.joined_at else None,
    )


@pool_router.delete("/{pool_id}/members/{user_id}")
async def remove_pool_member(
    pool_id: str,
    user_id: str,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> dict[str, str]:
    """Remove a member from a shared memory pool."""
    try:
        pool_uuid = uuid.UUID(pool_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID")

    removed = await service.remove_member(
        pool_id=pool_uuid,
        user_id=user_uuid,
        removed_by_id=current_user.id,
    )

    if not removed:
        raise HTTPException(404, "Member not found or not authorized")

    return {"status": "removed"}


# Pool Memories
@pool_router.get("/{pool_id}/memories", response_model=list[PoolMemoryResponse])
async def list_pool_memories(
    pool_id: str,
    query: str = Query("", description="Search query"),
    top_k: int = Query(10, ge=1, le=100),
    embedding_model_id: str | None = Query(None),
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> list[PoolMemoryResponse]:
    """Retrieve memories from a shared pool."""
    try:
        pool_uuid = uuid.UUID(pool_id)
    except ValueError:
        raise HTTPException(400, "Invalid pool ID")

    memories = await service.recall_pool_memories(
        pool_id=pool_uuid,
        user_id=current_user.id,
        query=query,
        top_k=top_k,
        embedding_model_id=embedding_model_id,
    )

    return [PoolMemoryResponse(**m) for m in memories]


@pool_router.post("/{pool_id}/memories")
async def share_memory_to_pool(
    pool_id: str,
    body: ShareMemoryRequest,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> dict[str, str]:
    """Share a memory to a pool."""
    try:
        pool_uuid = uuid.UUID(pool_id)
        memory_uuid = uuid.UUID(body.memory_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID")

    result = await service.add_memory_to_pool(
        pool_id=pool_uuid,
        memory_id=memory_uuid,
        user_id=current_user.id,
    )

    if not result:
        raise HTTPException(
            400, "Could not share memory. Check access permissions and pool capacity."
        )

    return {"status": "shared"}


@pool_router.delete("/{pool_id}/memories/{memory_id}")
async def remove_memory_from_pool(
    pool_id: str,
    memory_id: str,
    current_user: User = Depends(current_active_user),
    service: SharedPoolService = Depends(get_pool_service),
) -> dict[str, str]:
    """Remove a memory from a pool."""
    try:
        pool_uuid = uuid.UUID(pool_id)
        memory_uuid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(400, "Invalid ID")

    removed = await service.remove_memory_from_pool(
        pool_id=pool_uuid,
        memory_id=memory_uuid,
        user_id=current_user.id,
    )

    if not removed:
        raise HTTPException(404, "Memory not found in pool or not authorized")

    return {"status": "removed"}
