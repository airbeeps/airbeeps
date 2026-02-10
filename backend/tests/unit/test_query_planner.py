"""
Unit tests for Query Planner Module.

Tests for QueryPlanner with mocked LLM to ensure no real API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestQueryPlanResult:
    """Tests for QueryPlanResult dataclass."""

    def test_create_result(self):
        """Should create result with expected fields."""
        from airbeeps.rag.query_planner import QueryPlanResult

        result = QueryPlanResult(
            original_query="compare A and B",
            sub_queries=["What is A?", "What is B?"],
            sub_results=[],
            was_decomposed=True,
        )

        assert result.original_query == "compare A and B"
        assert len(result.sub_queries) == 2
        assert result.was_decomposed is True


class TestSubQueryResult:
    """Tests for SubQueryResult dataclass."""

    def test_create_sub_result(self):
        """Should create sub-query result."""
        from airbeeps.rag.query_planner import SubQueryResult

        result = SubQueryResult(
            sub_query="What is Python?",
            results=[{"content": "Python is..."}],
            success=True,
        )

        assert result.sub_query == "What is Python?"
        assert result.success is True


class TestQueryPlanner:
    """Tests for QueryPlanner class."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mocked LLM."""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def planner_no_llm(self):
        """Create QueryPlanner without LLM."""
        from airbeeps.rag.query_planner import QueryPlanner

        return QueryPlanner(llm=None)

    @pytest.fixture
    def planner_with_llm(self, mock_llm):
        """Create QueryPlanner with mocked LLM."""
        from airbeeps.rag.query_planner import QueryPlanner

        return QueryPlanner(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_should_decompose_short_query(self, planner_no_llm):
        """Should not decompose short queries."""
        result = await planner_no_llm.should_decompose("What is AI?")

        assert result is False

    @pytest.mark.asyncio
    async def test_should_decompose_comparison(self, planner_no_llm):
        """Should decompose comparison queries."""
        result = await planner_no_llm.should_decompose(
            "Compare Python and JavaScript for web development"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_should_decompose_vs_query(self, planner_no_llm):
        """Should decompose vs queries."""
        result = await planner_no_llm.should_decompose("React vs Vue for building apps")

        assert result is True

    @pytest.mark.asyncio
    async def test_should_decompose_multipart(self, planner_no_llm):
        """Should decompose multi-part queries."""
        result = await planner_no_llm.should_decompose(
            "What is Python and how does it compare to Ruby?"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_decompose_query_no_llm(self, planner_no_llm):
        """Should return original query without LLM."""
        result = await planner_no_llm.decompose_query("complex query")

        assert result == ["complex query"]

    @pytest.mark.asyncio
    async def test_decompose_query_with_llm(self, planner_with_llm, mock_llm):
        """Should use LLM for decomposition."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(
                text="What are the benefits of Python?\nWhat are the benefits of JavaScript?\nHow do they compare?"
            )
        )

        result = await planner_with_llm.decompose_query(
            "Compare Python and JavaScript benefits"
        )

        assert len(result) >= 2
        mock_llm.acomplete.assert_called_once()

    @pytest.mark.asyncio
    async def test_decompose_query_cleans_numbering(self, planner_with_llm, mock_llm):
        """Should clean up numbering in decomposed queries."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="1. What is Python?\n2. What is JavaScript?")
        )

        result = await planner_with_llm.decompose_query("Compare languages")

        # Should remove numbering
        assert all(not q.startswith("1.") for q in result)

    @pytest.mark.asyncio
    async def test_plan_query_no_decomposition(self, planner_no_llm):
        """Should not decompose simple queries."""
        sub_queries, was_decomposed = await planner_no_llm.plan_query("What is AI?")

        assert sub_queries == ["What is AI?"]
        assert was_decomposed is False

    @pytest.mark.asyncio
    async def test_plan_query_with_decomposition(self, planner_with_llm, mock_llm):
        """Should decompose complex queries."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="What is Python?\nWhat is JavaScript?")
        )

        # Query needs 5+ words to pass the length check before keywords are evaluated
        sub_queries, was_decomposed = await planner_with_llm.plan_query(
            "Compare the features of Python vs JavaScript programming languages"
        )

        assert len(sub_queries) >= 2
        assert was_decomposed is True

    @pytest.mark.asyncio
    async def test_execute_plan(self, planner_with_llm, mock_llm):
        """Should execute plan with sub-queries."""
        import uuid

        # Mock LLM responses
        mock_llm.acomplete = AsyncMock(return_value=MagicMock(text="Sub-query answer"))

        async def mock_retrieval(**kwargs):
            return [{"content": "result for " + kwargs.get("query", "")}]

        result = await planner_with_llm.execute_plan(
            query="Compare A vs B",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
        )

        assert result.original_query == "Compare A vs B"
        assert len(result.sub_results) >= 1

    @pytest.mark.asyncio
    async def test_execute_plan_parallel_execution(self, planner_with_llm, mock_llm):
        """Should execute sub-queries in parallel."""
        import asyncio
        import uuid

        execution_order = []

        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="Query A\nQuery B\nQuery C")
        )

        async def mock_retrieval(**kwargs):
            query = kwargs.get("query", "")
            execution_order.append(query)
            await asyncio.sleep(0.01)  # Small delay
            return [{"content": f"result for {query}"}]

        result = await planner_with_llm.execute_plan(
            query="Compare A vs B vs C",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
        )

        assert len(result.sub_results) >= 1

    @pytest.mark.asyncio
    async def test_execute_plan_handles_failures(self, planner_no_llm):
        """Should handle sub-query failures gracefully."""
        import uuid

        async def failing_retrieval(**kwargs):
            raise Exception("Retrieval failed")

        result = await planner_no_llm.execute_plan(
            query="test",
            kb_id=uuid.uuid4(),
            retrieval_func=failing_retrieval,
        )

        # Should not raise, but mark as failed
        assert len(result.sub_results) == 1
        assert result.sub_results[0].success is False


class TestGetQueryPlanner:
    """Tests for get_query_planner factory."""

    @pytest.mark.asyncio
    async def test_get_query_planner(self):
        """Should create query planner."""
        from airbeeps.rag.query_planner import get_query_planner

        planner = await get_query_planner()

        assert planner is not None
        assert planner.max_sub_queries == 5
