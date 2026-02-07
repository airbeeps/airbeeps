"""
Hybrid Retriever for SOTA RAG.

Combines dense (vector) and sparse (BM25) retrieval with
Reciprocal Rank Fusion (RRF) for improved recall.
"""

import logging
from typing import Any

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import BaseNode, NodeWithScore, QueryBundle

from airbeeps.config import settings

logger = logging.getLogger(__name__)


class HybridRetrieverBuilder:
    """
    Builder for hybrid retrievers that combine dense and sparse search.

    Uses Reciprocal Rank Fusion (RRF) to merge results from:
    - Dense retrieval (vector similarity)
    - Sparse retrieval (BM25 keyword matching)
    """

    def __init__(
        self,
        alpha: float | None = None,
        bm25_k1: float | None = None,
        bm25_b: float | None = None,
    ):
        """
        Initialize the hybrid retriever builder.

        Args:
            alpha: Weight for dense vs sparse (0=sparse only, 1=dense only)
            bm25_k1: BM25 k1 parameter
            bm25_b: BM25 b parameter
        """
        self.alpha = alpha if alpha is not None else settings.RAG_HYBRID_ALPHA
        self.bm25_k1 = bm25_k1 if bm25_k1 is not None else settings.RAG_BM25_K1
        self.bm25_b = bm25_b if bm25_b is not None else settings.RAG_BM25_B

    def build(
        self,
        index: VectorStoreIndex,
        nodes: list[BaseNode] | None = None,
        top_k: int = 10,
    ) -> BaseRetriever:
        """
        Build a hybrid retriever for the given index.

        Args:
            index: VectorStoreIndex for dense retrieval
            nodes: Optional list of nodes for BM25 (if not provided, uses index)
            top_k: Number of results to retrieve

        Returns:
            Configured hybrid retriever
        """
        try:
            return self._build_query_fusion_retriever(index, nodes, top_k)
        except Exception as e:
            logger.warning(
                f"Failed to build hybrid retriever, falling back to dense: {e}"
            )
            return index.as_retriever(similarity_top_k=top_k)

    def _build_query_fusion_retriever(
        self,
        index: VectorStoreIndex,
        nodes: list[BaseNode] | None,
        top_k: int,
    ) -> BaseRetriever:
        """Build using LlamaIndex QueryFusionRetriever."""
        from llama_index.core.retrievers import QueryFusionRetriever
        from llama_index.retrievers.bm25 import BM25Retriever

        # Dense retriever from index
        vector_retriever = index.as_retriever(similarity_top_k=top_k)

        # BM25 retriever
        if nodes:
            bm25_retriever = BM25Retriever.from_defaults(
                nodes=nodes,
                similarity_top_k=top_k,
            )
        else:
            # Try to get nodes from index docstore
            try:
                docstore = index.storage_context.docstore
                all_nodes = list(docstore.docs.values())
                bm25_retriever = BM25Retriever.from_defaults(
                    nodes=all_nodes,
                    similarity_top_k=top_k,
                )
            except Exception as e:
                logger.warning(f"Could not create BM25 retriever: {e}")
                return vector_retriever

        # Combine with RRF fusion
        return QueryFusionRetriever(
            retrievers=[vector_retriever, bm25_retriever],
            similarity_top_k=top_k,
            num_queries=1,  # We handle query expansion separately
            mode="reciprocal_rerank",  # RRF fusion
        )

    def build_with_auto_merge(
        self,
        index: VectorStoreIndex,
        storage_context: StorageContext,
        nodes: list[BaseNode] | None = None,
        top_k: int = 10,
        simple_ratio_thresh: float = 0.4,
    ) -> BaseRetriever:
        """
        Build a hybrid retriever with auto-merging for hierarchical chunks.

        Args:
            index: VectorStoreIndex for dense retrieval
            storage_context: Storage context with docstore for hierarchy
            nodes: Optional list of nodes for BM25
            top_k: Number of results
            simple_ratio_thresh: Merge threshold (merge if X% of children retrieved)

        Returns:
            Configured hybrid retriever with auto-merging
        """
        from llama_index.core.retrievers import AutoMergingRetriever

        # First build the hybrid retriever
        base_retriever = self.build(
            index, nodes, top_k=top_k * 2
        )  # Fetch more for merging

        # Wrap with auto-merging
        return AutoMergingRetriever(
            base_retriever,
            storage_context=storage_context,
            simple_ratio_thresh=simple_ratio_thresh,
        )


