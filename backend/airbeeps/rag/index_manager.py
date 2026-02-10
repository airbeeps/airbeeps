"""
Index Manager for LlamaIndex.

Manages VectorStoreIndex instances per knowledge base.
Handles index creation, document insertion, and retrieval setup.
"""

import logging
import uuid
from typing import Any

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.schema import BaseNode, Document

from .embeddings import EmbeddingService, get_embedding_service
from .stores import VectorStoreFactory, VectorStoreType, get_vector_store
from .stores.base import collection_name_for_kb

logger = logging.getLogger(__name__)


class IndexManager:
    """
    Manages LlamaIndex VectorStoreIndex per knowledge base.

    Provides:
    - Index creation and caching
    - Document/node insertion
    - Retriever configuration
    - Storage context management for hierarchical retrieval
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
    ):
        """
        Initialize the index manager.

        Args:
            embedding_service: Optional embedding service (uses global if not provided)
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self._index_cache: dict[str, VectorStoreIndex] = {}
        self._storage_context_cache: dict[str, StorageContext] = {}

    async def get_index(
        self,
        kb_id: uuid.UUID,
        embed_model: BaseEmbedding | None = None,
        embedding_model_id: str | None = None,
        store_type: VectorStoreType | str | None = None,
        embed_dim: int = 384,
    ) -> VectorStoreIndex:
        """
        Get or create a VectorStoreIndex for a knowledge base.

        Args:
            kb_id: Knowledge base UUID
            embed_model: Optional embedding model (fetched from embedding_model_id if not provided)
            embedding_model_id: Model ID to fetch embeddings from
            store_type: Vector store type (defaults to settings)
            embed_dim: Embedding dimension

        Returns:
            Configured VectorStoreIndex
        """
        cache_key = str(kb_id)

        # Return cached index if available
        if cache_key in self._index_cache:
            return self._index_cache[cache_key]

        # Get embedding model if not provided
        if embed_model is None and embedding_model_id:
            embed_model, info = await self.embedding_service.get_embed_model_with_info(
                embedding_model_id
            )
            embed_dim = info.get("embed_dim", embed_dim)

        # Get or create vector store
        collection_name = collection_name_for_kb(str(kb_id))
        vector_store = get_vector_store(
            collection_name=collection_name,
            store_type=store_type,
            embed_dim=embed_dim,
        )

        # Create storage context with persistent docstore
        from pathlib import Path

        from llama_index.core.storage.docstore import SimpleDocumentStore

        from airbeeps.config import BASE_DIR, settings as app_settings

        # Use persistent docstore directory
        docstore_dir = Path(app_settings.DATA_ROOT) / "docstore"
        if not docstore_dir.is_absolute():
            docstore_dir = BASE_DIR / docstore_dir
        docstore_dir.mkdir(parents=True, exist_ok=True)

        docstore_path = docstore_dir / f"{kb_id}.json"

        # Load or create docstore
        try:
            docstore = SimpleDocumentStore.from_persist_path(str(docstore_path))
        except Exception:
            docstore = SimpleDocumentStore()

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store, docstore=docstore
        )
        self._storage_context_cache[cache_key] = storage_context

        # Create index
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context,
            embed_model=embed_model,
        )

        self._index_cache[cache_key] = index
        logger.info(f"Created index for knowledge base: {kb_id}")

        return index

    async def add_nodes(
        self,
        kb_id: uuid.UUID,
        nodes: list[BaseNode],
        embed_model: BaseEmbedding | None = None,
        embedding_model_id: str | None = None,
        store_type: VectorStoreType | str | None = None,
        embed_dim: int = 384,
    ) -> int:
        """
        Add nodes to a knowledge base index.

        Args:
            kb_id: Knowledge base UUID
            nodes: List of nodes to add
            embed_model: Optional embedding model
            embedding_model_id: Model ID for embeddings
            store_type: Vector store type
            embed_dim: Embedding dimension

        Returns:
            Number of nodes added
        """
        if not nodes:
            return 0

        index = await self.get_index(
            kb_id=kb_id,
            embed_model=embed_model,
            embedding_model_id=embedding_model_id,
            store_type=store_type,
            embed_dim=embed_dim,
        )

        # Insert nodes
        index.insert_nodes(nodes)

        # Persist docstore for BM25/hybrid retrieval
        await self._persist_docstore(kb_id)

        logger.info(f"Added {len(nodes)} nodes to knowledge base {kb_id}")

        return len(nodes)

    async def add_documents(
        self,
        kb_id: uuid.UUID,
        documents: list[Document],
        embed_model: BaseEmbedding | None = None,
        embedding_model_id: str | None = None,
        store_type: VectorStoreType | str | None = None,
        embed_dim: int = 384,
    ) -> int:
        """
        Add LlamaIndex documents to a knowledge base.

        Documents will be processed into nodes using the index's transformations.

        Args:
            kb_id: Knowledge base UUID
            documents: List of LlamaIndex Documents
            embed_model: Optional embedding model
            embedding_model_id: Model ID for embeddings
            store_type: Vector store type
            embed_dim: Embedding dimension

        Returns:
            Number of documents processed
        """
        if not documents:
            return 0

        index = await self.get_index(
            kb_id=kb_id,
            embed_model=embed_model,
            embedding_model_id=embedding_model_id,
            store_type=store_type,
            embed_dim=embed_dim,
        )

        # Insert documents (will be chunked by index transformations)
        for doc in documents:
            index.insert(doc)

        logger.info(f"Added {len(documents)} documents to knowledge base {kb_id}")
        return len(documents)

    async def delete_nodes(
        self,
        kb_id: uuid.UUID,
        node_ids: list[str],
        store_type: VectorStoreType | str | None = None,
    ) -> int:
        """
        Delete nodes from a knowledge base by their IDs.

        Args:
            kb_id: Knowledge base UUID
            node_ids: List of node IDs to delete
            store_type: Vector store type

        Returns:
            Number of nodes deleted
        """
        if not node_ids:
            return 0

        collection_name = collection_name_for_kb(str(kb_id))
        vector_store = get_vector_store(
            collection_name=collection_name,
            store_type=store_type,
        )

        # Delete from vector store
        for node_id in node_ids:
            try:
                vector_store.delete(node_id)
            except Exception as e:
                logger.warning(f"Failed to delete node {node_id}: {e}")

        # Clear cache since index state changed
        self._clear_kb_cache(kb_id)

        logger.info(f"Deleted {len(node_ids)} nodes from knowledge base {kb_id}")
        return len(node_ids)

    async def delete_collection(
        self,
        kb_id: uuid.UUID,
        store_type: VectorStoreType | str | None = None,
    ) -> bool:
        """
        Delete the entire vector collection for a knowledge base.

        Args:
            kb_id: Knowledge base UUID
            store_type: Vector store type

        Returns:
            True if successful
        """
        store_type = store_type or VectorStoreFactory.get_default_type()
        if isinstance(store_type, str):
            store_type = VectorStoreType(store_type)

        collection_name = collection_name_for_kb(str(kb_id))

        try:
            if store_type == VectorStoreType.QDRANT:
                from .stores.qdrant import delete_qdrant_collection

                await delete_qdrant_collection(collection_name)

            elif store_type == VectorStoreType.CHROMADB:
                from .stores.chroma import delete_chroma_collection

                await delete_chroma_collection(collection_name)

            elif store_type == VectorStoreType.PGVECTOR:
                from .stores.pgvector import delete_pgvector_collection

                await delete_pgvector_collection(collection_name)

            elif store_type == VectorStoreType.MILVUS:
                from .stores.milvus import delete_milvus_collection

                await delete_milvus_collection(collection_name)

            # Clear caches
            self._clear_kb_cache(kb_id)
            VectorStoreFactory.remove_from_cache(store_type, collection_name)

            # Delete docstore file
            try:
                from pathlib import Path

                from airbeeps.config import BASE_DIR, settings as app_settings

                docstore_dir = Path(app_settings.DATA_ROOT) / "docstore"
                if not docstore_dir.is_absolute():
                    docstore_dir = BASE_DIR / docstore_dir
                docstore_path = docstore_dir / f"{kb_id}.json"
                if docstore_path.exists():
                    docstore_path.unlink()
                    logger.info(f"Deleted docstore file for KB {kb_id}")
            except Exception as e:
                logger.warning(f"Failed to delete docstore file: {e}")

            logger.info(f"Deleted collection for knowledge base {kb_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete collection for KB {kb_id}: {e}")
            return False

    async def get_collection_stats(
        self,
        kb_id: uuid.UUID,
        store_type: VectorStoreType | str | None = None,
    ) -> dict[str, Any]:
        """
        Get statistics for a knowledge base's vector collection.

        Args:
            kb_id: Knowledge base UUID
            store_type: Vector store type

        Returns:
            Collection statistics dict
        """
        store_type = store_type or VectorStoreFactory.get_default_type()
        if isinstance(store_type, str):
            store_type = VectorStoreType(store_type)

        collection_name = collection_name_for_kb(str(kb_id))

        try:
            if store_type == VectorStoreType.QDRANT:
                from .stores.qdrant import get_qdrant_collection_stats

                return await get_qdrant_collection_stats(collection_name)

            if store_type == VectorStoreType.CHROMADB:
                from .stores.chroma import get_chroma_collection_stats

                return await get_chroma_collection_stats(collection_name)

            if store_type == VectorStoreType.PGVECTOR:
                from .stores.pgvector import get_pgvector_collection_stats

                return await get_pgvector_collection_stats(collection_name)

            if store_type == VectorStoreType.MILVUS:
                from .stores.milvus import get_milvus_collection_stats

                return await get_milvus_collection_stats(collection_name)

            return {"name": collection_name, "error": "Unknown store type"}

        except Exception as e:
            logger.error(f"Failed to get collection stats for KB {kb_id}: {e}")
            return {"name": collection_name, "error": str(e)}

    def get_storage_context(self, kb_id: uuid.UUID) -> StorageContext | None:
        """
        Get the storage context for a knowledge base.

        Required for AutoMergingRetriever with hierarchical chunks.

        Args:
            kb_id: Knowledge base UUID

        Returns:
            StorageContext if available, None otherwise
        """
        return self._storage_context_cache.get(str(kb_id))

    def _clear_kb_cache(self, kb_id: uuid.UUID) -> None:
        """Clear cached index and storage context for a KB."""
        cache_key = str(kb_id)
        self._index_cache.pop(cache_key, None)
        self._storage_context_cache.pop(cache_key, None)

    def clear_all_caches(self) -> None:
        """Clear all cached indices and storage contexts."""
        self._index_cache.clear()
        self._storage_context_cache.clear()
        logger.debug("Cleared all index manager caches")

    async def _persist_docstore(self, kb_id: uuid.UUID) -> None:
        """Persist docstore to disk for BM25/hybrid retrieval."""
        try:
            from pathlib import Path

            from airbeeps.config import BASE_DIR, settings as app_settings

            storage_context = self._storage_context_cache.get(str(kb_id))
            if not storage_context:
                return

            docstore_dir = Path(app_settings.DATA_ROOT) / "docstore"
            if not docstore_dir.is_absolute():
                docstore_dir = BASE_DIR / docstore_dir
            docstore_dir.mkdir(parents=True, exist_ok=True)

            docstore_path = docstore_dir / f"{kb_id}.json"
            storage_context.docstore.persist(str(docstore_path))
            logger.debug(f"Persisted docstore for KB {kb_id}")
        except Exception as e:
            logger.warning(f"Failed to persist docstore for KB {kb_id}: {e}")


# Global singleton instance
_index_manager: IndexManager | None = None


def get_index_manager() -> IndexManager:
    """Get the global index manager instance."""
    global _index_manager
    if _index_manager is None:
        _index_manager = IndexManager()
    return _index_manager
