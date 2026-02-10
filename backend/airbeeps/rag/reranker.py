"""
Reranker Module for SOTA RAG.

Provides cross-encoder reranking for improved retrieval precision.
Supports multiple reranker backends:
- BGE Reranker (local, free)
- Cohere Rerank (API)
- ColBERT Rerank (local)
"""

import logging
from enum import Enum
from typing import Any

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle

from airbeeps.config import settings

logger = logging.getLogger(__name__)


class RerankerType(str, Enum):
    """Supported reranker types."""

    NONE = "none"
    BGE = "bge"
    COHERE = "cohere"
    COLBERT = "colbert"
    SENTENCE_TRANSFORMER = "sentence_transformer"


class RerankerFactory:
    """Factory for creating reranker instances."""

    @staticmethod
    def create(
        reranker_type: RerankerType | str,
        top_n: int | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseNodePostprocessor | None:
        """
        Create a reranker postprocessor.

        Args:
            reranker_type: Type of reranker to create
            top_n: Number of top results to return after reranking
            model: Model name/identifier (varies by reranker type)
            **kwargs: Additional reranker-specific configuration

        Returns:
            Configured reranker or None if type is "none"
        """
        if isinstance(reranker_type, str):
            reranker_type = RerankerType(reranker_type)

        top_n = top_n or settings.RAG_RERANKER_TOP_N

        if reranker_type == RerankerType.NONE:
            return None

        if reranker_type == RerankerType.BGE:
            return RerankerFactory._create_bge_reranker(top_n, model, **kwargs)

        if reranker_type == RerankerType.COHERE:
            return RerankerFactory._create_cohere_reranker(top_n, model, **kwargs)

        if reranker_type == RerankerType.COLBERT:
            return RerankerFactory._create_colbert_reranker(top_n, model, **kwargs)

        if reranker_type == RerankerType.SENTENCE_TRANSFORMER:
            return RerankerFactory._create_st_reranker(top_n, model, **kwargs)

        logger.warning(f"Unknown reranker type: {reranker_type}")
        return None

    @staticmethod
    def _create_bge_reranker(
        top_n: int,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseNodePostprocessor:
        """Create BGE reranker using FlagEmbedding."""
        from llama_index.postprocessor.flag_embedding_reranker import (
            FlagEmbeddingReranker,
        )

        model = model or settings.RAG_RERANKER_MODEL or "BAAI/bge-reranker-v2-m3"
        logger.info(f"Creating BGE reranker with model: {model}")

        return FlagEmbeddingReranker(
            model=model,
            top_n=top_n,
            use_fp16=kwargs.get("use_fp16", False),
        )

    @staticmethod
    def _create_cohere_reranker(
        top_n: int,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseNodePostprocessor:
        """Create Cohere reranker (requires API key)."""
        try:
            from llama_index.postprocessor.cohere_rerank import CohereRerank
        except ImportError:
            logger.error(
                "Cohere reranker requires llama-index-postprocessor-cohere-rerank"
            )
            raise

        model = model or "rerank-english-v3.0"
        api_key = kwargs.get("api_key")

        if not api_key:
            import os

            api_key = os.environ.get("COHERE_API_KEY")

        if not api_key:
            raise ValueError("Cohere reranker requires an API key")

        logger.info(f"Creating Cohere reranker with model: {model}")

        return CohereRerank(
            model=model,
            top_n=top_n,
            api_key=api_key,
        )

    @staticmethod
    def _create_colbert_reranker(
        top_n: int,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseNodePostprocessor:
        """Create ColBERT reranker."""
        try:
            from llama_index.postprocessor.colbert_rerank import ColbertRerank
        except ImportError:
            logger.error(
                "ColBERT reranker requires llama-index-postprocessor-colbert-rerank"
            )
            raise

        model = model or "colbert-ir/colbertv2.0"
        logger.info(f"Creating ColBERT reranker with model: {model}")

        return ColbertRerank(
            model=model,
            top_n=top_n,
        )

    @staticmethod
    def _create_st_reranker(
        top_n: int,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseNodePostprocessor:
        """Create Sentence Transformer cross-encoder reranker."""
        from llama_index.core.postprocessor import SentenceTransformerRerank

        model = model or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        logger.info(f"Creating SentenceTransformer reranker with model: {model}")

        return SentenceTransformerRerank(
            model=model,
            top_n=top_n,
        )


class EmbeddingReranker(BaseNodePostprocessor):
    """
    Simple embedding-based reranker.

    Uses cosine similarity between query and document embeddings
    as a lightweight reranking signal. Less accurate than cross-encoders
    but faster and doesn't require additional models.
    """

    def __init__(self, embed_model: Any, top_n: int = 5):
        """
        Initialize embedding reranker.

        Args:
            embed_model: LlamaIndex embedding model
            top_n: Number of results to return
        """
        super().__init__()
        self.embed_model = embed_model
        self.top_n = top_n

    @classmethod
    def class_name(cls) -> str:
        return "EmbeddingReranker"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: QueryBundle | None = None,
    ) -> list[NodeWithScore]:
        """Rerank nodes using embedding similarity."""
        if not nodes or query_bundle is None:
            return nodes[: self.top_n]

        import numpy as np

        try:
            # Get query embedding
            query_embedding = self.embed_model.get_query_embedding(
                query_bundle.query_str
            )
            query_vec = np.array(query_embedding)

            # Get document embeddings and compute similarities
            scored_nodes: list[tuple[NodeWithScore, float]] = []

            for node_with_score in nodes:
                content = node_with_score.node.get_content()
                doc_embedding = self.embed_model.get_text_embedding(content)
                doc_vec = np.array(doc_embedding)

                # Cosine similarity
                similarity = float(
                    np.dot(query_vec, doc_vec)
                    / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec) + 1e-9)
                )

                # Update node score
                new_node = NodeWithScore(
                    node=node_with_score.node,
                    score=similarity,
                )
                scored_nodes.append((new_node, similarity))

            # Sort by similarity and return top_n
            scored_nodes.sort(key=lambda x: x[1], reverse=True)
            return [node for node, _ in scored_nodes[: self.top_n]]

        except Exception as e:
            logger.warning(f"Embedding reranking failed: {e}")
            return nodes[: self.top_n]


class EnsembleReranker(BaseNodePostprocessor):
    """
    Ensemble reranker that combines multiple rerankers using score fusion.

    Supports different fusion strategies:
    - RRF (Reciprocal Rank Fusion): Good for combining rankings
    - weighted_average: Weighted average of normalized scores
    - max: Take the maximum score from any reranker

    This allows combining different reranker strengths (e.g., BGE for
    semantic matching + ColBERT for token-level matching).
    """

    def __init__(
        self,
        rerankers: list[BaseNodePostprocessor],
        fusion_method: str = "rrf",
        weights: list[float] | None = None,
        top_n: int = 5,
        rrf_k: int = 60,
    ):
        """
        Initialize ensemble reranker.

        Args:
            rerankers: List of reranker instances to combine
            fusion_method: How to combine scores - 'rrf', 'weighted_average', or 'max'
            weights: Weights for weighted_average (must match rerankers length)
            top_n: Number of results to return
            rrf_k: RRF constant (default 60 is standard)
        """
        super().__init__()
        self.rerankers = rerankers
        self.fusion_method = fusion_method
        self.weights = weights or [1.0] * len(rerankers)
        self.top_n = top_n
        self.rrf_k = rrf_k

        if len(self.weights) != len(rerankers):
            raise ValueError("Number of weights must match number of rerankers")

    @classmethod
    def class_name(cls) -> str:
        return "EnsembleReranker"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: QueryBundle | None = None,
    ) -> list[NodeWithScore]:
        """Combine rankings from multiple rerankers."""
        if not nodes or not self.rerankers:
            return nodes[: self.top_n]

        # Get rankings from each reranker
        rankings: list[list[NodeWithScore]] = []
        for reranker in self.rerankers:
            try:
                ranked = reranker.postprocess_nodes(nodes, query_bundle)
                rankings.append(ranked)
            except Exception as e:
                logger.warning(f"Reranker {reranker.class_name()} failed: {e}")
                # Fall back to original order for this reranker
                rankings.append(nodes)

        if not rankings:
            return nodes[: self.top_n]

        # Fuse rankings
        if self.fusion_method == "rrf":
            return self._rrf_fusion(rankings)
        if self.fusion_method == "weighted_average":
            return self._weighted_average_fusion(rankings)
        if self.fusion_method == "max":
            return self._max_fusion(rankings)
        logger.warning(f"Unknown fusion method: {self.fusion_method}, using RRF")
        return self._rrf_fusion(rankings)

    def _rrf_fusion(self, rankings: list[list[NodeWithScore]]) -> list[NodeWithScore]:
        """Reciprocal Rank Fusion."""
        # Calculate RRF scores for each node
        rrf_scores: dict[str, float] = {}
        node_map: dict[str, NodeWithScore] = {}

        for ranking_idx, ranking in enumerate(rankings):
            weight = self.weights[ranking_idx]
            for rank, node_with_score in enumerate(ranking):
                node_id = node_with_score.node.node_id
                node_map[node_id] = node_with_score

                # RRF formula: 1 / (k + rank)
                rrf_score = weight * (1.0 / (self.rrf_k + rank + 1))
                rrf_scores[node_id] = rrf_scores.get(node_id, 0) + rrf_score

        # Sort by RRF score
        sorted_ids = sorted(
            rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
        )

        # Return top_n with updated scores
        results = []
        for node_id in sorted_ids[: self.top_n]:
            original_node = node_map[node_id]
            results.append(
                NodeWithScore(
                    node=original_node.node,
                    score=rrf_scores[node_id],
                )
            )

        return results

    def _weighted_average_fusion(
        self, rankings: list[list[NodeWithScore]]
    ) -> list[NodeWithScore]:
        """Weighted average of normalized scores."""
        # Normalize scores within each ranking
        weighted_scores: dict[str, float] = {}
        weight_sums: dict[str, float] = {}
        node_map: dict[str, NodeWithScore] = {}

        for ranking_idx, ranking in enumerate(rankings):
            weight = self.weights[ranking_idx]

            # Get min/max for normalization
            if not ranking:
                continue

            scores = [n.score or 0 for n in ranking]
            min_score = min(scores)
            max_score = max(scores)
            score_range = max_score - min_score if max_score != min_score else 1

            for node_with_score in ranking:
                node_id = node_with_score.node.node_id
                node_map[node_id] = node_with_score

                # Normalize to [0, 1]
                normalized = ((node_with_score.score or 0) - min_score) / score_range

                weighted_scores[node_id] = (
                    weighted_scores.get(node_id, 0) + normalized * weight
                )
                weight_sums[node_id] = weight_sums.get(node_id, 0) + weight

        # Calculate final scores (weighted average)
        final_scores = {
            node_id: weighted_scores[node_id] / weight_sums[node_id]
            for node_id in weighted_scores
        }

        # Sort and return
        sorted_ids = sorted(
            final_scores.keys(), key=lambda x: final_scores[x], reverse=True
        )

        results = []
        for node_id in sorted_ids[: self.top_n]:
            original_node = node_map[node_id]
            results.append(
                NodeWithScore(
                    node=original_node.node,
                    score=final_scores[node_id],
                )
            )

        return results

    def _max_fusion(self, rankings: list[list[NodeWithScore]]) -> list[NodeWithScore]:
        """Take the maximum score from any reranker."""
        max_scores: dict[str, float] = {}
        node_map: dict[str, NodeWithScore] = {}

        for ranking in rankings:
            for node_with_score in ranking:
                node_id = node_with_score.node.node_id
                score = node_with_score.score or 0

                if node_id not in max_scores or score > max_scores[node_id]:
                    max_scores[node_id] = score
                    node_map[node_id] = node_with_score

        # Sort by max score
        sorted_ids = sorted(
            max_scores.keys(), key=lambda x: max_scores[x], reverse=True
        )

        return [node_map[node_id] for node_id in sorted_ids[: self.top_n]]


def get_reranker(
    reranker_type: RerankerType | str | None = None,
    top_n: int | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> BaseNodePostprocessor | None:
    """
    Get a configured reranker.

    Args:
        reranker_type: Type of reranker (defaults to settings)
        top_n: Number of results
        model: Model identifier
        **kwargs: Additional configuration

    Returns:
        Configured reranker or None
    """
    if not settings.RAG_ENABLE_RERANKING:
        return None

    if reranker_type is None:
        # Determine type from model name
        model_name = model or settings.RAG_RERANKER_MODEL
        if "bge" in model_name.lower():
            reranker_type = RerankerType.BGE
        elif "colbert" in model_name.lower():
            reranker_type = RerankerType.COLBERT
        elif "cohere" in model_name.lower():
            reranker_type = RerankerType.COHERE
        else:
            reranker_type = RerankerType.BGE  # Default

    return RerankerFactory.create(
        reranker_type=reranker_type,
        top_n=top_n,
        model=model,
        **kwargs,
    )


def get_ensemble_reranker(
    reranker_configs: list[dict[str, Any]],
    fusion_method: str = "rrf",
    weights: list[float] | None = None,
    top_n: int | None = None,
) -> EnsembleReranker | None:
    """
    Create an ensemble reranker from multiple reranker configurations.

    Args:
        reranker_configs: List of reranker configs, each with 'type' and optional 'model'
            Example: [{"type": "bge"}, {"type": "colbert"}]
        fusion_method: Fusion strategy - 'rrf', 'weighted_average', or 'max'
        weights: Optional weights for weighted_average fusion
        top_n: Number of results to return

    Returns:
        Configured EnsembleReranker or None if no rerankers configured

    Example:
        ensemble = get_ensemble_reranker(
            reranker_configs=[
                {"type": "bge", "model": "BAAI/bge-reranker-v2-m3"},
                {"type": "sentence_transformer", "model": "cross-encoder/ms-marco-MiniLM-L-6-v2"},
            ],
            fusion_method="rrf",
            top_n=5,
        )
    """
    if not settings.RAG_ENABLE_RERANKING:
        return None

    if not reranker_configs:
        return None

    top_n = top_n or settings.RAG_RERANKER_TOP_N

    # Create individual rerankers
    rerankers: list[BaseNodePostprocessor] = []

    for config in reranker_configs:
        reranker_type = config.get("type", "bge")
        model = config.get("model")
        extra_kwargs = {k: v for k, v in config.items() if k not in ("type", "model")}

        try:
            reranker = RerankerFactory.create(
                reranker_type=reranker_type,
                top_n=top_n * 2,  # Get more from individual rerankers for fusion
                model=model,
                **extra_kwargs,
            )
            if reranker:
                rerankers.append(reranker)
        except Exception as e:
            logger.warning(f"Failed to create reranker {reranker_type}: {e}")

    if not rerankers:
        logger.warning("No rerankers could be created for ensemble")
        return None

    logger.info(
        f"Created ensemble reranker with {len(rerankers)} rerankers, fusion={fusion_method}"
    )

    return EnsembleReranker(
        rerankers=rerankers,
        fusion_method=fusion_method,
        weights=weights,
        top_n=top_n,
    )
