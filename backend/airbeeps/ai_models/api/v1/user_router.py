from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.ai_models.models import Model, ModelStatusEnum
from airbeeps.database import get_async_session

from .schemas import ModelResponse

router = APIRouter()


@router.get("/models", response_model=list[ModelResponse], summary="List active models")
async def list_active_models(session: AsyncSession = Depends(get_async_session)):
    """List all active models available for users (Chat only)"""
    query = select(Model).options(selectinload(Model.provider))
    query = query.where(Model.status == ModelStatusEnum.ACTIVE)

    result = await session.execute(query)
    models = result.scalars().all()

    # Hard restriction: only return models with 'chat' capability
    filtered_models = [model for model in models if "chat" in model.capabilities]

    return filtered_models