class SimpleHybridRetriever(BaseRetriever):
    """
    Simple hybrid retriever implementation.

    Manually combines dense and sparse retrieval when
    LlamaIndex's QueryFusionRetriever is not available.
    """

    def __init__(
        self,
        vector_retriever: BaseRetriever,
        bm25_retriever: BaseRetriever,
        alpha: float = 0.5,
        top_k: int = 10,
    ):
        """
        Initialize the simple hybrid retriever.

        Args:
            vector_retriever: Dense retriever
            bm25_retriever: Sparse BM25 retriever
            alpha: Weight for dense (0=sparse only, 1=dense only)
            top_k: Final number of results
        """
        super().__init__()
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.alpha = alpha
        self.top_k = top_k

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """Retrieve with hybrid fusion."""
        # Get results from both retrievers
        vector_results = self.vector_retriever.retrieve(query_bundle)
        bm25_results = self.bm25_retriever.retrieve(query_bundle)

        # Apply RRF fusion
        return self._rrf_fusion(vector_results, bm25_results)

    async def _aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """Async retrieve with hybrid fusion."""
        import asyncio

        # Run both retrievals concurrently
        vector_task = asyncio.create_task(self.vector_retriever.aretrieve(query_bundle))
        bm25_task = asyncio.create_task(self.bm25_retriever.aretrieve(query_bundle))

        vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)

        return self._rrf_fusion(vector_results, bm25_results)

    def _rrf_fusion(
        self,
        vector_results: list[NodeWithScore],
        bm25_results: list[NodeWithScore],
        k: int = 60,
    ) -> list[NodeWithScore]:
        """
        Apply Reciprocal Rank Fusion to merge results.

        RRF score = sum(1 / (k + rank)) for each list where doc appears
        """
        # Build node_id -> NodeWithScore mapping
        node_map: dict[str, NodeWithScore] = {}
        rrf_scores: dict[str, float] = {}

        # Process vector results
        for rank, node_with_score in enumerate(vector_results):
            node_id = node_with_score.node.node_id
            node_map[node_id] = node_with_score
            rrf_scores[node_id] = rrf_scores.get(node_id, 0) + self.alpha / (
                k + rank + 1
            )

        # Process BM25 results
        for rank, node_with_score in enumerate(bm25_results):
            node_id = node_with_score.node.node_id
            if node_id not in node_map:
                node_map[node_id] = node_with_score
            rrf_scores[node_id] = rrf_scores.get(node_id, 0) + (1 - self.alpha) / (
                k + rank + 1
            )

        # Sort by RRF score and return top_k
        sorted_ids = sorted(
            rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
        )

        results: list[NodeWithScore] = []
        for node_id in sorted_ids[: self.top_k]:
            node_with_score = node_map[node_id]
            # Update score to RRF score
            node_with_score.score = rrf_scores[node_id]
            results.append(node_with_score)

        return results


def build_hybrid_retriever(
    index: VectorStoreIndex,
    nodes: list[BaseNode] | None = None,
    top_k: int = 10,
    storage_context: StorageContext | None = None,
    use_auto_merge: bool = False,
) -> BaseRetriever:
    """
    Convenience function to build a hybrid retriever.

    Args:
        index: VectorStoreIndex
        nodes: Optional nodes for BM25
        top_k: Number of results
        storage_context: For auto-merging (optional)
        use_auto_merge: Whether to use auto-merging

    Returns:
        Configured retriever
    """
    builder = HybridRetrieverBuilder()

    if use_auto_merge and storage_context:
        return builder.build_with_auto_merge(
            index=index,
            storage_context=storage_context,
            nodes=nodes,
            top_k=top_k,
        )

    return builder.build(index=index, nodes=nodes, top_k=top_k)
