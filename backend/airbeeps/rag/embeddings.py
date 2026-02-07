"""
LlamaIndex Embedding Service for AirBeeps.

Provides embedding models for vector indexing and retrieval.
Supports multiple providers: OpenAI, HuggingFace, DashScope, and local models.
"""

import asyncio
import hashlib
import logging
import uuid
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from airbeeps.ai_models.hf_assets import ASSET_TYPE_HF_EMBEDDING
from airbeeps.ai_models.models import (
    Model,
    ModelAsset,
    ModelAssetStatusEnum,
    ModelProvider,
    ProviderCategoryEnum,
)
from airbeeps.database import async_session_maker

logger = logging.getLogger(__name__)


def _is_test_mode() -> bool:
    """Check if test mode is enabled."""
    from airbeeps.config import settings

    return settings.TEST_MODE


# =============================================================================
# Fake Embeddings for Test Mode
# =============================================================================


class FakeEmbedding(BaseEmbedding):
    """
    Fake embeddings for test mode.

    Returns deterministic vectors based on text content hash.
    This ensures tests never hit real embedding APIs.
    """

    # Fixed embedding dimension (common for many models)
    EMBEDDING_DIM: int = 384

    model_name: str = "fake-embeddings"

    def __init__(self, model_name: str = "fake-embeddings", **kwargs: Any):
        super().__init__(**kwargs)
        self.model_name = model_name
        logger.info(f"FakeEmbedding created for model: {model_name} (TEST_MODE)")

    @classmethod
    def class_name(cls) -> str:
        return "FakeEmbedding"

    def _text_to_vector(self, text: str) -> list[float]:
        """
        Convert text to a deterministic vector.

        Uses MD5 hash to generate consistent vectors for the same input text.
        """
        # Create a hash of the text (md5 is used for deterministic hashing, not security)
        text_hash = hashlib.md5(text.encode()).hexdigest()  # noqa: S324

        # Convert hash to list of floats (deterministic)
        vector = []
        for i in range(self.EMBEDDING_DIM):
            # Use modulo to cycle through hash characters
            char_idx = i % len(text_hash)
            # Convert hex char to float in range [-1, 1]
            value = (int(text_hash[char_idx], 16) - 7.5) / 7.5
            vector.append(value)

        # Normalize the vector
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def _get_text_embedding(self, text: str) -> list[float]:
        """Get embedding for a single text."""
        return self._text_to_vector(text)

    def _get_query_embedding(self, query: str) -> list[float]:
        """Get embedding for a query."""
        return self._text_to_vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        """Async get embedding for a query."""
        return self._text_to_vector(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        """Async get embedding for a single text."""
        return self._text_to_vector(text)


class EmbeddingService:
    """
    LlamaIndex Embedding Service.

    Provides embedding models for vector indexing and retrieval.
    """

    def __init__(self):
        # Cache initialized embedders to avoid repeated construction
        self._embedder_cache: dict[str, BaseEmbedding] = {}

    async def get_embed_model(self, model_id: str) -> BaseEmbedding:
        """Get LlamaIndex embedding model by model ID."""
        model = await self._get_model_by_id(model_id)
        if not model:
            raise ValueError(f"Model not found: {model_id}")

        if "embedding" not in model.capabilities:
            raise ValueError(f"Model {model.name} does not support embedding")

        return await self._get_embedder_for_model(model)

    async def get_embed_model_with_info(
        self, model_id: str
    ) -> tuple[BaseEmbedding, dict[str, Any]]:
        """Get embedding model along with model info."""
        model = await self._get_model_by_id(model_id)
        if not model:
            raise ValueError(f"Model not found: {model_id}")

        if "embedding" not in model.capabilities:
            raise ValueError(f"Model {model.name} does not support embedding")

        embedder = await self._get_embedder_for_model(model)

        info = {
            "model_id": str(model.id),
            "model_name": model.name,
            "display_name": model.display_name,
            "embed_dim": self._get_embed_dim(model),
        }

        return embedder, info

    def _get_embed_dim(self, model: Model) -> int:
        """Get embedding dimension for a model."""
        # Common embedding dimensions
        dim_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
            "BAAI/bge-large-en-v1.5": 1024,
            "sentence-transformers/all-MiniLM-L6-v2": 384,
            "sentence-transformers/all-mpnet-base-v2": 768,
        }
        return dim_map.get(model.name, 384)

    async def list_available_embedding_models(self) -> list[dict]:
        """Get all available embedding models."""
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(Model)
                    .options(selectinload(Model.provider))
                    .where(Model.status == "ACTIVE")
                )
                result = await session.execute(stmt)
                all_models = result.scalars().all()

                # Filter models with embedding capability
                models = [m for m in all_models if "embedding" in m.capabilities]

                return [
                    {
                        "id": str(model.id),
                        "name": model.name,
                        "display_name": model.display_name,
                        "provider": model.provider.display_name
                        if model.provider
                        else "Unknown",
                        "description": model.description,
                        "max_context_tokens": model.max_context_tokens,
                        "embed_dim": self._get_embed_dim(model),
                    }
                    for model in models
                ]

        except Exception as e:
            logger.error(f"Failed to list embedding models: {e}")
            return []

    async def _get_model_by_id(self, model_id: str) -> Model | None:
        """Get model by ID."""
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(Model)
                    .options(selectinload(Model.provider))
                    .where(Model.id == uuid.UUID(model_id))
                )
                result = await session.execute(stmt)
                return result.scalars().first()
        except Exception as e:
            logger.error(f"Failed to get model {model_id}: {e}")
            return None

    async def _get_embedder_for_model(self, model: Model) -> BaseEmbedding:
        """
        Return LlamaIndex embedding model based on provider config.

        In test mode (AIRBEEPS_TEST_MODE=1), returns a FakeEmbedding instance
        that produces deterministic vectors without making any external API calls.
        """
        # Check for test mode first
        if _is_test_mode():
            cache_key = f"fake:{model.name}"
            if cache_key not in self._embedder_cache:
                logger.info(
                    f"TEST_MODE: Creating FakeEmbedding for model: {model.name}"
                )
                self._embedder_cache[cache_key] = FakeEmbedding(model_name=model.name)
            return self._embedder_cache[cache_key]

        provider = model.provider
        if not provider:
            raise ValueError("Model provider not configured")

        cache_key = f"{provider.id}:{model.name}"
        if cache_key in self._embedder_cache:
            return self._embedder_cache[cache_key]

        hf_local_path: str | None = None
        if provider.category == ProviderCategoryEnum.LOCAL:
            hf_local_path = await self._get_hf_local_path(model.name)

        embedder = await asyncio.to_thread(
            self._create_embedder,
            provider,
            model,
            hf_local_path,
        )

        self._embedder_cache[cache_key] = embedder
        return embedder

    async def _get_hf_local_path(self, repo_id: str) -> str | None:
        """Get local path for HuggingFace model if downloaded."""
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(ModelAsset)
                    .where(ModelAsset.asset_type == ASSET_TYPE_HF_EMBEDDING)
                    .where(ModelAsset.identifier == repo_id)
                    .where(ModelAsset.status == ModelAssetStatusEnum.READY)
                )
                result = await session.execute(stmt)
                asset = result.scalars().first()
                if asset and asset.local_path:
                    return asset.local_path
        except Exception as e:
            logger.debug(f"Failed to resolve HF local path for {repo_id}: {e}")
        return None

    def _create_embedder(
        self,
        provider: ModelProvider,
        model: Model,
        hf_local_path: str | None = None,
    ) -> BaseEmbedding:
        """Construct LlamaIndex embedding model instance."""
        category = provider.category

        # OpenAI-compatible providers
        if category == ProviderCategoryEnum.OPENAI_COMPATIBLE or (
            category == ProviderCategoryEnum.CUSTOM and provider.is_openai_compatible
        ):
            from llama_index.embeddings.openai import OpenAIEmbedding

            kwargs: dict[str, Any] = {"model": model.name}
            if provider.api_key:
                kwargs["api_key"] = provider.api_key
            if provider.api_base_url:
                kwargs["api_base"] = provider.api_base_url

            return OpenAIEmbedding(**kwargs)

        # Provider-specific implementations
        if category == ProviderCategoryEnum.PROVIDER_SPECIFIC:
            # DashScope (Alibaba)
            if provider.litellm_provider == "dashscope":
                from llama_index.embeddings.dashscope import DashScopeEmbedding

                kwargs = {"model_name": model.name}
                if provider.api_key:
                    kwargs["api_key"] = provider.api_key
                return DashScopeEmbedding(**kwargs)

            raise NotImplementedError(
                f"Provider-specific embeddings not yet implemented for: {provider.litellm_provider}"
            )

        # Local models (HuggingFace)
        if category == ProviderCategoryEnum.LOCAL:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            model_name = hf_local_path or model.name
            return HuggingFaceEmbedding(
                model_name=model_name,
                device="cpu",
                normalize=True,
            )

        raise NotImplementedError(
            f"Unsupported provider category for embeddings: {category}"
        )

    def clear_cache(self) -> None:
        """Clear the embedder cache."""
        self._embedder_cache.clear()
        logger.debug("Cleared embedding service cache")


# Global singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
