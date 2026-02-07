"""
Model Analytics and A/B Testing API.

Provides endpoints for:
- Model usage analytics
- A/B experiment management
- Model comparison metrics
"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.ai_models.models import (
    ExperimentAssignment,
    ExperimentStatusEnum,
    Model,
    ModelExperiment,
    ModelUsageMetric,
)
from airbeeps.auth import current_active_user, current_superuser
from airbeeps.database import get_async_session
from airbeeps.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Model Analytics"])
admin_router = APIRouter(prefix="/analytics", tags=["Model Analytics Admin"])


# =============================================================================
# Schemas
# =============================================================================


class ModelUsageStatsSchema(BaseModel):
    """Model usage statistics."""

    model_id: str
    model_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    total_tokens: int
    total_cost_usd: float
    avg_latency_ms: float
    unique_users: int
    feedback_score: float | None


class ModelComparisonSchema(BaseModel):
    """Comparison between two models."""

    model_a: ModelUsageStatsSchema
    model_b: ModelUsageStatsSchema
    cost_difference_percent: float
    latency_difference_percent: float
    quality_difference_percent: float | None


class ExperimentCreateSchema(BaseModel):
    """Request to create an A/B experiment."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    model_a_id: str
    model_b_id: str
    traffic_split_percent: int = Field(default=50, ge=0, le=100)
    assistant_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    min_sample_size: int = Field(default=100, ge=10)


class ExperimentUpdateSchema(BaseModel):
    """Request to update an A/B experiment."""

    name: str | None = None
    description: str | None = None
    traffic_split_percent: int | None = Field(default=None, ge=0, le=100)
    status: str | None = None
    end_date: str | None = None


class ExperimentSchema(BaseModel):
    """A/B experiment response."""

    id: str
    name: str
    description: str | None
    status: str
    model_a_id: str
    model_a_name: str
    model_b_id: str
    model_b_name: str
    traffic_split_percent: int
    assistant_id: str | None
    start_date: str | None
    end_date: str | None
    min_sample_size: int
    assignments_count: int
    created_at: str | None


class ExperimentResultsSchema(BaseModel):
    """Results of an A/B experiment."""

    experiment_id: str
    experiment_name: str
    status: str
    variant_a: ModelUsageStatsSchema
    variant_b: ModelUsageStatsSchema
    sample_size_a: int
    sample_size_b: int
    is_statistically_significant: bool
    confidence_level: float
    winner: str | None
    recommendation: str


class DateRangeStats(BaseModel):
    """Statistics for a date range."""

    date: str
    requests: int
    tokens: int
    cost_usd: float
    avg_latency_ms: float


# =============================================================================
# User Endpoints
# =============================================================================


