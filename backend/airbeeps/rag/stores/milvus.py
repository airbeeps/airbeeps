"""
Milvus vector store adapter for LlamaIndex.

Milvus is suitable for enterprise-scale deployments with billions of vectors.
"""

import logging
from typing import Any

from llama_index.core.vector_stores.types import BasePydanticVectorStore

from airbeeps.config import settings

logger = logging.getLogger(__name__)


def create_milvus_store(
    collection_name: str,
    embed_dim: int = 384,
    **kwargs: Any,
) -> BasePydanticVectorStore:
    """
    Create a Milvus vector store instance.

    Args:
        collection_name: Name of the collection
        embed_dim: Embedding dimension
        **kwargs: Additional configuration overrides

    Returns:
        Configured MilvusVectorStore
    """
    from llama_index.vector_stores.milvus import MilvusVectorStore

    uri = kwargs.get("uri", settings.MILVUS_URI)
    token = kwargs.get("token", settings.MILVUS_TOKEN)
    db_name = kwargs.get("db_name", settings.MILVUS_DB_NAME)

    logger.info(f"Connecting to Milvus at: {uri}")

    return MilvusVectorStore(
        uri=uri,
        token=token if token else None,
        collection_name=collection_name,
        dim=embed_dim,
        db_name=db_name,
        # Index parameters for better performance
        index_config={
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 128},
        },
        search_config={
            "metric_type": "COSINE",
            "params": {"nprobe": 10},
        },
        # Enable hybrid search if configured
        enable_sparse=kwargs.get("enable_sparse", settings.RAG_ENABLE_HYBRID_SEARCH),
        hybrid_ranker=kwargs.get("hybrid_ranker", "RRFRanker"),
        hybrid_ranker_params=kwargs.get("hybrid_ranker_params", {"k": 60}),
    )


async def delete_milvus_collection(collection_name: str) -> bool:
    """Delete a Milvus collection."""
    try:
        from pymilvus import MilvusClient

        client = MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN if settings.MILVUS_TOKEN else None,
            db_name=settings.MILVUS_DB_NAME,
        )

        client.drop_collection(collection_name)
        logger.info(f"Deleted Milvus collection: {collection_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete Milvus collection {collection_name}: {e}")
        return False


async def get_milvus_collection_stats(collection_name: str) -> dict[str, Any]:
    """Get statistics for a Milvus collection."""
    try:
        from pymilvus import MilvusClient

        client = MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN if settings.MILVUS_TOKEN else None,
            db_name=settings.MILVUS_DB_NAME,
        )

        # Get collection info
        stats = client.get_collection_stats(collection_name)
        return {
            "name": collection_name,
            "row_count": stats.get("row_count", 0),
        }

    except Exception as e:
        logger.error(f"Failed to get Milvus collection stats: {e}")
        return {"name": collection_name, "error": str(e)}


async def list_milvus_collections() -> list[str]:
    """List all Milvus collections."""
    try:
        from pymilvus import MilvusClient

        client = MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN if settings.MILVUS_TOKEN else None,
            db_name=settings.MILVUS_DB_NAME,
        )

        return client.list_collections()

    except Exception as e:
        logger.error(f"Failed to list Milvus collections: {e}")
        return []
