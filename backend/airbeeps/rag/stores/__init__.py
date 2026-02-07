"""
Vector Store Factory and Adapters for LlamaIndex.

Provides a unified interface for multiple vector store backends:
- Qdrant (recommended for production)
- ChromaDB (local development)
- PGVector (PostgreSQL-based)
- Milvus (enterprise scale)
"""

import logging
from enum import Enum
from typing import Any

from llama_index.core.vector_stores.types import BasePydanticVectorStore

from airbeeps.config import settings

logger = logging.getLogger(__name__)


class VectorStoreType(str, Enum):
    """Supported vector store backends."""

    QDRANT = "qdrant"
    CHROMADB = "chromadb"
    PGVECTOR = "pgvector"
    MILVUS = "milvus"


class VectorStoreFactory:
    """Factory for creating vector store instances."""

    _instances: dict[str, BasePydanticVectorStore] = {}

    @classmethod
    def create(
        cls,
        store_type: VectorStoreType | str,
        collection_name: str,
        embed_dim: int = 384,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> BasePydanticVectorStore:
        """
        Create or retrieve a cached vector store instance.

        Args:
            store_type: Type of vector store to create
            collection_name: Name of the collection/index
            embed_dim: Embedding dimension (required for some stores)
            use_cache: Whether to cache and reuse instances
            **kwargs: Additional store-specific configuration

        Returns:
            Configured vector store instance
        """
        if isinstance(store_type, str):
            store_type = VectorStoreType(store_type)

        cache_key = f"{store_type.value}:{collection_name}"

        if use_cache and cache_key in cls._instances:
            logger.debug(f"Returning cached vector store: {cache_key}")
            return cls._instances[cache_key]

        logger.info(f"Creating vector store: {store_type.value} for {collection_name}")

        if store_type == VectorStoreType.QDRANT:
            from .qdrant import create_qdrant_store

            store = create_qdrant_store(collection_name, embed_dim, **kwargs)

        elif store_type == VectorStoreType.CHROMADB:
            from .chroma import create_chroma_store

            store = create_chroma_store(collection_name, **kwargs)

        elif store_type == VectorStoreType.PGVECTOR:
            from .pgvector import create_pgvector_store

            store = create_pgvector_store(collection_name, embed_dim, **kwargs)

        elif store_type == VectorStoreType.MILVUS:
            from .milvus import create_milvus_store

            store = create_milvus_store(collection_name, embed_dim, **kwargs)

        else:
            raise ValueError(f"Unsupported vector store type: {store_type}")

        if use_cache:
            cls._instances[cache_key] = store

        return store

    @classmethod
    def get_default_type(cls) -> VectorStoreType:
        """Get the default vector store type from settings."""
        return VectorStoreType(settings.VECTOR_STORE_TYPE)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached vector store instances."""
        cls._instances.clear()
        logger.debug("Cleared vector store cache")

    @classmethod
    def remove_from_cache(
        cls, store_type: VectorStoreType, collection_name: str
    ) -> None:
        """Remove a specific store from cache."""
        cache_key = f"{store_type.value}:{collection_name}"
        cls._instances.pop(cache_key, None)


def get_vector_store(
    collection_name: str,
    store_type: VectorStoreType | str | None = None,
    embed_dim: int = 384,
    **kwargs: Any,
) -> BasePydanticVectorStore:
    """
    Convenience function to get a vector store with default settings.

    Args:
        collection_name: Name of the collection
        store_type: Type of store (defaults to settings.VECTOR_STORE_TYPE)
        embed_dim: Embedding dimension
        **kwargs: Additional configuration

    Returns:
        Configured vector store instance
    """
    if store_type is None:
        store_type = VectorStoreFactory.get_default_type()

    return VectorStoreFactory.create(
        store_type=store_type,
        collection_name=collection_name,
        embed_dim=embed_dim,
        **kwargs,
    )


__all__ = [
    "VectorStoreType",
    "VectorStoreFactory",
    "get_vector_store",
]
