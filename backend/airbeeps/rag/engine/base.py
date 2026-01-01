"""
Base RAG Engine interface.

Defines the abstract interface that all RAG engine implementations must follow.
This allows swapping between vector, hybrid, and graph-based RAG approaches.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.documents import Document as VectorDocument


class EngineType(str, Enum):
    """Supported RAG engine types."""

    VECTOR = "vector"  # Traditional vector similarity search
    HYBRID = "hybrid"  # Vector + BM25/keyword search
    GRAPH = "graph"  # Graph-based RAG (future)
    LIGHTRAG = "lightrag"  # LightRAG implementation (future)


@dataclass
class RetrievalResult:
    """Result from a retrieval query."""

    id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    # Source info for citations
    document_id: str | None = None
    chunk_index: int | None = None
    title: str | None = None

    # Engine-specific data
    engine_type: str | None = None
    engine_data: dict[str, Any] = field(default_factory=dict)


class BaseRAGEngine(ABC):
    """
    Abstract base class for RAG engines.

    All RAG engine implementations must provide:
    - index_documents(): Add/update documents in the index
    - delete_documents(): Remove documents from the index
    - retrieve(): Search for relevant documents
    - get_collection_info(): Get metadata about the collection

    Engine implementations can have their own initialization and configuration,
    but must conform to this interface for use in the RAG service.
    """

    engine_type: EngineType = EngineType.VECTOR

    @abstractmethod
    async def index_documents(
        self,
        collection_name: str,
        documents: list[VectorDocument],
        embedding_function: Any,
        **kwargs,
    ) -> int:
        """
        Add or update documents in the index.

        Args:
            collection_name: Name of the collection/index
            documents: List of documents to index
            embedding_function: Embedder to use for vectorization
            **kwargs: Engine-specific options

        Returns:
            Number of documents indexed
        """

    @abstractmethod
    async def delete_documents(
        self,
        collection_name: str,
        document_ids: list[str],
        **kwargs,
    ) -> int:
        """
        Delete documents from the index.

        Args:
            collection_name: Name of the collection/index
            document_ids: List of document IDs to delete
            **kwargs: Engine-specific options

        Returns:
            Number of documents deleted
        """

    @abstractmethod
    async def retrieve(
        self,
        collection_name: str,
        query: str,
        embedding_function: Any,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
        filter_metadata: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[RetrievalResult]:
        """
        Retrieve relevant documents for a query.

        Args:
            collection_name: Name of the collection/index
            query: Search query text
            embedding_function: Embedder for query vectorization
            top_k: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
            filter_metadata: Optional metadata filters
            **kwargs: Engine-specific options

        Returns:
            List of retrieval results, sorted by relevance
        """

    @abstractmethod
    async def get_collection_info(
        self,
        collection_name: str,
    ) -> dict[str, Any]:
        """
        Get metadata about a collection.

        Args:
            collection_name: Name of the collection/index

        Returns:
            Dict with collection info (count, settings, etc.)
        """

    async def clear_collection(
        self,
        collection_name: str,
    ) -> bool:
        """
        Clear all documents from a collection.

        Default implementation may not be efficient for all engines.
        Override in subclasses for optimized clearing.

        Args:
            collection_name: Name of the collection/index

        Returns:
            True if successful
        """
        info = await self.get_collection_info(collection_name)
        if info.get("count", 0) == 0:
            return True

        # Default: engines should override with bulk delete
        return False

    def get_engine_type(self) -> EngineType:
        """Get the type of this engine."""
        return self.engine_type

    def get_config(self) -> dict[str, Any]:
        """
        Get engine configuration for serialization.

        Override in subclasses to include engine-specific config.
        """
        return {
            "engine_type": self.engine_type.value,
        }
