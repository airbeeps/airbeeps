import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.ai_models.hf_assets import (
    ASSET_TYPE_HF_EMBEDDING,
    enqueue_hf_embedding_download,
    list_hf_hub_cached_model_repo_ids,
    resolve_hf_hub_cached_snapshot_dir,
)
from airbeeps.ai_models.models import (
    Model,
    ModelAsset,
    ModelAssetStatusEnum,
    ModelProvider,
    ProviderCategoryEnum,
)
from airbeeps.database import get_async_session

from .schemas import (
    HuggingFaceDownloadRequest,
    HuggingFaceResolveResponse,
    ModelAssetResponse,
    ModelCreate,
    ModelProviderCreate,
    ModelProviderResponse,
    ModelProviderUpdate,
    ModelResponse,
    ModelStatusEnum,
    ModelUpdate,
    ProviderStatusEnum,
)

router = APIRouter()


# ============================================================================
# LiteLLM Providers (Dynamic from LiteLLM SDK)
# ============================================================================


@router.get(
    "/litellm-providers",
    summary="List all providers supported by LiteLLM",
)
async def list_litellm_providers():
    """
    Get list of all providers supported by LiteLLM SDK.
    This is dynamically fetched from LiteLLM's provider_list.
    """
    from airbeeps.ai_models.litellm_providers import get_all_providers_info

    return get_all_providers_info()


@router.get(
    "/litellm-providers/by-category",
    summary="List LiteLLM providers grouped by category",
)
async def list_litellm_providers_by_category():
    """
    Get providers grouped by category (OpenAI-compatible, Native, Custom, Local).
    """
    from airbeeps.ai_models.litellm_providers import get_providers_by_category

    return get_providers_by_category()


@router.get(
    "/litellm-providers/{provider_id}",
    summary="Get info for a specific LiteLLM provider",
)
async def get_litellm_provider_info(provider_id: str):
    """Get metadata for a specific LiteLLM provider."""
    from airbeeps.ai_models.litellm_providers import get_provider_info

    return get_provider_info(provider_id)


# ============================================================================
# Model discovery and available models
# ============================================================================


