"""
Multi-Agent System API Endpoints.

Provides endpoints for:
- Listing specialist types and configurations
- Executing multi-agent tasks
- Viewing collaboration logs
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.database import get_async_session
from airbeeps.auth import current_active_user, current_superuser
from airbeeps.users.models import User
from airbeeps.assistants.models import Assistant
from airbeeps.agents.models import (
    AgentCollaborationLog,
    CollaborationStatusEnum,
    CustomSpecialistType,
    SpecialistRoutingRule,
    SpecialistPerformanceMetric,
    RoutingRuleTypeEnum,
)

from .types import (
    SpecialistType,
    SpecialistConfig,
    SPECIALIST_CONFIGS,
    get_specialist_config,
)
from .router import AgentRouter, RoutingDecision
from .orchestrator import (
    MultiAgentOrchestrator,
    AgentCollaborationConfig,
    CollaborationResult,
)

logger = logging.getLogger(__name__)


# === Pydantic Schemas ===


class SpecialistTypeSchema(BaseModel):
    """Schema for specialist type information"""

    type: str
    name: str
    tools: list[str]
    max_iterations: int
    cost_limit_usd: float
    can_handoff_to: list[str]
    priority_keywords: list[str]

    class Config:
        from_attributes = True


class RoutingRequestSchema(BaseModel):
    """Request to classify and route user input"""

    user_input: str = Field(..., min_length=1, max_length=5000)
    available_specialists: list[str] | None = None


class RoutingResponseSchema(BaseModel):
    """Response from routing classification"""

    specialist_type: str
    confidence: float
    reasoning: str
    method: str


class CollaborationRequestSchema(BaseModel):
    """Request to execute multi-agent collaboration"""

    user_input: str = Field(..., min_length=1, max_length=10000)
    assistant_ids: dict[str, str] = Field(
        ...,
        description="Mapping of specialist type to assistant ID",
        examples=[{"GENERAL": "uuid", "RESEARCH": "uuid"}],
    )
    conversation_id: str | None = None
    max_handoffs: int = Field(default=3, ge=1, le=10)
    cost_limit_usd: float = Field(default=1.00, ge=0.01, le=10.0)


class CollaborationStepSchema(BaseModel):
    """Schema for a single collaboration step"""

    step_number: int
    specialist_type: str
    specialist_id: str | None
    input_context: str
    output: str
    iterations: int
    cost_usd: float
    duration_ms: float
    handoff_requested: str | None


class CollaborationResponseSchema(BaseModel):
    """Response from multi-agent collaboration"""

    success: bool
    final_output: str
    steps: list[CollaborationStepSchema]
    total_iterations: int
    total_cost_usd: float
    total_duration_ms: float
    agent_chain: list[str]
    error: str | None = None
    error_type: str | None = None


class CollaborationLogSchema(BaseModel):
    """Schema for collaboration log entry"""

    id: str
    user_id: str
    conversation_id: str | None
    initial_assistant_id: str | None
    user_input: str
    final_output: str | None
    status: str
    agent_chain: list[str]
    total_iterations: int
    total_cost_usd: float
    total_duration_ms: float
    handoff_count: int
    error_message: str | None
    error_type: str | None
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class CollaborationStatsSchema(BaseModel):
    """Statistics about collaboration usage"""

    total_collaborations: int
    successful_collaborations: int
    failed_collaborations: int
    total_handoffs: int
    total_cost_usd: float
    average_duration_ms: float
    most_used_specialists: dict[str, int]
    common_handoff_patterns: list[dict[str, Any]]


# === Custom Specialist Schemas ===


class CustomSpecialistCreateSchema(BaseModel):
    """Schema for creating a custom specialist type"""

    name: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z_]+$")
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    tools: list[str] = Field(default_factory=list)
    system_prompt_suffix: str = ""
    max_iterations: int = Field(default=5, ge=1, le=20)
    cost_limit_usd: float = Field(default=0.25, ge=0.01, le=10.0)
    can_handoff_to: list[str] = Field(default_factory=list)
    priority_keywords: list[str] = Field(default_factory=list)


class CustomSpecialistUpdateSchema(BaseModel):
    """Schema for updating a custom specialist type"""

    display_name: str | None = None
    description: str | None = None
    tools: list[str] | None = None
    system_prompt_suffix: str | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=20)
    cost_limit_usd: float | None = Field(default=None, ge=0.01, le=10.0)
    can_handoff_to: list[str] | None = None
    priority_keywords: list[str] | None = None
    is_enabled: bool | None = None


class CustomSpecialistSchema(BaseModel):
    """Schema for custom specialist type response"""

    id: str
    name: str
    display_name: str
    description: str | None
    tools: list[str]
    system_prompt_suffix: str
    max_iterations: int
    cost_limit_usd: float
    can_handoff_to: list[str]
    priority_keywords: list[str]
    is_enabled: bool
    created_at: datetime | None


# === Routing Rule Schemas ===


class RoutingRuleCreateSchema(BaseModel):
    """Schema for creating a routing rule"""

    specialist_name: str = Field(..., min_length=2, max_length=50)
    rule_type: str = Field(..., description="KEYWORD, REGEX, or LLM")
    rule_value: str = Field(..., min_length=1)
    priority: int = Field(default=0, ge=-100, le=100)
    description: str | None = None
    is_enabled: bool = True


class RoutingRuleUpdateSchema(BaseModel):
    """Schema for updating a routing rule"""

    rule_type: str | None = None
    rule_value: str | None = None
    priority: int | None = Field(default=None, ge=-100, le=100)
    description: str | None = None
    is_enabled: bool | None = None


class RoutingRuleSchema(BaseModel):
    """Schema for routing rule response"""

    id: str
    specialist_name: str
    custom_specialist_id: str | None
    rule_type: str
    rule_value: str
    priority: int
    description: str | None
    is_enabled: bool
    created_at: datetime | None


class RoutingRuleTestSchema(BaseModel):
    """Schema for testing a routing rule"""

    user_input: str = Field(..., min_length=1, max_length=5000)


class RoutingRuleTestResultSchema(BaseModel):
    """Result of testing routing rules"""

    matched: bool
    matched_rule_id: str | None
    specialist_name: str | None
    rule_type: str | None
    confidence: float


# === Performance Analytics Schemas ===


class SpecialistAnalyticsSchema(BaseModel):
    """Analytics for a specialist type"""

    specialist_name: str
    total_invocations: int
    success_rate: float
    avg_cost_usd: float
    avg_duration_ms: float
    avg_iterations: float
    total_handoffs_from: int
    total_handoffs_to: int
    top_tools: dict[str, int]


class RoutingAnalyticsSchema(BaseModel):
    """Analytics for routing performance"""

    total_classifications: int
    keyword_match_rate: float
    llm_fallback_rate: float
    avg_confidence: float
    top_specialists: list[dict[str, Any]]


# === Routers ===

# Public router (authenticated users)
router = APIRouter(prefix="/multiagent", tags=["Multi-Agent"])

# Admin router
admin_router = APIRouter(prefix="/multiagent", tags=["Multi-Agent Admin"])


# === Public Endpoints ===


@router.get("/specialists", response_model=list[SpecialistTypeSchema])
async def list_specialist_types():
    """
    List all available specialist types and their configurations.
    """
    specialists = []
    for spec_type, config in SPECIALIST_CONFIGS.items():
        specialists.append(
            SpecialistTypeSchema(
                type=spec_type.value,
                name=config.name,
                tools=config.tools,
                max_iterations=config.max_iterations,
                cost_limit_usd=config.cost_limit_usd,
                can_handoff_to=[t.value for t in config.can_handoff_to],
                priority_keywords=config.priority_keywords[
                    :10
                ],  # Limit for response size
            )
        )
    return specialists


@router.get("/specialists/{specialist_type}", response_model=SpecialistTypeSchema)
async def get_specialist_type(specialist_type: str):
    """
    Get configuration for a specific specialist type.
    """
    try:
        spec_type = SpecialistType(specialist_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown specialist type: {specialist_type}",
        )

    config = get_specialist_config(spec_type)

    return SpecialistTypeSchema(
        type=spec_type.value,
        name=config.name,
        tools=config.tools,
        max_iterations=config.max_iterations,
        cost_limit_usd=config.cost_limit_usd,
        can_handoff_to=[t.value for t in config.can_handoff_to],
        priority_keywords=config.priority_keywords,
    )


@router.post("/classify", response_model=RoutingResponseSchema)
async def classify_request(
    request: RoutingRequestSchema,
    current_user: User = Depends(current_active_user),
):
    """
    Classify a user request to determine the best specialist.

    Uses keyword matching first, then LLM if available.
    """
    # Parse available specialists
    available = None
    if request.available_specialists:
        try:
            available = [
                SpecialistType(s.upper()) for s in request.available_specialists
            ]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid specialist type: {e}")

    # Create router (without LLM for now - quick classification)
    router = AgentRouter(llm=None, use_llm_classification=False)

    # Route the request
    import asyncio

    result = await router.route(request.user_input, available)

    return RoutingResponseSchema(
        specialist_type=result.specialist_type.value,
        confidence=result.confidence,
        reasoning=result.reasoning,
        method=result.method,
    )


# === Admin Endpoints ===


@admin_router.get("/logs", response_model=list[CollaborationLogSchema])
async def list_collaboration_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    List collaboration logs (admin only).
    """
    query = select(AgentCollaborationLog).order_by(
        desc(AgentCollaborationLog.created_at)
    )

    if user_id:
        query = query.where(AgentCollaborationLog.user_id == UUID(user_id))

    if status:
        try:
            status_enum = CollaborationStatusEnum(status.upper())
            query = query.where(AgentCollaborationLog.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    query = query.offset(skip).limit(limit)

    result = await session.execute(query)
    logs = result.scalars().all()

    return [
        CollaborationLogSchema(
            id=str(log.id),
            user_id=str(log.user_id),
            conversation_id=str(log.conversation_id) if log.conversation_id else None,
            initial_assistant_id=str(log.initial_assistant_id)
            if log.initial_assistant_id
            else None,
            user_input=log.user_input[:500],  # Truncate for list view
            final_output=log.final_output[:500] if log.final_output else None,
            status=log.status.value,
            agent_chain=log.agent_chain,
            total_iterations=log.total_iterations,
            total_cost_usd=log.total_cost_usd,
            total_duration_ms=log.total_duration_ms,
            handoff_count=log.handoff_count,
            error_message=log.error_message,
            error_type=log.error_type,
            created_at=log.created_at,
            completed_at=log.completed_at,
        )
        for log in logs
    ]


@admin_router.get("/logs/{log_id}")
async def get_collaboration_log(
    log_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Get detailed collaboration log by ID (admin only).
    """
    result = await session.execute(
        select(AgentCollaborationLog).where(AgentCollaborationLog.id == UUID(log_id))
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Collaboration log not found")

    return {
        "id": str(log.id),
        "user_id": str(log.user_id),
        "conversation_id": str(log.conversation_id) if log.conversation_id else None,
        "initial_assistant_id": str(log.initial_assistant_id)
        if log.initial_assistant_id
        else None,
        "user_input": log.user_input,
        "final_output": log.final_output,
        "status": log.status.value,
        "agent_chain": log.agent_chain,
        "steps": log.steps,
        "total_iterations": log.total_iterations,
        "total_cost_usd": log.total_cost_usd,
        "total_duration_ms": log.total_duration_ms,
        "handoff_count": log.handoff_count,
        "error_message": log.error_message,
        "error_type": log.error_type,
        "extra_data": log.extra_data,
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
    }


@admin_router.get("/stats", response_model=CollaborationStatsSchema)
async def get_collaboration_stats(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Get collaboration statistics (admin only).
    """
    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get all logs in the period
    result = await session.execute(
        select(AgentCollaborationLog).where(
            AgentCollaborationLog.created_at >= cutoff_date
        )
    )
    logs = result.scalars().all()

    total = len(logs)
    successful = sum(
        1 for log in logs if log.status == CollaborationStatusEnum.COMPLETED
    )
    failed = total - successful
    total_handoffs = sum(log.handoff_count for log in logs)
    total_cost = sum(log.total_cost_usd for log in logs)
    avg_duration = (
        sum(log.total_duration_ms for log in logs) / total if total > 0 else 0
    )

    # Count specialist usage
    specialist_counts: dict[str, int] = {}
    for log in logs:
        for specialist in log.agent_chain:
            specialist_counts[specialist] = specialist_counts.get(specialist, 0) + 1

    # Find common handoff patterns
    handoff_patterns: dict[str, int] = {}
    for log in logs:
        if len(log.agent_chain) > 1:
            pattern = " -> ".join(log.agent_chain)
            handoff_patterns[pattern] = handoff_patterns.get(pattern, 0) + 1

    # Sort and limit patterns
    sorted_patterns = sorted(
        handoff_patterns.items(), key=lambda x: x[1], reverse=True
    )[:10]

    return CollaborationStatsSchema(
        total_collaborations=total,
        successful_collaborations=successful,
        failed_collaborations=failed,
        total_handoffs=total_handoffs,
        total_cost_usd=total_cost,
        average_duration_ms=avg_duration,
        most_used_specialists=specialist_counts,
        common_handoff_patterns=[
            {"pattern": p, "count": c} for p, c in sorted_patterns
        ],
    )


@admin_router.delete("/logs/{log_id}")
async def delete_collaboration_log(
    log_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Delete a collaboration log (admin only).
    """
    result = await session.execute(
        select(AgentCollaborationLog).where(AgentCollaborationLog.id == UUID(log_id))
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Collaboration log not found")

    await session.delete(log)
    await session.commit()

    return {"status": "deleted", "id": log_id}


@admin_router.delete("/logs/old")
async def delete_old_collaboration_logs(
    days: int = Query(90, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Delete collaboration logs older than specified days (admin only).
    """
    from datetime import timedelta
    from sqlalchemy import delete

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        delete(AgentCollaborationLog).where(
            AgentCollaborationLog.created_at < cutoff_date
        )
    )

    await session.commit()

    return {
        "status": "deleted",
        "deleted_count": result.rowcount,
        "cutoff_date": cutoff_date.isoformat(),
    }


# =============================================================================
# Custom Specialist Type Endpoints (Admin)
# =============================================================================


@admin_router.get("/specialist-types", response_model=list[CustomSpecialistSchema])
async def list_custom_specialists(
    include_disabled: bool = Query(False),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """List all custom specialist types."""
    query = select(CustomSpecialistType).order_by(CustomSpecialistType.name)

    if not include_disabled:
        query = query.where(CustomSpecialistType.is_enabled.is_(True))

    result = await session.execute(query)
    specialists = result.scalars().all()

    return [
        CustomSpecialistSchema(
            id=str(s.id),
            name=s.name,
            display_name=s.display_name,
            description=s.description,
            tools=s.tools,
            system_prompt_suffix=s.system_prompt_suffix,
            max_iterations=s.max_iterations,
            cost_limit_usd=s.cost_limit_usd,
            can_handoff_to=s.can_handoff_to,
            priority_keywords=s.priority_keywords,
            is_enabled=s.is_enabled,
            created_at=s.created_at,
        )
        for s in specialists
    ]


@admin_router.post("/specialist-types", response_model=CustomSpecialistSchema)
async def create_custom_specialist(
    body: CustomSpecialistCreateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Create a new custom specialist type."""
    # Check for duplicate name
    existing = await session.execute(
        select(CustomSpecialistType).where(CustomSpecialistType.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Specialist type '{body.name}' already exists")

    # Check if name conflicts with built-in types
    try:
        SpecialistType(body.name)
        raise HTTPException(400, f"'{body.name}' is a built-in specialist type")
    except ValueError:
        pass  # Not a built-in type, good to create

    specialist = CustomSpecialistType(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        tools=body.tools,
        system_prompt_suffix=body.system_prompt_suffix,
        max_iterations=body.max_iterations,
        cost_limit_usd=body.cost_limit_usd,
        can_handoff_to=body.can_handoff_to,
        priority_keywords=body.priority_keywords,
        created_by_id=current_user.id,
    )

    session.add(specialist)
    await session.commit()
    await session.refresh(specialist)

    return CustomSpecialistSchema(
        id=str(specialist.id),
        name=specialist.name,
        display_name=specialist.display_name,
        description=specialist.description,
        tools=specialist.tools,
        system_prompt_suffix=specialist.system_prompt_suffix,
        max_iterations=specialist.max_iterations,
        cost_limit_usd=specialist.cost_limit_usd,
        can_handoff_to=specialist.can_handoff_to,
        priority_keywords=specialist.priority_keywords,
        is_enabled=specialist.is_enabled,
        created_at=specialist.created_at,
    )


@admin_router.get(
    "/specialist-types/{specialist_id}", response_model=CustomSpecialistSchema
)
async def get_custom_specialist(
    specialist_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get a custom specialist type by ID."""
    result = await session.execute(
        select(CustomSpecialistType).where(
            CustomSpecialistType.id == UUID(specialist_id)
        )
    )
    specialist = result.scalar_one_or_none()

    if not specialist:
        raise HTTPException(404, "Custom specialist type not found")

    return CustomSpecialistSchema(
        id=str(specialist.id),
        name=specialist.name,
        display_name=specialist.display_name,
        description=specialist.description,
        tools=specialist.tools,
        system_prompt_suffix=specialist.system_prompt_suffix,
        max_iterations=specialist.max_iterations,
        cost_limit_usd=specialist.cost_limit_usd,
        can_handoff_to=specialist.can_handoff_to,
        priority_keywords=specialist.priority_keywords,
        is_enabled=specialist.is_enabled,
        created_at=specialist.created_at,
    )


@admin_router.patch(
    "/specialist-types/{specialist_id}", response_model=CustomSpecialistSchema
)
async def update_custom_specialist(
    specialist_id: str,
    body: CustomSpecialistUpdateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Update a custom specialist type."""
    result = await session.execute(
        select(CustomSpecialistType).where(
            CustomSpecialistType.id == UUID(specialist_id)
        )
    )
    specialist = result.scalar_one_or_none()

    if not specialist:
        raise HTTPException(404, "Custom specialist type not found")

    if body.display_name is not None:
        specialist.display_name = body.display_name
    if body.description is not None:
        specialist.description = body.description
    if body.tools is not None:
        specialist.tools = body.tools
    if body.system_prompt_suffix is not None:
        specialist.system_prompt_suffix = body.system_prompt_suffix
    if body.max_iterations is not None:
        specialist.max_iterations = body.max_iterations
    if body.cost_limit_usd is not None:
        specialist.cost_limit_usd = body.cost_limit_usd
    if body.can_handoff_to is not None:
        specialist.can_handoff_to = body.can_handoff_to
    if body.priority_keywords is not None:
        specialist.priority_keywords = body.priority_keywords
    if body.is_enabled is not None:
        specialist.is_enabled = body.is_enabled

    await session.commit()
    await session.refresh(specialist)

    return CustomSpecialistSchema(
        id=str(specialist.id),
        name=specialist.name,
        display_name=specialist.display_name,
        description=specialist.description,
        tools=specialist.tools,
        system_prompt_suffix=specialist.system_prompt_suffix,
        max_iterations=specialist.max_iterations,
        cost_limit_usd=specialist.cost_limit_usd,
        can_handoff_to=specialist.can_handoff_to,
        priority_keywords=specialist.priority_keywords,
        is_enabled=specialist.is_enabled,
        created_at=specialist.created_at,
    )


@admin_router.delete("/specialist-types/{specialist_id}")
async def delete_custom_specialist(
    specialist_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Delete a custom specialist type."""
    result = await session.execute(
        select(CustomSpecialistType).where(
            CustomSpecialistType.id == UUID(specialist_id)
        )
    )
    specialist = result.scalar_one_or_none()

    if not specialist:
        raise HTTPException(404, "Custom specialist type not found")

    await session.delete(specialist)
    await session.commit()

    return {"status": "deleted", "id": specialist_id}


# =============================================================================
# Routing Rule Endpoints (Admin)
# =============================================================================


@admin_router.get("/routing-rules", response_model=list[RoutingRuleSchema])
async def list_routing_rules(
    specialist_name: str | None = Query(None),
    include_disabled: bool = Query(False),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """List all routing rules."""
    query = select(SpecialistRoutingRule).order_by(
        desc(SpecialistRoutingRule.priority),
        SpecialistRoutingRule.specialist_name,
    )

    if specialist_name:
        query = query.where(SpecialistRoutingRule.specialist_name == specialist_name)

    if not include_disabled:
        query = query.where(SpecialistRoutingRule.is_enabled.is_(True))

    result = await session.execute(query)
    rules = result.scalars().all()

    return [
        RoutingRuleSchema(
            id=str(r.id),
            specialist_name=r.specialist_name,
            custom_specialist_id=str(r.custom_specialist_id)
            if r.custom_specialist_id
            else None,
            rule_type=r.rule_type.value,
            rule_value=r.rule_value,
            priority=r.priority,
            description=r.description,
            is_enabled=r.is_enabled,
            created_at=r.created_at,
        )
        for r in rules
    ]


@admin_router.post("/routing-rules", response_model=RoutingRuleSchema)
async def create_routing_rule(
    body: RoutingRuleCreateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Create a new routing rule."""
    # Validate rule type
    try:
        rule_type = RoutingRuleTypeEnum(body.rule_type.upper())
    except ValueError:
        raise HTTPException(400, f"Invalid rule type: {body.rule_type}")

    # Check if specialist exists (built-in or custom)
    custom_specialist_id = None
    try:
        SpecialistType(body.specialist_name.upper())
    except ValueError:
        # Not a built-in type, check custom
        result = await session.execute(
            select(CustomSpecialistType).where(
                CustomSpecialistType.name == body.specialist_name.upper()
            )
        )
        custom = result.scalar_one_or_none()
        if not custom:
            raise HTTPException(
                404, f"Specialist type '{body.specialist_name}' not found"
            )
        custom_specialist_id = custom.id

    rule = SpecialistRoutingRule(
        specialist_name=body.specialist_name.upper(),
        custom_specialist_id=custom_specialist_id,
        rule_type=rule_type,
        rule_value=body.rule_value,
        priority=body.priority,
        description=body.description,
        is_enabled=body.is_enabled,
    )

    session.add(rule)
    await session.commit()
    await session.refresh(rule)

    return RoutingRuleSchema(
        id=str(rule.id),
        specialist_name=rule.specialist_name,
        custom_specialist_id=str(rule.custom_specialist_id)
        if rule.custom_specialist_id
        else None,
        rule_type=rule.rule_type.value,
        rule_value=rule.rule_value,
        priority=rule.priority,
        description=rule.description,
        is_enabled=rule.is_enabled,
        created_at=rule.created_at,
    )


@admin_router.patch("/routing-rules/{rule_id}", response_model=RoutingRuleSchema)
async def update_routing_rule(
    rule_id: str,
    body: RoutingRuleUpdateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Update a routing rule."""
    result = await session.execute(
        select(SpecialistRoutingRule).where(SpecialistRoutingRule.id == UUID(rule_id))
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(404, "Routing rule not found")

    if body.rule_type is not None:
        try:
            rule.rule_type = RoutingRuleTypeEnum(body.rule_type.upper())
        except ValueError:
            raise HTTPException(400, f"Invalid rule type: {body.rule_type}")

    if body.rule_value is not None:
        rule.rule_value = body.rule_value
    if body.priority is not None:
        rule.priority = body.priority
    if body.description is not None:
        rule.description = body.description
    if body.is_enabled is not None:
        rule.is_enabled = body.is_enabled

    await session.commit()
    await session.refresh(rule)

    return RoutingRuleSchema(
        id=str(rule.id),
        specialist_name=rule.specialist_name,
        custom_specialist_id=str(rule.custom_specialist_id)
        if rule.custom_specialist_id
        else None,
        rule_type=rule.rule_type.value,
        rule_value=rule.rule_value,
        priority=rule.priority,
        description=rule.description,
        is_enabled=rule.is_enabled,
        created_at=rule.created_at,
    )


@admin_router.delete("/routing-rules/{rule_id}")
async def delete_routing_rule(
    rule_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Delete a routing rule."""
    result = await session.execute(
        select(SpecialistRoutingRule).where(SpecialistRoutingRule.id == UUID(rule_id))
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(404, "Routing rule not found")

    await session.delete(rule)
    await session.commit()

    return {"status": "deleted", "id": rule_id}


@admin_router.post("/routing-rules/test", response_model=RoutingRuleTestResultSchema)
async def test_routing_rules(
    body: RoutingRuleTestSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Test routing rules against sample input."""
    import re

    # Get all enabled rules ordered by priority
    result = await session.execute(
        select(SpecialistRoutingRule)
        .where(SpecialistRoutingRule.is_enabled.is_(True))
        .order_by(desc(SpecialistRoutingRule.priority))
    )
    rules = result.scalars().all()

    user_input_lower = body.user_input.lower()

    for rule in rules:
        if rule.rule_type == RoutingRuleTypeEnum.KEYWORD:
            keywords = [k.strip().lower() for k in rule.rule_value.split(",")]
            if any(kw in user_input_lower for kw in keywords):
                return RoutingRuleTestResultSchema(
                    matched=True,
                    matched_rule_id=str(rule.id),
                    specialist_name=rule.specialist_name,
                    rule_type=rule.rule_type.value,
                    confidence=0.8,
                )
        elif rule.rule_type == RoutingRuleTypeEnum.REGEX:
            try:
                if re.search(rule.rule_value, body.user_input, re.IGNORECASE):
                    return RoutingRuleTestResultSchema(
                        matched=True,
                        matched_rule_id=str(rule.id),
                        specialist_name=rule.specialist_name,
                        rule_type=rule.rule_type.value,
                        confidence=0.85,
                    )
            except re.error:
                continue  # Invalid regex, skip

    return RoutingRuleTestResultSchema(
        matched=False,
        matched_rule_id=None,
        specialist_name=None,
        rule_type=None,
        confidence=0.0,
    )


# =============================================================================
# Specialist Analytics Endpoints (Admin)
# =============================================================================


@admin_router.get(
    "/analytics/specialists", response_model=list[SpecialistAnalyticsSchema]
)
async def get_specialist_analytics(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get performance analytics for each specialist type."""
    from datetime import timedelta
    from collections import defaultdict

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get collaboration logs
    result = await session.execute(
        select(AgentCollaborationLog).where(
            AgentCollaborationLog.created_at >= cutoff_date
        )
    )
    logs = result.scalars().all()

    # Aggregate by specialist
    specialist_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "cost": 0.0,
            "duration": 0.0,
            "iterations": 0,
            "handoffs_from": 0,
            "handoffs_to": 0,
            "tools": defaultdict(int),
        }
    )

    for log in logs:
        for i, specialist in enumerate(log.agent_chain):
            data = specialist_data[specialist]
            data["total"] += 1

            if log.status == CollaborationStatusEnum.COMPLETED:
                data["successful"] += 1
            else:
                data["failed"] += 1

            # Approximate cost/duration per specialist (divide equally)
            chain_len = len(log.agent_chain)
            data["cost"] += log.total_cost_usd / chain_len
            data["duration"] += log.total_duration_ms / chain_len
            data["iterations"] += log.total_iterations / chain_len

            # Track handoffs
            if i > 0:
                data["handoffs_to"] += 1
            if i < len(log.agent_chain) - 1:
                data["handoffs_from"] += 1

            # Tool usage from steps
            for step in log.steps:
                if step.get("specialist") == specialist:
                    for tool_call in step.get("tool_calls", []):
                        tool_name = tool_call.get("name", "unknown")
                        data["tools"][tool_name] += 1

    # Format response
    analytics = []
    for name, data in specialist_data.items():
        total = data["total"]
        analytics.append(
            SpecialistAnalyticsSchema(
                specialist_name=name,
                total_invocations=total,
                success_rate=data["successful"] / total if total > 0 else 0,
                avg_cost_usd=data["cost"] / total if total > 0 else 0,
                avg_duration_ms=data["duration"] / total if total > 0 else 0,
                avg_iterations=data["iterations"] / total if total > 0 else 0,
                total_handoffs_from=data["handoffs_from"],
                total_handoffs_to=data["handoffs_to"],
                top_tools=dict(
                    sorted(data["tools"].items(), key=lambda x: x[1], reverse=True)[:5]
                ),
            )
        )

    # Sort by total invocations
    analytics.sort(key=lambda x: x.total_invocations, reverse=True)
    return analytics


@admin_router.get("/analytics/routing", response_model=RoutingAnalyticsSchema)
async def get_routing_analytics(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get routing performance analytics."""
    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get collaboration logs with routing info in extra_data
    result = await session.execute(
        select(AgentCollaborationLog).where(
            AgentCollaborationLog.created_at >= cutoff_date
        )
    )
    logs = result.scalars().all()

    total = len(logs)
    keyword_matches = 0
    llm_fallbacks = 0
    confidence_sum = 0.0
    specialist_counts: dict[str, int] = {}

    for log in logs:
        routing_info = log.extra_data.get("routing", {})
        method = routing_info.get("method", "keyword")

        if method == "keyword":
            keyword_matches += 1
        elif method == "llm":
            llm_fallbacks += 1

        confidence_sum += routing_info.get("confidence", 0.5)

        # Count initial specialist
        if log.agent_chain:
            initial = log.agent_chain[0]
            specialist_counts[initial] = specialist_counts.get(initial, 0) + 1

    # Top specialists by routing
    top_specialists = [
        {"name": k, "count": v}
        for k, v in sorted(specialist_counts.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]
    ]

    return RoutingAnalyticsSchema(
        total_classifications=total,
        keyword_match_rate=keyword_matches / total if total > 0 else 0,
        llm_fallback_rate=llm_fallbacks / total if total > 0 else 0,
        avg_confidence=confidence_sum / total if total > 0 else 0,
        top_specialists=top_specialists,
    )
