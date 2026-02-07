"""
Unit tests for hybrid retriever module.
"""

import pytest
from unittest.mock import MagicMock

from airbeeps.rag.hybrid_retriever import (
    HybridRetrieverBuilder,
    SimpleHybridRetriever,
)


class TestHybridRetrieverBuilder:
    """Tests for HybridRetrieverBuilder."""

    def test_initialization_with_defaults(self):
        """Test builder initializes with default settings."""
        builder = HybridRetrieverBuilder()

        # Should use settings values
        assert builder.alpha is not None
        assert builder.bm25_k1 is not None
        assert builder.bm25_b is not None

    def test_initialization_with_custom_values(self):
        """Test builder with custom alpha."""
        builder = HybridRetrieverBuilder(alpha=0.7, bm25_k1=1.2, bm25_b=0.8)

        assert builder.alpha == 0.7
        assert builder.bm25_k1 == 1.2
        assert builder.bm25_b == 0.8


class TestSimpleHybridRetriever:
    """Tests for SimpleHybridRetriever."""

    @pytest.fixture
    def mock_vector_retriever(self):
        """Create mock vector retriever."""
        return MagicMock()

    @pytest.fixture
    def mock_bm25_retriever(self):
        """Create mock BM25 retriever."""
        return MagicMock()

    def test_initialization(self, mock_vector_retriever, mock_bm25_retriever):
        """Test retriever initialization."""
        retriever = SimpleHybridRetriever(
            vector_retriever=mock_vector_retriever,
            bm25_retriever=mock_bm25_retriever,
            alpha=0.6,
            top_k=5,
        )

        assert retriever.alpha == 0.6
        assert retriever.top_k == 5

    def test_rrf_fusion_basic(self, mock_vector_retriever, mock_bm25_retriever):
        """Test basic RRF fusion logic."""
        retriever = SimpleHybridRetriever(
            vector_retriever=mock_vector_retriever,
            bm25_retriever=mock_bm25_retriever,
            alpha=0.5,
            top_k=3,
        )

        # Create mock results
        mock_node_1 = MagicMock()
        mock_node_1.node.node_id = "node-1"
        mock_node_1.score = 0.9

        mock_node_2 = MagicMock()
        mock_node_2.node.node_id = "node-2"
        mock_node_2.score = 0.8

        mock_node_3 = MagicMock()
        mock_node_3.node.node_id = "node-3"
        mock_node_3.score = 0.7

        vector_results = [mock_node_1, mock_node_2]
        bm25_results = [mock_node_2, mock_node_3]  # node-2 appears in both

        result = retriever._rrf_fusion(vector_results, bm25_results)

        # Should have 3 unique nodes
        assert len(result) <= 3

        # node-2 should have higher score (appears in both lists)
        node_ids = [r.node.node_id for r in result]
        assert "node-2" in node_ids

    def test_rrf_fusion_with_k_parameter(
        self, mock_vector_retriever, mock_bm25_retriever
    ):
        """Test RRF fusion uses k parameter correctly."""
        retriever = SimpleHybridRetriever(
            vector_retriever=mock_vector_retriever,
            bm25_retriever=mock_bm25_retriever,
            alpha=0.5,
            top_k=10,
        )

        mock_node = MagicMock()
        mock_node.node.node_id = "node-1"
        mock_node.score = 0.9

        # With default k=60, first rank gets score of alpha/(60+1) = 0.5/61
        vector_results = [mock_node]
        bm25_results = []

        result = retriever._rrf_fusion(vector_results, bm25_results, k=60)

        assert len(result) == 1
        # Score should be approximately 0.5/61 ≈ 0.0082
        assert result[0].score < 0.01

    def test_rrf_respects_top_k(self, mock_vector_retriever, mock_bm25_retriever):
        """Test RRF fusion respects top_k limit."""
        retriever = SimpleHybridRetriever(
            vector_retriever=mock_vector_retriever,
            bm25_retriever=mock_bm25_retriever,
            alpha=0.5,
            top_k=2,
        )

        # Create 5 mock nodes
        nodes = []
        for i in range(5):
            node = MagicMock()
            node.node.node_id = f"node-{i}"
            node.score = 0.9 - i * 0.1
            nodes.append(node)

        result = retriever._rrf_fusion(nodes, [])

        # Should only return top_k results
        assert len(result) == 2
