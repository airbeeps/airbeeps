"""
ChromaDB vector store adapter for LlamaIndex.

ChromaDB is suitable for local development and small-scale deployments.
"""

import logging
from pathlib import Path
from typing import Any

from llama_index.core.vector_stores.types import BasePydanticVectorStore

from airbeeps.config import settings

logger = logging.getLogger(__name__)


def create_chroma_store(
    collection_name: str,
    **kwargs: Any,
) -> BasePydanticVectorStore:
    """
    Create a ChromaDB vector store instance.

    Args:
        collection_name: Name of the collection
        **kwargs: Additional configuration overrides

    Returns:
        Configured ChromaVectorStore
    """
    from llama_index.vector_stores.chroma import ChromaVectorStore
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    # Determine connection mode
    host = kwargs.get("host", settings.CHROMA_SERVER_HOST)
    port = kwargs.get("port", settings.CHROMA_SERVER_PORT)
    persist_dir = kwargs.get("persist_dir", settings.CHROMA_PERSIST_DIR)

    # Use embedded mode if no host is set
    use_embedded = not host or host in ["", "chromadb"]

    if use_embedded:
        logger.info(f"Using embedded ChromaDB at: {persist_dir}")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        chroma_client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
    else:
        logger.info(f"Connecting to ChromaDB at: {host}:{port}")
        chroma_client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=ChromaSettings(
                anonymized_telemetry=False,
            ),
        )

    # Get or create collection
    chroma_collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    return ChromaVectorStore(
        chroma_collection=chroma_collection,
    )


async def delete_chroma_collection(collection_name: str) -> bool:
    """Delete a ChromaDB collection."""
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        host = settings.CHROMA_SERVER_HOST
        use_embedded = not host or host in ["", "chromadb"]

        if use_embedded:
            chroma_client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            chroma_client = chromadb.HttpClient(
                host=host,
                port=settings.CHROMA_SERVER_PORT,
            )

        chroma_client.delete_collection(collection_name)
        logger.info(f"Deleted ChromaDB collection: {collection_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete ChromaDB collection {collection_name}: {e}")
        return False


async def get_chroma_collection_stats(collection_name: str) -> dict[str, Any]:
    """Get statistics for a ChromaDB collection."""
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        host = settings.CHROMA_SERVER_HOST
        use_embedded = not host or host in ["", "chromadb"]

        if use_embedded:
            chroma_client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            chroma_client = chromadb.HttpClient(
                host=host,
                port=settings.CHROMA_SERVER_PORT,
            )

        collection = chroma_client.get_collection(collection_name)
        return {
            "name": collection_name,
            "count": collection.count(),
        }

    except Exception as e:
        logger.error(f"Failed to get ChromaDB collection stats: {e}")
        return {"name": collection_name, "error": str(e)}