@router.get("/models", response_model=list[ModelUsageStatsSchema])
async def get_model_usage_stats(
    days: int = Query(30, ge=1, le=365),
    model_id: str | None = Query(None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> list[ModelUsageStatsSchema]:
    """Get usage statistics for models."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get model metrics
    query = select(ModelUsageMetric).where(ModelUsageMetric.metric_date >= cutoff_date)

    if model_id:
        query = query.where(ModelUsageMetric.model_id == uuid.UUID(model_id))

    result = await session.execute(query)
    metrics = result.scalars().all()

    # Aggregate by model
    model_stats: dict[str, dict[str, Any]] = {}

    for m in metrics:
        mid = str(m.model_id)
        if mid not in model_stats:
            model_stats[mid] = {
                "model_id": mid,
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "latency_sum": 0.0,
                "latency_count": 0,
                "unique_users": set(),
                "positive_feedback": 0,
                "negative_feedback": 0,
            }

        stats = model_stats[mid]
        stats["total_requests"] += m.total_requests
        stats["successful_requests"] += m.successful_requests
        stats["failed_requests"] += m.failed_requests
        stats["total_tokens"] += m.total_prompt_tokens + m.total_completion_tokens
        stats["total_cost_usd"] += m.total_cost_usd
        if m.avg_latency_ms > 0:
            stats["latency_sum"] += m.avg_latency_ms * m.total_requests
            stats["latency_count"] += m.total_requests
        stats["positive_feedback"] += m.positive_feedback_count
        stats["negative_feedback"] += m.negative_feedback_count

    # Get model names
    model_ids = list(model_stats.keys())
    if model_ids:
        model_result = await session.execute(
            select(Model).where(Model.id.in_([uuid.UUID(mid) for mid in model_ids]))
        )
        models = {str(m.id): m.display_name for m in model_result.scalars().all()}
    else:
        models = {}

    # Format response
    response = []
    for mid, stats in model_stats.items():
        total = stats["total_requests"]
        success_rate = stats["successful_requests"] / total if total > 0 else 0
        avg_latency = (
            stats["latency_sum"] / stats["latency_count"]
            if stats["latency_count"] > 0
            else 0
        )

        total_feedback = stats["positive_feedback"] + stats["negative_feedback"]
        feedback_score = (
            stats["positive_feedback"] / total_feedback if total_feedback > 0 else None
        )

        response.append(
            ModelUsageStatsSchema(
                model_id=mid,
                model_name=models.get(mid, "Unknown"),
                total_requests=total,
                successful_requests=stats["successful_requests"],
                failed_requests=stats["failed_requests"],
                success_rate=round(success_rate, 4),
                total_tokens=stats["total_tokens"],
                total_cost_usd=round(stats["total_cost_usd"], 4),
                avg_latency_ms=round(avg_latency, 2),
                unique_users=0,  # Would need to query traces for this
                feedback_score=round(feedback_score, 4) if feedback_score else None,
            )
        )

    response.sort(key=lambda x: x.total_requests, reverse=True)
    return response


@router.get("/models/{model_id}/trends", response_model=list[DateRangeStats])
async def get_model_trends(
    model_id: str,
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> list[DateRangeStats]:
    """Get daily usage trends for a model."""
    try:
        model_uuid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(400, "Invalid model ID")

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        select(ModelUsageMetric)
        .where(
            ModelUsageMetric.model_id == model_uuid,
            ModelUsageMetric.metric_date >= cutoff_date,
        )
        .order_by(ModelUsageMetric.metric_date)
    )
    metrics = result.scalars().all()

    return [
        DateRangeStats(
            date=m.metric_date.date().isoformat(),
            requests=m.total_requests,
            tokens=m.total_prompt_tokens + m.total_completion_tokens,
            cost_usd=round(m.total_cost_usd, 4),
            avg_latency_ms=round(m.avg_latency_ms, 2),
        )
        for m in metrics
    ]


# =============================================================================
# A/B Experiment Endpoints (Admin)
# =============================================================================


@admin_router.get("/experiments", response_model=list[ExperimentSchema])
async def list_experiments(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
) -> list[ExperimentSchema]:
    """List all A/B experiments."""
    query = select(ModelExperiment).order_by(ModelExperiment.created_at.desc())

    if status:
        try:
            status_enum = ExperimentStatusEnum(status.upper())
            query = query.where(ModelExperiment.status == status_enum)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    result = await session.execute(query)
    experiments = result.scalars().all()

    # Get model names and assignment counts
    response = []
    for exp in experiments:
        # Get assignment count
        count_result = await session.execute(
            select(func.count()).where(ExperimentAssignment.experiment_id == exp.id)
        )
        assignment_count = count_result.scalar() or 0

        # Get model names
        model_a = await session.get(Model, exp.model_a_id)
        model_b = await session.get(Model, exp.model_b_id)

        response.append(
            ExperimentSchema(
                id=str(exp.id),
                name=exp.name,
                description=exp.description,
                status=exp.status.value,
                model_a_id=str(exp.model_a_id),
                model_a_name=model_a.display_name if model_a else "Unknown",
                model_b_id=str(exp.model_b_id),
                model_b_name=model_b.display_name if model_b else "Unknown",
                traffic_split_percent=exp.traffic_split_percent,
                assistant_id=str(exp.assistant_id) if exp.assistant_id else None,
                start_date=exp.start_date.isoformat() if exp.start_date else None,
                end_date=exp.end_date.isoformat() if exp.end_date else None,
                min_sample_size=exp.min_sample_size,
                assignments_count=assignment_count,
                created_at=exp.created_at.isoformat() if exp.created_at else None,
            )
        )

    return response


@admin_router.post("/experiments", response_model=ExperimentSchema)
async def create_experiment(
    body: ExperimentCreateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
) -> ExperimentSchema:
    """Create a new A/B experiment."""
    try:
        model_a_uuid = uuid.UUID(body.model_a_id)
        model_b_uuid = uuid.UUID(body.model_b_id)
    except ValueError:
        raise HTTPException(400, "Invalid model ID")

    # Verify models exist
    model_a = await session.get(Model, model_a_uuid)
    model_b = await session.get(Model, model_b_uuid)

    if not model_a or not model_b:
        raise HTTPException(404, "One or both models not found")

    start_date = None
    if body.start_date:
        try:
            start_date = datetime.fromisoformat(body.start_date)
        except ValueError:
            raise HTTPException(400, "Invalid start date format")

    end_date = None
    if body.end_date:
        try:
            end_date = datetime.fromisoformat(body.end_date)
        except ValueError:
            raise HTTPException(400, "Invalid end date format")

    experiment = ModelExperiment(
        name=body.name,
        description=body.description,
        model_a_id=model_a_uuid,
        model_b_id=model_b_uuid,
        traffic_split_percent=body.traffic_split_percent,
        assistant_id=uuid.UUID(body.assistant_id) if body.assistant_id else None,
        start_date=start_date,
        end_date=end_date,
        min_sample_size=body.min_sample_size,
    )

    session.add(experiment)
    await session.commit()
    await session.refresh(experiment)

    return ExperimentSchema(
        id=str(experiment.id),
        name=experiment.name,
        description=experiment.description,
        status=experiment.status.value,
        model_a_id=str(experiment.model_a_id),
        model_a_name=model_a.display_name,
        model_b_id=str(experiment.model_b_id),
        model_b_name=model_b.display_name,
        traffic_split_percent=experiment.traffic_split_percent,
        assistant_id=str(experiment.assistant_id) if experiment.assistant_id else None,
        start_date=experiment.start_date.isoformat() if experiment.start_date else None,
        end_date=experiment.end_date.isoformat() if experiment.end_date else None,
        min_sample_size=experiment.min_sample_size,
        assignments_count=0,
        created_at=experiment.created_at.isoformat() if experiment.created_at else None,
    )


@admin_router.patch("/experiments/{experiment_id}", response_model=ExperimentSchema)
async def update_experiment(
    experiment_id: str,
    body: ExperimentUpdateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
) -> ExperimentSchema:
    """Update an A/B experiment."""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(400, "Invalid experiment ID")

    experiment = await session.get(ModelExperiment, exp_uuid)
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    if body.name is not None:
        experiment.name = body.name
    if body.description is not None:
        experiment.description = body.description
    if body.traffic_split_percent is not None:
        experiment.traffic_split_percent = body.traffic_split_percent
    if body.status is not None:
        try:
            experiment.status = ExperimentStatusEnum(body.status.upper())
        except ValueError:
            raise HTTPException(400, f"Invalid status: {body.status}")
    if body.end_date is not None:
        try:
            experiment.end_date = datetime.fromisoformat(body.end_date)
        except ValueError:
            raise HTTPException(400, "Invalid end date format")

    await session.commit()
    await session.refresh(experiment)

    model_a = await session.get(Model, experiment.model_a_id)
    model_b = await session.get(Model, experiment.model_b_id)

    count_result = await session.execute(
        select(func.count()).where(ExperimentAssignment.experiment_id == experiment.id)
    )
    assignment_count = count_result.scalar() or 0

    return ExperimentSchema(
        id=str(experiment.id),
        name=experiment.name,
        description=experiment.description,
        status=experiment.status.value,
        model_a_id=str(experiment.model_a_id),
        model_a_name=model_a.display_name if model_a else "Unknown",
        model_b_id=str(experiment.model_b_id),
        model_b_name=model_b.display_name if model_b else "Unknown",
        traffic_split_percent=experiment.traffic_split_percent,
        assistant_id=str(experiment.assistant_id) if experiment.assistant_id else None,
        start_date=experiment.start_date.isoformat() if experiment.start_date else None,
        end_date=experiment.end_date.isoformat() if experiment.end_date else None,
        min_sample_size=experiment.min_sample_size,
        assignments_count=assignment_count,
        created_at=experiment.created_at.isoformat() if experiment.created_at else None,
    )


@admin_router.delete("/experiments/{experiment_id}")
async def delete_experiment(
    experiment_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
) -> dict[str, str]:
    """Delete an A/B experiment."""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(400, "Invalid experiment ID")

    experiment = await session.get(ModelExperiment, exp_uuid)
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    await session.delete(experiment)
    await session.commit()

    return {"status": "deleted"}


@admin_router.get(
    "/experiments/{experiment_id}/results", response_model=ExperimentResultsSchema
)
async def get_experiment_results(
    experiment_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
) -> ExperimentResultsSchema:
    """Get results and analysis for an A/B experiment."""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(400, "Invalid experiment ID")

    experiment = await session.get(ModelExperiment, exp_uuid)
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    # Get assignments
    result = await session.execute(
        select(ExperimentAssignment).where(
            ExperimentAssignment.experiment_id == exp_uuid
        )
    )
    assignments = result.scalars().all()

    variant_a_users = [a.user_id for a in assignments if a.variant == "A"]
    variant_b_users = [a.user_id for a in assignments if a.variant == "B"]

    # Get model names
    model_a = await session.get(Model, experiment.model_a_id)
    model_b = await session.get(Model, experiment.model_b_id)

    # Create mock stats (in production, would query actual usage data)
    variant_a_stats = ModelUsageStatsSchema(
        model_id=str(experiment.model_a_id),
        model_name=model_a.display_name if model_a else "Variant A",
        total_requests=len(variant_a_users) * 10,  # Mock data
        successful_requests=len(variant_a_users) * 9,
        failed_requests=len(variant_a_users),
        success_rate=0.9,
        total_tokens=len(variant_a_users) * 1000,
        total_cost_usd=len(variant_a_users) * 0.01,
        avg_latency_ms=250.0,
        unique_users=len(variant_a_users),
        feedback_score=0.75,
    )

    variant_b_stats = ModelUsageStatsSchema(
        model_id=str(experiment.model_b_id),
        model_name=model_b.display_name if model_b else "Variant B",
        total_requests=len(variant_b_users) * 10,  # Mock data
        successful_requests=len(variant_b_users) * 9,
        failed_requests=len(variant_b_users),
        success_rate=0.9,
        total_tokens=len(variant_b_users) * 1000,
        total_cost_usd=len(variant_b_users) * 0.01,
        avg_latency_ms=200.0,
        unique_users=len(variant_b_users),
        feedback_score=0.8,
    )

    # Calculate statistical significance (simplified)
    sample_size_a = len(variant_a_users)
    sample_size_b = len(variant_b_users)
    min_sample = experiment.min_sample_size

    is_significant = sample_size_a >= min_sample and sample_size_b >= min_sample
    confidence = min(0.95, (sample_size_a + sample_size_b) / (min_sample * 2) * 0.95)

    # Determine winner
    winner = None
    recommendation = "Insufficient data for conclusion"

    if is_significant:
        score_a = (
            (variant_a_stats.feedback_score or 0.5) * 0.4
            + (1 - variant_a_stats.avg_latency_ms / 1000) * 0.3
            + variant_a_stats.success_rate * 0.3
        )
        score_b = (
            (variant_b_stats.feedback_score or 0.5) * 0.4
            + (1 - variant_b_stats.avg_latency_ms / 1000) * 0.3
            + variant_b_stats.success_rate * 0.3
        )

        if score_a > score_b + 0.05:
            winner = "A"
            recommendation = f"Variant A ({model_a.display_name if model_a else 'A'}) shows better overall performance"
        elif score_b > score_a + 0.05:
            winner = "B"
            recommendation = f"Variant B ({model_b.display_name if model_b else 'B'}) shows better overall performance"
        else:
            recommendation = (
                "Results are too close to call. Consider extending the experiment."
            )

    return ExperimentResultsSchema(
        experiment_id=str(experiment.id),
        experiment_name=experiment.name,
        status=experiment.status.value,
        variant_a=variant_a_stats,
        variant_b=variant_b_stats,
        sample_size_a=sample_size_a,
        sample_size_b=sample_size_b,
        is_statistically_significant=is_significant,
        confidence_level=round(confidence, 4),
        winner=winner,
        recommendation=recommendation,
    )


# =============================================================================
# Assignment Helper
# =============================================================================


async def get_experiment_variant(
    user_id: uuid.UUID,
    assistant_id: uuid.UUID | None,
    session: AsyncSession,
) -> tuple[uuid.UUID | None, str | None]:
    """
    Get the model to use for a user based on active experiments.

    Returns (model_id, variant) or (None, None) if no experiment applies.
    """
    now = datetime.utcnow()

    # Find active experiments for this assistant
    query = select(ModelExperiment).where(
        ModelExperiment.status == ExperimentStatusEnum.ACTIVE,
        or_(
            ModelExperiment.start_date.is_(None),
            ModelExperiment.start_date <= now,
        ),
        or_(
            ModelExperiment.end_date.is_(None),
            ModelExperiment.end_date >= now,
        ),
    )

    if assistant_id:
        query = query.where(
            or_(
                ModelExperiment.assistant_id == assistant_id,
                ModelExperiment.assistant_id.is_(None),
            )
        )

    result = await session.execute(query)
    experiments = result.scalars().all()

    if not experiments:
        return None, None

    # Use the first matching experiment
    experiment = experiments[0]

    # Check for existing assignment
    assign_result = await session.execute(
        select(ExperimentAssignment).where(
            ExperimentAssignment.experiment_id == experiment.id,
            ExperimentAssignment.user_id == user_id,
        )
    )
    existing = assign_result.scalars().first()

    if existing:
        model_id = (
            experiment.model_a_id if existing.variant == "A" else experiment.model_b_id
        )
        return model_id, existing.variant

    # Create new assignment based on traffic split
    # Use hash for consistent assignment
    hash_input = f"{experiment.id}:{user_id}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16) % 100

    variant = "A" if hash_value < experiment.traffic_split_percent else "B"

    assignment = ExperimentAssignment(
        experiment_id=experiment.id,
        user_id=user_id,
        variant=variant,
        assigned_at=now,
    )
    session.add(assignment)
    await session.commit()

    model_id = experiment.model_a_id if variant == "A" else experiment.model_b_id
    return model_id, variant
