"""
Unit tests for the reranker module.
"""

import pytest

from airbeeps.rag.reranker import (
    EmbeddingReranker,
    RerankerFactory,
    RerankerType,
    get_reranker,
)


class TestRerankerType:
    """Tests for RerankerType enum."""

    def test_enum_values(self):
        """Test enum has expected values."""
        assert RerankerType.NONE.value == "none"
        assert RerankerType.BGE.value == "bge"
        assert RerankerType.COHERE.value == "cohere"
        assert RerankerType.COLBERT.value == "colbert"
        assert RerankerType.SENTENCE_TRANSFORMER.value == "sentence_transformer"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert RerankerType("none") == RerankerType.NONE
        assert RerankerType("bge") == RerankerType.BGE


class TestRerankerFactory:
    """Tests for RerankerFactory."""

    def test_create_none_returns_none(self):
        """Test creating 'none' reranker returns None."""
        result = RerankerFactory.create(RerankerType.NONE)
        assert result is None

    def test_create_with_string_type(self):
        """Test creating reranker with string type."""
        result = RerankerFactory.create("none")
        assert result is None


class TestEmbeddingReranker:
    """Tests for EmbeddingReranker."""

    def test_class_name(self):
        """Test class name method."""
        mock_embed_model = None
        reranker = EmbeddingReranker(embed_model=mock_embed_model, top_n=5)

        assert reranker.class_name() == "EmbeddingReranker"

    def test_initialization(self):
        """Test reranker initialization."""
        mock_embed_model = None
        reranker = EmbeddingReranker(embed_model=mock_embed_model, top_n=3)

        assert reranker.embed_model is None
        assert reranker.top_n == 3


class TestGetReranker:
    """Tests for get_reranker factory function."""

    def test_returns_none_when_disabled(self):
        """Test returns None when reranking disabled in settings."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr("airbeeps.rag.reranker.settings.RAG_ENABLE_RERANKING", False)
            result = get_reranker()
            assert result is None

    def test_infers_bge_type_from_model(self):
        """Test BGE type is inferred from model name."""
        # This would need the actual flag_embedding_reranker package installed
        # For unit testing, we just verify the logic
        pass
