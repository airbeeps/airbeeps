import asyncio
import hashlib
import logging
import uuid

from langchain_core.embeddings import Embeddings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from airbeeps.ai_models.hf_assets import ASSET_TYPE_HF_EMBEDDING
from airbeeps.ai_models.models import (
    PROVIDER_INTERFACE_TYPES,
    Model,
    ModelAsset,
    ModelAssetStatusEnum,
    ModelProvider,
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


class FakeEmbeddings(Embeddings):
    """
    Fake embeddings for test mode.

    Returns deterministic vectors based on text content hash.
    This ensures tests never hit real embedding APIs.
    """

    # Fixed embedding dimension (common for many models)
    EMBEDDING_DIM = 384

    def __init__(self, model_name: str = "fake-embeddings"):
        self.model_name = model_name
        logger.info(f"FakeEmbeddings created for model: {model_name} (TEST_MODE)")

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

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents."""
        logger.debug(f"FakeEmbeddings.embed_documents called with {len(texts)} texts")
        return [self._text_to_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query string."""
        logger.debug("FakeEmbeddings.embed_query called")
        return self._text_to_vector(text)


class EmbeddingService:
    """Vector Embedding Service - Provides LangChain Embeddings instances based on model info"""

    def __init__(self):
        # Cache initialized embedders to avoid repeated construction
        self._embedder_cache: dict[str, Embeddings] = {}

    async def get_embedder(self, model_id: str) -> Embeddings:
        """Get LangChain Embeddings instance by model ID"""
        model = await self._get_model_by_id(model_id)
        if not model:
            raise ValueError(f"Model not found: {model_id}")

        if "embedding" not in model.capabilities:
            raise ValueError(f"Model {model.name} does not support embedding")

        return await self._get_embedder_for_model(model)

    async def list_available_embedding_models(self) -> list[dict]:
        """Get all available embedding models"""
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(Model)
                    .options(selectinload(Model.provider))
                    .where(Model.status == "ACTIVE")
                )
                result = await session.execute(stmt)
                all_models = result.scalars().all()

                # Filter models with embedding capability at Python level for database compatibility
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
                    }
                    for model in models
                ]

        except Exception as e:
            logger.error(f"Failed to list embedding models: {e}")
            return []

    async def _get_model_by_id(self, model_id: str) -> Model | None:
        """Get model by ID"""
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

    async def _get_embedder_for_model(self, model: Model) -> Embeddings:
        """Return LangChain embedder instance based on model provider config.

        In test mode (AIRBEEPS_TEST_MODE=1), returns a FakeEmbeddings instance
        that produces deterministic vectors without making any external API calls.
        """
        # Check for test mode first - return fake embeddings without any external setup
        if _is_test_mode():
            cache_key = f"fake:{model.name}"
            if cache_key not in self._embedder_cache:
                logger.info(
                    f"TEST_MODE: Creating FakeEmbeddings for model: {model.name}"
                )
                self._embedder_cache[cache_key] = FakeEmbeddings(model_name=model.name)
            return self._embedder_cache[cache_key]

        provider = model.provider
        if not provider:
            raise ValueError("Model provider not configured")

        cache_key = f"{provider.id}:{model.name}"
        if cache_key in self._embedder_cache:
            return self._embedder_cache[cache_key]

        hf_local_path: str | None = None
        if provider.interface_type == PROVIDER_INTERFACE_TYPES["HUGGINGFACE"]:
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
    ) -> Embeddings:
        """Construct concrete embedder instance"""
        interface_type = provider.interface_type

        if interface_type == PROVIDER_INTERFACE_TYPES["OPENAI"]:
            from langchain_openai import OpenAIEmbeddings

            kwargs = {"model": model.name}
            if provider.api_key:
                kwargs["openai_api_key"] = provider.api_key
            if provider.api_base_url:
                kwargs["openai_api_base"] = provider.api_base_url

            return OpenAIEmbeddings(**kwargs)
        if interface_type == PROVIDER_INTERFACE_TYPES["DASHSCOPE"]:
            from langchain_community.embeddings import DashScopeEmbeddings

            kwargs = {"model": model.name}
            if provider.api_key:
                kwargs["dashscope_api_key"] = provider.api_key
            return DashScopeEmbeddings(**kwargs)
        if interface_type == PROVIDER_INTERFACE_TYPES["HUGGINGFACE"]:
            from langchain_huggingface import HuggingFaceEmbeddings

            # Default to CPU; sentence-transformers must be installed
            model_name = hf_local_path or model.name
            return HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        raise NotImplementedError(
            f"Unsupported provider interface for embeddings: {interface_type}"
        )
