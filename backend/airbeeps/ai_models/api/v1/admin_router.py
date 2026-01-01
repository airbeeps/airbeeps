import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.ai_models.catalog import (
    get_provider_template,
    list_model_templates,
    list_provider_templates,
)
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
    ModelTemplateResponse,
    ModelUpdate,
    ProviderStatusEnum,
    ProviderTemplateDetailResponse,
    ProviderTemplateResponse,
)

router = APIRouter()


# ============================================================================
# Catalog (templates)
# ============================================================================


@router.get(
    "/provider-templates",
    response_model=list[ProviderTemplateResponse],
    summary="List built-in provider templates",
)
async def list_provider_template_options():
    return list_provider_templates()


@router.get(
    "/provider-templates/{template_id}",
    response_model=ProviderTemplateDetailResponse,
    summary="Get provider template detail (includes recommended models)",
)
async def get_provider_template_detail(template_id: str):
    tpl = get_provider_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Provider template not found")
    # Normalize into response shape
    base = {
        "id": tpl.get("id"),
        "display_name": tpl.get("display_name"),
        "description": tpl.get("description"),
        "website": tpl.get("website"),
        "api_base_url": tpl.get("api_base_url"),
        "interface_type": tpl.get("interface_type"),
        "litellm_provider": tpl.get("litellm_provider"),
        "models": tpl.get("models", []) or [],
    }
    return base


def _guess_provider_template_id(provider: ModelProvider) -> str | None:
    if getattr(provider, "template_id", None):
        return provider.template_id
    # Legacy/local providers: map by interface type when appropriate
    if provider.interface_type == "HUGGINGFACE":
        return "huggingface_local"
    name = (provider.name or "").strip().lower()
    if name:
        # Common fallback: match provider.name to template id
        return name
    return None


@router.get(
    "/providers/{provider_id}/model-suggestions",
    response_model=list[ModelTemplateResponse],
    summary="List model template suggestions for a provider instance",
)
async def list_model_suggestions(
    provider_id: uuid.UUID,
    capability: str | None = Query(None, description="Filter by capability"),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    template_id = _guess_provider_template_id(provider)
    if not template_id:
        return []

    models = list_model_templates(template_id) or []
    if capability:
        models = [m for m in models if capability in (m.get("capabilities") or [])]
    # Ensure provider_template_id is set for downstream UI grouping
    out: list[dict[str, Any]] = []
    for m in models:
        out.append({**m, "provider_template_id": template_id})
    return out


# ============================================================================
# Provider utilities (test/discover)
# ============================================================================


def _is_test_mode() -> bool:
    """Check if test mode is enabled."""
    from airbeeps.config import settings

    return settings.TEST_MODE


@router.post(
    "/providers/{provider_id}/test-connection",
    summary="Test provider connectivity/auth (best-effort)",
)
async def test_provider_connection(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    # Short-circuit in test mode: return mock success without any external calls
    if _is_test_mode():
        return {"ok": True, "message": "TEST_MODE: Connection test skipped"}

    import httpx

    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Local HF embeddings: nothing to call
    if provider.interface_type == "HUGGINGFACE":
        return {"ok": True, "message": "Local HuggingFace embeddings provider"}

    if not provider.api_base_url:
        raise HTTPException(status_code=400, detail="API base URL is required")

    # Best-effort: OpenAI-compatible /models endpoint
    url = provider.api_base_url.rstrip("/") + "/models"
    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            # Provide user-friendly error messages based on status code
            error_msg = ""
            if resp.status_code == 401:
                error_msg = "Unauthorized. Please check your API key."
            elif resp.status_code == 403:
                error_msg = "Forbidden. API key may lack required permissions."
            elif resp.status_code == 404:
                error_msg = "API endpoint not found. Please verify the base URL."
            elif resp.status_code == 429:
                error_msg = "Rate limit exceeded. Please try again later."
            elif resp.status_code >= 500:
                error_msg = f"Provider server error ({resp.status_code}). Please try again later."
            else:
                error_msg = f"Connection failed with status {resp.status_code}."

            return {
                "ok": False,
                "status_code": resp.status_code,
                "message": error_msg,
                "detail": resp.text[:500],
            }
        return {"ok": True, "status_code": resp.status_code}
    except Exception as e:
        return {"ok": False, "message": f"Connection error: {str(e)}"}


@router.get(
    "/providers/{provider_id}/discover-models",
    summary="Discover available models from provider (OpenAI-compatible only)",
)
async def discover_models_from_provider(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    # Short-circuit in test mode: return mock model list without any external calls
    if _is_test_mode():
        return ["test-model-1", "test-model-2", "test-model-gpt-4"]

    import httpx

    result = await session.execute(
        select(ModelProvider).where(ModelProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not provider.api_base_url:
        raise HTTPException(status_code=400, detail="API base URL is required")

    if provider.interface_type not in ("OPENAI", "XAI"):
        raise HTTPException(
            status_code=400,
            detail="Model discovery is currently supported for OpenAI-compatible providers only",
        )

    url = provider.api_base_url.rstrip("/") + "/models"
    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code >= 400:
            # Provide user-friendly error messages based on status code
            error_msg = ""
            if resp.status_code == 401:
                error_msg = "Unauthorized. Please check your API key."
            elif resp.status_code == 403:
                error_msg = "Forbidden. API key may lack required permissions."
            elif resp.status_code == 404:
                error_msg = "API endpoint not found. Please verify the base URL."
            elif resp.status_code == 429:
                error_msg = "Rate limit exceeded. Please try again later."
            elif resp.status_code >= 500:
                error_msg = f"Provider server error ({resp.status_code}). Please try again later."
            else:
                error_msg = f"Request failed with status {resp.status_code}."
            raise HTTPException(status_code=resp.status_code, detail=error_msg)

        payload = resp.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        # Return sorted ids
        ids = []
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
        return sorted(set(ids))
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


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
