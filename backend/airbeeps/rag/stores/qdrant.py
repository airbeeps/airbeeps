"""
Qdrant vector store adapter for LlamaIndex.

Qdrant is the recommended production vector store for AirBeeps due to:
- Excellent performance and scalability
- Native hybrid search support
- Rich filtering capabilities
- Both cloud and self-hosted options
"""

import logging
from typing import Any

from llama_index.core.vector_stores.types import BasePydanticVectorStore
from qdrant_client import QdrantClient, models

from airbeeps.config import settings

logger = logging.getLogger(__name__)


def create_qdrant_store(
    collection_name: str,
    embed_dim: int = 384,
    **kwargs: Any,
) -> BasePydanticVectorStore:
    """
    Create a Qdrant vector store instance.

    Args:
        collection_name: Name of the collection
        embed_dim: Embedding dimension
        **kwargs: Additional configuration overrides

    Returns:
        Configured QdrantVectorStore
    """
    from llama_index.vector_stores.qdrant import QdrantVectorStore

    # Determine if using local file storage or remote server
    url = kwargs.get("url", settings.QDRANT_URL)
    api_key = kwargs.get("api_key", settings.QDRANT_API_KEY)
    prefer_grpc = kwargs.get("prefer_grpc", settings.QDRANT_PREFER_GRPC)

    # If no URL or localhost, use local file storage
    use_local = not url or url in ["", "localhost", "http://localhost:6333"]

    if use_local:
        # Use local file-based storage
        from pathlib import Path

        from airbeeps.config import BASE_DIR, settings as app_settings

        persist_dir = Path(app_settings.DATA_ROOT) / settings.QDRANT_PERSIST_DIR
        if not persist_dir.is_absolute():
            persist_dir = BASE_DIR / persist_dir
        persist_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Using local Qdrant storage at: {persist_dir}")
        client = QdrantClient(path=str(persist_dir))
    else:
        logger.info(f"Connecting to Qdrant at: {url}")
        client = QdrantClient(
            url=url,
            api_key=api_key if api_key else None,
            prefer_grpc=prefer_grpc,
        )

    # Ensure collection exists with proper configuration
    _ensure_collection(client, collection_name, embed_dim)

    return QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        enable_hybrid=kwargs.get("enable_hybrid", settings.RAG_ENABLE_HYBRID_SEARCH),
        fastembed_sparse_model=kwargs.get("sparse_model", "Qdrant/bm25"),
    )


def _ensure_collection(
    client: QdrantClient,
    collection_name: str,
    embed_dim: int,
) -> None:
    """Ensure collection exists with proper configuration."""
    try:
        collections = client.get_collections().collections
        existing_names = [c.name for c in collections]

        if collection_name not in existing_names:
            logger.info(f"Creating Qdrant collection: {collection_name}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embed_dim,
                    distance=models.Distance.COSINE,
                ),
                # Enable sparse vectors for hybrid search
                sparse_vectors_config={
                    "text-sparse": models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    )
                },
            )
        else:
            logger.debug(f"Collection {collection_name} already exists")

    except Exception as e:
        logger.error(f"Failed to ensure Qdrant collection: {e}")
        raise


async def delete_qdrant_collection(collection_name: str) -> bool:
    """Delete a Qdrant collection."""
    try:
        from pathlib import Path

        from airbeeps.config import BASE_DIR, settings as app_settings

        url = settings.QDRANT_URL
        use_local = not url or url in ["", "localhost", "http://localhost:6333"]

        if use_local:
            persist_dir = Path(app_settings.DATA_ROOT) / settings.QDRANT_PERSIST_DIR
            if not persist_dir.is_absolute():
                persist_dir = BASE_DIR / persist_dir
            persist_dir.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=str(persist_dir))
        else:
            client = QdrantClient(
                url=url,
                api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
            )

        client.delete_collection(collection_name)
        logger.info(f"Deleted Qdrant collection: {collection_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete Qdrant collection {collection_name}: {e}")
        return False


async def get_qdrant_collection_stats(collection_name: str) -> dict[str, Any]:
    """Get statistics for a Qdrant collection."""
    try:
        from pathlib import Path

        from airbeeps.config import BASE_DIR, settings as app_settings

        url = settings.QDRANT_URL
        use_local = not url or url in ["", "localhost", "http://localhost:6333"]

        if use_local:
            persist_dir = Path(app_settings.DATA_ROOT) / settings.QDRANT_PERSIST_DIR
            if not persist_dir.is_absolute():
                persist_dir = BASE_DIR / persist_dir
            persist_dir.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=str(persist_dir))
        else:
            client = QdrantClient(
                url=url,
                api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
            )

        info = client.get_collection(collection_name)
        return {
            "name": collection_name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status.value,
            "optimizer_status": info.optimizer_status.status.value
            if info.optimizer_status
            else None,
        }

    except Exception as e:
        logger.error(f"Failed to get Qdrant collection stats: {e}")
        return {"name": collection_name, "error": str(e)}