@router.get(
    "/providers/{provider_id}/available-models",
    summary="List available models from provider (live fetch with caching)",
)
async def list_available_models(
    provider_id: uuid.UUID,
    force_refresh: bool = Query(False, description="Force refresh cache"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Fetch available models from the provider.

    This endpoint:
    1. Attempts to fetch models directly from the provider (quick method)
    2. Falls back to comprehensive discovery if quick fails
    3. Caches results in memory for 5 minutes
    4. Returns empty list if provider doesn't support discovery

    Args:
        provider_id: Provider UUID
        force_refresh: If True, bypass cache and fetch fresh data
    """
    import logging
    from datetime import datetime, timedelta

    logger = logging.getLogger(__name__)

    # Simple in-memory cache (5 minute TTL)
    cache_key = f"models_{provider_id}"
    cache_ttl = timedelta(minutes=5)

    # Check cache first (unless force_refresh)
    if not force_refresh and hasattr(list_available_models, "_cache"):
        cached = list_available_models._cache.get(cache_key)
        if cached and datetime.now() - cached["timestamp"] < cache_ttl:
            logger.info(f"Returning cached models for provider {provider_id}")
            return cached["data"]

    # Fetch provider
    provider = await _get_provider_or_404(session, provider_id)

    # Try to discover models
    try:
        # First try quick discovery (OpenAI-compatible)
        if provider.category == ProviderCategoryEnum.OPENAI_COMPATIBLE or (
            provider.category == ProviderCategoryEnum.CUSTOM
            and provider.is_openai_compatible
        ):
            try:
                models = await _discover_models_quick(provider)
                logger.info(
                    f"Quick discovery found {len(models)} models for provider {provider_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Quick discovery failed for provider {provider_id}: {e}, trying comprehensive"
                )
                models = await _discover_models_comprehensive(provider)
        else:
            # Use comprehensive for provider-specific
            models = await _discover_models_comprehensive(provider)
            logger.info(
                f"Comprehensive discovery found {len(models)} models for provider {provider_id}"
            )

        # Format response
        result = {
            "provider_id": str(provider_id),
            "provider_name": provider.display_name,
            "models": [{"id": m, "name": m} for m in models],
            "cached_at": datetime.now().isoformat(),
        }

        # Cache the result
        if not hasattr(list_available_models, "_cache"):
            list_available_models._cache = {}
        list_available_models._cache[cache_key] = {
            "data": result,
            "timestamp": datetime.now(),
        }

        return result

    except Exception as e:
        logger.error(f"Model discovery failed for provider {provider_id}: {e}")
        # Return empty list instead of failing
        return {
            "provider_id": str(provider_id),
            "provider_name": provider.display_name,
            "models": [],
            "error": str(e),
        }


# ============================================================================
# Provider utilities (test/discover)
# ============================================================================


def _is_test_mode() -> bool:
    """Check if test mode is enabled."""
    from airbeeps.config import settings

    return settings.TEST_MODE


async def _get_provider_or_404(
    session: AsyncSession, provider_id: uuid.UUID
) -> ModelProvider:
    """Helper to get provider or raise 404."""
    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


async def _test_openai_compatible_connection(provider: ModelProvider) -> dict:
    """Test OpenAI-compatible endpoint via direct HTTP."""
    import logging

    import httpx

    logger = logging.getLogger(__name__)

    url = provider.api_base_url.rstrip("/") + "/models"
    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 200:
            # Count available models
            try:
                data = resp.json().get("data", [])
                model_count = len(data) if isinstance(data, list) else 0
                return {
                    "ok": True,
                    "status_code": 200,
                    "message": f"Connected successfully ({model_count} models available)",
                }
            except Exception:
                return {
                    "ok": True,
                    "status_code": 200,
                    "message": "Connected successfully",
                }
        elif resp.status_code == 401:
            return {"ok": False, "message": "Unauthorized. Check your API key."}
        elif resp.status_code == 403:
            return {"ok": False, "message": "Forbidden. API key may lack permissions."}
        elif resp.status_code == 404:
            return {"ok": False, "message": "Endpoint not found. Verify the base URL."}
        else:
            return {
                "ok": False,
                "message": f"Status {resp.status_code}",
                "detail": resp.text[:200],
            }
    except httpx.TimeoutException:
        return {"ok": False, "message": "Connection timeout. Check the base URL."}
    except Exception as e:
        logger.error(f"Connection test error: {e}")
        return {"ok": False, "message": f"Connection error: {e!s}"}


async def _test_litellm_provider_connection(provider: ModelProvider) -> dict:
    """Test provider-specific connection using LiteLLM validation."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        from litellm import validate_environment

        # Build a test model name for validation
        test_model = f"{provider.litellm_provider}/test-model"

        # Validate environment setup
        env_result = await asyncio.to_thread(
            validate_environment,
            model=test_model,
            api_key=provider.api_key,
            api_base=provider.api_base_url,
        )

        if not env_result.get("keys_in_environment"):
            missing = env_result.get("missing_keys", [])
            return {
                "ok": False,
                "message": f"Missing configuration: {', '.join(missing)}",
            }

        # Environment is valid
        return {
            "ok": True,
            "message": "Configuration validated (actual model calls will work)",
        }
    except ImportError:
        logger.warning("LiteLLM not available for validation")
        return {
            "ok": True,
            "message": "Basic validation passed (LiteLLM validation unavailable)",
        }
    except Exception as e:
        logger.error(f"LiteLLM validation error: {e}")
        return {"ok": False, "message": f"Validation error: {e!s}"}


@router.post(
    "/providers/{provider_id}/test-connection",
    summary="Test provider connectivity/auth (best-effort)",
)
async def test_provider_connection(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Test provider connection using category-aware strategies."""
    import logging

    logger = logging.getLogger(__name__)

    # Short-circuit in test mode
    if _is_test_mode():
        return {"ok": True, "message": "TEST_MODE: Connection test skipped"}

    provider = await _get_provider_or_404(session, provider_id)

    # Local providers don't need connectivity checks
    if provider.category == ProviderCategoryEnum.LOCAL:
        return {"ok": True, "message": "Local provider"}

    try:
        # Strategy 1: For OpenAI-compatible, try direct HTTP first (fast)
        if provider.category == ProviderCategoryEnum.OPENAI_COMPATIBLE or (
            provider.category == ProviderCategoryEnum.CUSTOM
            and provider.is_openai_compatible
        ):
            return await _test_openai_compatible_connection(provider)

        # Strategy 2: For provider-specific, use LiteLLM validation
        return await _test_litellm_provider_connection(provider)

    except Exception as e:
        logger.error(f"Connection test failed for provider {provider_id}: {e}")
        return {"ok": False, "message": f"Connection error: {e!s}"}


async def _discover_models_quick(provider: ModelProvider) -> list[str]:
    """Quick discovery via direct HTTP /models endpoint."""
    import httpx

    url = provider.api_base_url.rstrip("/") + "/models"
    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Provider returned status {resp.status_code}",
        )

    data = resp.json().get("data", [])
    if not isinstance(data, list):
        return []

    models = [m["id"] for m in data if isinstance(m, dict) and m.get("id")]
    return sorted(set(models))


async def _discover_models_comprehensive(provider: ModelProvider) -> list[str]:
    """Comprehensive discovery using LiteLLM's get_valid_models."""
    import logging
    import os

    logger = logging.getLogger(__name__)

    try:
        from litellm import get_valid_models
    except ImportError:
        logger.warning("LiteLLM not available for model discovery")
        raise HTTPException(
            status_code=501,
            detail="Comprehensive discovery requires LiteLLM (not installed)",
        )

    # Set up environment for this provider
    cleanup_vars = []

    try:
        # Set provider-specific environment variables
        if provider.api_key:
            key_var = f"{provider.litellm_provider.upper()}_API_KEY"
            os.environ[key_var] = provider.api_key
            cleanup_vars.append(key_var)

        if provider.api_base_url:
            base_var = f"{provider.litellm_provider.upper()}_API_BASE"
            os.environ[base_var] = provider.api_base_url
            cleanup_vars.append(base_var)

        # Call LiteLLM's get_valid_models
        models = await asyncio.to_thread(
            get_valid_models,
            custom_llm_provider=provider.litellm_provider,
            check_provider_endpoint=True,
        )

        return sorted(models) if models else []

    finally:
        # Clean up environment variables
        for var in cleanup_vars:
            if var in os.environ:
                del os.environ[var]


@router.get(
    "/providers/{provider_id}/discover-models",
    summary="Discover available models from provider",
)
async def discover_models_from_provider(
    provider_id: uuid.UUID,
    method: str = Query(
        "auto", description="Discovery method: 'auto', 'quick', 'comprehensive'"
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Discover available models from provider.

    Methods:
    - auto: Choose best method based on provider category
    - quick: Direct HTTP /models (OpenAI-compatible only)
    - comprehensive: LiteLLM get_valid_models (works for all, slower)
    """
    import logging

    logger = logging.getLogger(__name__)

    # Short-circuit in test mode
    if _is_test_mode():
        return ["test-model-1", "test-model-2", "test-gpt-4"]

    provider = await _get_provider_or_404(session, provider_id)

    # Determine discovery method
    if method == "auto":
        if provider.category == ProviderCategoryEnum.OPENAI_COMPATIBLE or (
            provider.category == ProviderCategoryEnum.CUSTOM
            and provider.is_openai_compatible
        ):
            method = "quick"
        else:
            method = "comprehensive"

    try:
        if method == "quick":
            return await _discover_models_quick(provider)
        return await _discover_models_comprehensive(provider)
    except Exception as e:
        logger.error(f"Model discovery failed for provider {provider_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery failed: {e!s}")


# list all providers (non-paginated)
@router.get(
    "/all-providers",
    response_model=list[ModelProviderResponse],
    summary="List all providers",
)
async def list_all_providers(session: AsyncSession = Depends(get_async_session)):
    """List model providers with pagination and filtering"""
    query = select(ModelProvider)

    query = query.where(ModelProvider.status == ProviderStatusEnum.ACTIVE)

    result = await session.execute(query)

    return result.scalars().all()


# Provider list
@router.get(
    "/providers",
    response_model=Page[ModelProviderResponse],
    summary="List model providers",
)
async def list_providers(
    status: ProviderStatusEnum | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search in name or display_name"),
    session: AsyncSession = Depends(get_async_session),
):
    """List model providers with pagination and filtering"""
    query = select(ModelProvider)

    # Apply filters
    if status:
        query = query.where(ModelProvider.status == status)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            (ModelProvider.name.ilike(search_term))
            | (ModelProvider.display_name.ilike(search_term))
        )

    return await sqlalchemy_paginate(session, query)


@router.post(
    "/providers",
    response_model=ModelProviderResponse,
    summary="Create a new model provider",
)
async def create_provider(
    provider_data: ModelProviderCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new model provider"""
    # Check if provider with same name already exists
    existing = await session.execute(
        select(ModelProvider).where(ModelProvider.name == provider_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Provider with this name already exists"
        )

    provider = ModelProvider(**provider_data.model_dump())
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider


# Provider detail endpoints - parameterized paths last
@router.get(
    "/providers/{provider_id}",
    response_model=ModelProviderResponse,
    summary="Get a model provider",
)
async def get_provider(
    provider_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
):
    """Get a specific model provider by ID"""
    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return provider


@router.put(
    "/providers/{provider_id}",
    response_model=ModelProviderResponse,
    summary="Update a model provider",
)
async def update_provider(
    provider_id: uuid.UUID,
    provider_data: ModelProviderUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update a model provider"""
    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Check for name conflicts if name is being updated
    if provider_data.name and provider_data.name != provider.name:
        existing = await session.execute(
            select(ModelProvider).where(ModelProvider.name == provider_data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail="Provider with this name already exists"
            )

    # Update fields
    update_data = provider_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)

    await session.commit()
    await session.refresh(provider)
    return provider


@router.delete("/providers/{provider_id}", summary="Delete a model provider")
async def delete_provider(
    provider_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
):
    """Delete a model provider and all associated models"""
    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    await session.delete(provider)
    await session.commit()
    return {"message": "Provider deleted successfully"}


@router.get(
    "/all-models", response_model=list[ModelResponse], summary="List all models"
)
async def list_all_models(
    capabilities: list[str] | None = Query(
        None,
        description="Filter model capabilities, return models containing all specified capabilities, multiple selection allowed",
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """List all models, support filtering by multiple capabilities (all must be included)"""
    query = select(Model).options(selectinload(Model.provider))
    query = query.where(Model.status == ModelStatusEnum.ACTIVE)
    result = await session.execute(query)
    models = result.scalars().all()

    # Filter capabilities at Python level to ensure database compatibility
    if capabilities:
        filtered_models = []
        for model in models:
            # Check if model contains all specified capabilities
            if all(cap in model.capabilities for cap in capabilities):
                filtered_models.append(model)
        return filtered_models

    return models


# Model list and create endpoints
@router.get("/models", response_model=Page[ModelResponse], summary="List models")
async def list_models(
    status: ModelStatusEnum | None = Query(None, description="Filter by status"),
    provider_id: uuid.UUID | None = Query(None, description="Filter by provider"),
    capability: str | None = Query(None, description="Filter by capability"),
    search: str | None = Query(None, description="Search in name or display_name"),
    session: AsyncSession = Depends(get_async_session),
):
    """List models with pagination and filtering"""
    query = select(Model).options(selectinload(Model.provider))

    # Apply filters
    if status:
        query = query.where(Model.status == status)

    if provider_id:
        query = query.where(Model.provider_id == provider_id)

    # Note: capability filtering is handled at Python level due to database compatibility issues
    # Not filtering at SQL level here

    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Model.name.ilike(search_term)) | (Model.display_name.ilike(search_term))
        )

    # If capability filtering is present, filter at Python level before pagination
    if capability:
        # Get all results first
        result = await session.execute(query)
        all_models = result.scalars().all()

        # Filter at Python level
        filtered_models = [m for m in all_models if capability in m.capabilities]

        # Manually implement pagination (not optimal, but ensures compatibility)
        from fastapi_pagination import Page as PageType, Params

        # Get current pagination params
        params = Params()

        # Calculate pagination
        total = len(filtered_models)
        start = (params.page - 1) * params.size
        end = start + params.size
        page_items = filtered_models[start:end]

        return PageType.create(items=page_items, total=total, params=params)

    return await sqlalchemy_paginate(session, query)


@router.post("/models", response_model=ModelResponse, summary="Create a new model")
async def create_model(
    model_data: ModelCreate, session: AsyncSession = Depends(get_async_session)
):
    """Create a new model"""
    # Check if provider exists
    provider_result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == model_data.provider_id)
    )
    if not provider_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider not found")

    # Check if model with same name and provider already exists
    existing = await session.execute(
        select(Model).where(
            (Model.name == model_data.name)
            & (Model.provider_id == model_data.provider_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Model with this name already exists for this provider",
        )

    model = Model(**model_data.model_dump())
    session.add(model)
    await session.commit()
    await session.refresh(model, ["provider"])
    return model


# Model detail endpoints - parameterized paths last
@router.get("/models/{model_id}", response_model=ModelResponse, summary="Get a model")
async def get_model(
    model_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
):
    """Get a specific model by ID"""
    result = await session.execute(
        select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
    )
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return model


@router.put(
    "/models/{model_id}", response_model=ModelResponse, summary="Update a model"
)
async def update_model(
    model_id: uuid.UUID,
    model_data: ModelUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update a model"""
    result = await session.execute(
        select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
    )
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Check if provider exists if provider_id is being updated
    if model_data.provider_id and model_data.provider_id != model.provider_id:
        provider_result = await session.execute(
            select(ModelProvider).where(ModelProvider.id == model_data.provider_id)
        )
        if not provider_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Provider not found")

    # Check for name conflicts if name or provider is being updated
    if (model_data.name and model_data.name != model.name) or (
        model_data.provider_id and model_data.provider_id != model.provider_id
    ):
        check_name = model_data.name or model.name
        check_provider_id = model_data.provider_id or model.provider_id

        existing = await session.execute(
            select(Model).where(
                (Model.name == check_name)
                & (Model.provider_id == check_provider_id)
                & (Model.id != model_id)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Model with this name already exists for this provider",
            )

    # Update fields
    update_data = model_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)

    await session.commit()
    await session.refresh(model)
    return model


@router.delete("/models/{model_id}", summary="Delete a model")
async def delete_model(
    model_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
):
    """Delete a model"""
    result = await session.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    await session.delete(model)
    await session.commit()
    return {"message": "Model deleted successfully"}


# ============================================================================
# Local model assets (Hugging Face local embeddings)
# ============================================================================


@router.get(
    "/model-assets/huggingface/embeddings",
    response_model=list[ModelAssetResponse],
    summary="List Hugging Face local embedding assets",
)
async def list_hf_embedding_assets(
    status: ModelAssetStatusEnum | None = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_async_session),
):
    query = select(ModelAsset).where(ModelAsset.asset_type == ASSET_TYPE_HF_EMBEDDING)
    if status:
        query = query.where(ModelAsset.status == status)
    result = await session.execute(query)
    return result.scalars().all()


@router.get(
    "/model-assets/huggingface/embeddings/installed-repos",
    response_model=list[str],
    summary="List Hugging Face embedding repos installed locally (AirBeeps assets + HF cache)",
)
async def list_hf_embedding_installed_repos(
    session: AsyncSession = Depends(get_async_session),
):
    # AirBeeps-managed downloads
    result = await session.execute(
        select(ModelAsset.identifier)
        .where(ModelAsset.asset_type == ASSET_TYPE_HF_EMBEDDING)
        .where(ModelAsset.status == ModelAssetStatusEnum.READY)
    )
    managed = [row[0] for row in result.all() if row and row[0]]

    # HuggingFace hub cache (best-effort)
    cached = list_hf_hub_cached_model_repo_ids()

    return sorted(set(managed + cached))


@router.post(
    "/model-assets/huggingface/embeddings/download",
    response_model=ModelAssetResponse,
    summary="Download a Hugging Face embedding model snapshot",
)
async def download_hf_embedding_asset(
    req: HuggingFaceDownloadRequest,
    session: AsyncSession = Depends(get_async_session),
):
    repo_id = req.repo_id.strip()
    if not repo_id:
        raise HTTPException(status_code=400, detail="repo_id is required")

    # Upsert by (asset_type, identifier)
    existing = await session.execute(
        select(ModelAsset).where(
            (ModelAsset.asset_type == ASSET_TYPE_HF_EMBEDDING)
            & (ModelAsset.identifier == repo_id)
        )
    )
    asset = existing.scalar_one_or_none()
    if asset:
        asset.revision = req.revision
        asset.status = ModelAssetStatusEnum.QUEUED
        asset.error_message = None
    else:
        asset = ModelAsset(
            asset_type=ASSET_TYPE_HF_EMBEDDING,
            identifier=repo_id,
            revision=req.revision,
            status=ModelAssetStatusEnum.QUEUED,
            extra_data={},
        )
        session.add(asset)

    await session.commit()
    await session.refresh(asset)

    # Fire-and-forget background download
    await enqueue_hf_embedding_download(asset.id)
    return asset


@router.get(
    "/model-assets/huggingface/embeddings/resolve",
    response_model=HuggingFaceResolveResponse,
    summary="Resolve whether a Hugging Face embedding model is already available locally",
)
async def resolve_hf_embedding_availability(
    repo_id: str = Query(..., description="Hugging Face repo id"),
    revision: str | None = Query(None, description="Optional revision/tag/commit"),
    session: AsyncSession = Depends(get_async_session),
):
    repo_id = (repo_id or "").strip()
    if not repo_id:
        raise HTTPException(status_code=400, detail="repo_id is required")

    # 1) Prefer our tracked local assets
    existing = await session.execute(
        select(ModelAsset).where(
            (ModelAsset.asset_type == ASSET_TYPE_HF_EMBEDDING)
            & (ModelAsset.identifier == repo_id)
        )
    )
    asset = existing.scalar_one_or_none()
    if asset and asset.status == ModelAssetStatusEnum.READY and asset.local_path:
        return {
            "repo_id": repo_id,
            "revision": asset.revision,
            "available": True,
            "source": "model_asset",
            "local_path": asset.local_path,
            "asset_id": asset.id,
        }

    # 2) Check Hugging Face global cache (no network)
    try:
        from huggingface_hub import snapshot_download

        local_path = await asyncio.to_thread(
            snapshot_download,
            repo_id=repo_id,
            revision=revision,
            local_files_only=True,
        )

        # Optionally: record this as READY so UI can show "installed" without re-checking.
        if asset:
            asset.revision = revision or asset.revision
            asset.local_path = str(local_path)
            asset.status = ModelAssetStatusEnum.READY
            asset.error_message = None
        else:
            asset = ModelAsset(
                asset_type=ASSET_TYPE_HF_EMBEDDING,
                identifier=repo_id,
                revision=revision,
                local_path=str(local_path),
                status=ModelAssetStatusEnum.READY,
                extra_data={},
            )
            session.add(asset)
        await session.commit()
        await session.refresh(asset)

        return {
            "repo_id": repo_id,
            "revision": revision,
            "available": True,
            "source": "hf_cache",
            "local_path": str(local_path),
            "asset_id": asset.id,
        }
    except Exception:
        # Fallback: check HF hub cache folder directly (works even if hf libs are missing/misconfigured).
        snap_dir = resolve_hf_hub_cached_snapshot_dir(repo_id)
        if snap_dir:
            local_path = str(snap_dir)
            if asset:
                asset.local_path = local_path
                asset.status = ModelAssetStatusEnum.READY
                asset.error_message = None
            else:
                asset = ModelAsset(
                    asset_type=ASSET_TYPE_HF_EMBEDDING,
                    identifier=repo_id,
                    revision=revision,
                    local_path=local_path,
                    status=ModelAssetStatusEnum.READY,
                    extra_data={},
                )
                session.add(asset)
            await session.commit()
            await session.refresh(asset)

            return {
                "repo_id": repo_id,
                "revision": revision,
                "available": True,
                "source": "hf_cache",
                "local_path": local_path,
                "asset_id": asset.id,
            }

        # Not in cache (or hf hub not installed). Treat as unavailable.
        return {
            "repo_id": repo_id,
            "revision": revision,
            "available": False,
            "source": "none",
            "local_path": None,
            "asset_id": asset.id if asset else None,
        }


@router.get(
    "/model-assets/{asset_id}",
    response_model=ModelAssetResponse,
    summary="Get model asset status",
)
async def get_model_asset(
    asset_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(ModelAsset).where(ModelAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset
