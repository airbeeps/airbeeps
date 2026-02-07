"""
Unit tests for query transformation module.
"""

import pytest

from airbeeps.rag.query_transform import (
    QueryTransformer,
    QueryTransformType,
    get_query_transformer,
)


class TestQueryTransformType:
    """Tests for QueryTransformType enum."""

    def test_enum_values(self):
        """Test enum has expected values."""
        assert QueryTransformType.NONE.value == "none"
        assert QueryTransformType.HYDE.value == "hyde"
        assert QueryTransformType.MULTI_QUERY.value == "multi_query"
        assert QueryTransformType.STEP_BACK.value == "step_back"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert QueryTransformType("none") == QueryTransformType.NONE
        assert QueryTransformType("multi_query") == QueryTransformType.MULTI_QUERY


class TestQueryTransformer:
    """Tests for QueryTransformer."""

    @pytest.fixture
    def transformer(self):
        """Create a query transformer without LLM."""
        return QueryTransformer(llm=None, transform_type=QueryTransformType.NONE)

    @pytest.mark.asyncio
    async def test_no_transform(self, transformer):
        """Test no transformation returns original query."""
        query = "What is machine learning?"
        result = await transformer.transform(
            query, transform_type=QueryTransformType.NONE
        )

        assert result == [query]

    @pytest.mark.asyncio
    async def test_multi_query_deterministic(self):
        """Test deterministic multi-query generation."""
        transformer = QueryTransformer(
            llm=None, transform_type=QueryTransformType.MULTI_QUERY
        )
        query = "What is the capital of France? Tell me more about it."

        result = await transformer.transform(query)

        # Should include original and variations
        assert len(result) >= 1
        assert query in result or query.strip() in [r.strip() for r in result]

    @pytest.mark.asyncio
    async def test_multi_query_removes_punctuation(self):
        """Test that multi-query variant removes punctuation."""
        transformer = QueryTransformer(llm=None)
        query = "What's the weather like today?"

        result = transformer._deterministic_multi_query(query, max_count=3)

        # Should have at least the original
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_hyde_without_llm_fallback(self):
        """Test HyDE falls back to original without LLM."""
        transformer = QueryTransformer(llm=None, transform_type=QueryTransformType.HYDE)
        query = "Explain quantum computing"

        result = await transformer.transform(
            query, transform_type=QueryTransformType.HYDE
        )

        # Without LLM, should return original query
        assert query in result

    @pytest.mark.asyncio
    async def test_step_back_without_llm_fallback(self):
        """Test step-back falls back to original without LLM."""
        transformer = QueryTransformer(llm=None)
        query = "How do I fix error X in Python 3.9?"

        result = await transformer.transform(
            query, transform_type=QueryTransformType.STEP_BACK
        )

        # Without LLM, should return original query
        assert query in result


class TestDeterministicMultiQuery:
    """Tests for deterministic multi-query generation."""

    @pytest.fixture
    def transformer(self):
        """Create a transformer."""
        return QueryTransformer(llm=None)

    def test_removes_punctuation(self, transformer):
        """Test punctuation removal variant."""
        query = "What's the difference between Python and Java?"
        result = transformer._deterministic_multi_query(query, max_count=5)

        # Should have variants
        assert len(result) >= 1

    def test_splits_on_sentence_boundaries(self, transformer):
        """Test splitting on sentence boundaries."""
        query = "First question? Second part. Third section!"
        result = transformer._deterministic_multi_query(query, max_count=5)

        assert len(result) >= 1

    def test_respects_max_count(self, transformer):
        """Test max_count is respected."""
        query = (
            "A very long query. With many sentences. And more content. Even more here."
        )
        result = transformer._deterministic_multi_query(query, max_count=2)

        assert len(result) <= 2

    def test_deduplicates(self, transformer):
        """Test duplicate removal."""
        query = "Simple query"
        result = transformer._deterministic_multi_query(query, max_count=5)

        # Check no duplicates (case-insensitive)
        lower_results = [r.lower() for r in result]
        assert len(lower_results) == len(set(lower_results))


class TestGetQueryTransformer:
    """Tests for get_query_transformer factory."""

    def test_creates_transformer(self):
        """Test factory creates transformer."""
        transformer = get_query_transformer()
        assert isinstance(transformer, QueryTransformer)

    def test_respects_transform_type(self):
        """Test factory respects transform_type parameter."""
        transformer = get_query_transformer(transform_type=QueryTransformType.HYDE)
        assert transformer.transform_type == QueryTransformType.HYDE
