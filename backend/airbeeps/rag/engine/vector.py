"""
Vector Engine: Traditional vector similarity search using Chroma.

This is the default RAG engine that wraps the existing ChromaVectorStore
implementation in the BaseRAGEngine interface.
"""

import logging
from typing import Any

from langchain_core.documents import Document as VectorDocument

from airbeeps.rag.vector_store import ChromaVectorStore

from .base import BaseRAGEngine, EngineType, RetrievalResult

logger = logging.getLogger(__name__)


class VectorEngine(BaseRAGEngine):
    """
    Vector-based RAG engine using ChromaDB.

    Provides traditional vector similarity search with optional
    MMR (Maximal Marginal Relevance) for result diversity.
    """

    engine_type = EngineType.VECTOR

    def __init__(self, chroma_store: ChromaVectorStore | None = None):
        """
        Initialize the vector engine.

        Args:
            chroma_store: Optional existing ChromaVectorStore instance.
                         Creates a new one if not provided.
        """
        self._store = chroma_store or ChromaVectorStore()

    async def index_documents(
        self,
        collection_name: str,
        documents: list[VectorDocument],
        embedding_function: Any,
        **kwargs,
    ) -> int:
        """Add documents to the Chroma collection."""
        if not documents:
            return 0

        await self._store.add_documents(
            collection_name=collection_name,
            documents=documents,
            embedding_function=embedding_function,
        )

        logger.debug(f"Indexed {len(documents)} documents to {collection_name}")
        return len(documents)

    async def delete_documents(
        self,
        collection_name: str,
        document_ids: list[str],
        **kwargs,
    ) -> int:
        """Delete documents from the Chroma collection."""
        if not document_ids:
            return 0

        await self._store.delete_documents(
            collection_name=collection_name,
            ids=document_ids,
        )

        logger.debug(f"Deleted {len(document_ids)} documents from {collection_name}")
        return len(document_ids)

    async def retrieve(
        self,
        collection_name: str,
        query: str,
        embedding_function: Any,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
        filter_metadata: dict[str, Any] | None = None,
        search_type: str = "similarity",
        fetch_k: int | None = None,
        mmr_lambda: float = 0.5,
        **kwargs,
    ) -> list[RetrievalResult]:
        """
        Retrieve relevant documents using vector similarity.

        Supports both standard similarity search and MMR for diversity.
        """
        # Use the existing ChromaVectorStore wrapper API.
        # Note: ChromaVectorStore.search_documents returns "relevance scores" in [0,1]
        # (higher is better), not raw distances.
        raw_results = await self._store.search_documents(
            collection_name=collection_name,
            embedding_function=embedding_function,
            query=query,
            k=top_k,
            fetch_k=fetch_k,
            score_threshold=similarity_threshold if similarity_threshold else None,
            where_filter=filter_metadata,
            search_type=search_type,
            mmr_lambda=mmr_lambda,
        )

        # Convert to RetrievalResult format
        results = []
        for rank, (doc, score) in enumerate(raw_results):
            # For MMR path, score may be None. Preserve ordering using a fallback score.
            similarity = (
                float(score) if score is not None else max(0.0, 1.0 - (rank * 0.001))
            )

            metadata = doc.metadata or {}

            result = RetrievalResult(
                id=metadata.get("chunk_id", str(id(doc))),
                content=doc.page_content,
                score=similarity,
                metadata=metadata,
                document_id=metadata.get("document_id"),
                chunk_index=metadata.get("chunk_index"),
                title=metadata.get("title"),
                engine_type=self.engine_type.value,
            )
            results.append(result)

        # Sort by score descending (defensive; raw_results should already be ordered)
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:top_k]

    async def get_collection_info(
        self,
        collection_name: str,
    ) -> dict[str, Any]:
        """Get information about a Chroma collection."""
        info = await self._store.get_collection_info(collection_name)
        info["engine_type"] = self.engine_type.value
        return info

    async def clear_collection(
        self,
        collection_name: str,
    ) -> bool:
        """Delete and recreate the collection."""
        try:
            await self._store.delete_collection(collection_name)
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection {collection_name}: {e}")
            return False

    def get_config(self) -> dict[str, Any]:
        """Get engine configuration."""
        return {
            "engine_type": self.engine_type.value,
            "store_type": "chroma",
        }
