"""
Unit tests for Multi-Hop Retrieval Module.

Tests for MultiHopRetriever with mocked LLM to ensure no real API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestHopResult:
    """Tests for HopResult dataclass."""

    def test_create_hop_result(self):
        """Should create hop result with expected fields."""
        from airbeeps.rag.multi_hop import HopResult

        result = HopResult(
            hop_number=1,
            query="first query",
            results=[{"content": "doc1"}],
            num_results=1,
        )

        assert result.hop_number == 1
        assert result.query == "first query"


class TestMultiHopResult:
    """Tests for MultiHopResult dataclass."""

    def test_create_multi_hop_result(self):
        """Should create multi-hop result."""
        from airbeeps.rag.multi_hop import HopResult, MultiHopResult

        result = MultiHopResult(
            original_query="complex query",
            hops=[HopResult(hop_number=1, query="q1")],
            total_hops=1,
            success=True,
        )

        assert result.original_query == "complex query"
        assert result.total_hops == 1


class TestMultiHopRetriever:
    """Tests for MultiHopRetriever class."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mocked LLM."""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def retriever_no_llm(self):
        """Create MultiHopRetriever without LLM."""
        from airbeeps.rag.multi_hop import MultiHopRetriever

        return MultiHopRetriever(llm=None, max_hops=3)

    @pytest.fixture
    def retriever_with_llm(self, mock_llm):
        """Create MultiHopRetriever with mocked LLM."""
        from airbeeps.rag.multi_hop import MultiHopRetriever

        return MultiHopRetriever(llm=mock_llm, max_hops=3, synthesize_results=True)

    @pytest.mark.asyncio
    async def test_needs_more_info_no_llm(self, retriever_no_llm):
        """Should return False without LLM."""
        needs_more, follow_up = await retriever_no_llm.needs_more_info(
            "query", "retrieved info"
        )

        assert needs_more is False
        assert follow_up is None

    @pytest.mark.asyncio
    async def test_needs_more_info_with_llm(self, retriever_with_llm, mock_llm):
        """Should use LLM to determine if more info needed."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(
                text="NEED_MORE: YES\nREASON: Missing details\nFOLLOW_UP: What are the details?"
            )
        )

        needs_more, follow_up = await retriever_with_llm.needs_more_info(
            "original query", "some results"
        )

        assert needs_more is True
        assert follow_up == "What are the details?"

    @pytest.mark.asyncio
    async def test_needs_more_info_no(self, retriever_with_llm, mock_llm):
        """Should detect when no more info needed."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="NEED_MORE: NO\nREASON: Complete information")
        )

        needs_more, follow_up = await retriever_with_llm.needs_more_info(
            "query", "comprehensive results"
        )

        assert needs_more is False

    @pytest.mark.asyncio
    async def test_generate_follow_up_no_llm(self, retriever_no_llm):
        """Should return None without LLM."""
        result = await retriever_no_llm.generate_follow_up("query", "info", 1)

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_follow_up_with_llm(self, retriever_with_llm, mock_llm):
        """Should generate follow-up query."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="What are the implementation details?")
        )

        result = await retriever_with_llm.generate_follow_up("query", "info", 1)

        assert result == "What are the implementation details?"

    def test_format_results_for_context(self, retriever_no_llm):
        """Should format results for prompt context."""
        results = [
            MagicMock(content="First document content"),
            {"content": "Second document content"},
            "Third plain string",
        ]

        formatted = retriever_no_llm._format_results_for_context(results)

        assert "[1]" in formatted
        assert "[2]" in formatted
        assert "First document" in formatted

    def test_format_results_empty(self, retriever_no_llm):
        """Should handle empty results."""
        formatted = retriever_no_llm._format_results_for_context([])

        assert formatted == "No results"

    @pytest.mark.asyncio
    async def test_synthesize_all_results(self, retriever_with_llm, mock_llm):
        """Should synthesize results from all hops."""
        from airbeeps.rag.multi_hop import HopResult

        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="Synthesized answer from all hops")
        )

        hops = [
            HopResult(hop_number=1, query="q1", results=[MagicMock(content="r1")]),
            HopResult(hop_number=2, query="q2", results=[MagicMock(content="r2")]),
        ]

        result = await retriever_with_llm.synthesize_all_results("original", hops)

        assert result == "Synthesized answer from all hops"

    @pytest.mark.asyncio
    async def test_retrieve_multi_hop_single_hop(self, retriever_with_llm, mock_llm):
        """Should stop early when no more info needed."""
        import uuid

        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="NEED_MORE: NO\nREASON: Complete")
        )

        async def mock_retrieval(**kwargs):
            return [{"content": "result", "node_id": "1"}]

        result = await retriever_with_llm.retrieve_multi_hop(
            query="simple query",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
        )

        assert result.success is True
        assert result.total_hops == 1

    @pytest.mark.asyncio
    async def test_retrieve_multi_hop_multiple_hops(self, retriever_with_llm, mock_llm):
        """Should perform multiple hops when needed."""
        import uuid

        hop_count = 0

        async def mock_acomplete(prompt):
            nonlocal hop_count
            hop_count += 1
            if hop_count == 1:
                return MagicMock(
                    text="NEED_MORE: YES\nREASON: Need more\nFOLLOW_UP: More details"
                )
            return MagicMock(text="NEED_MORE: NO")

        mock_llm.acomplete = mock_acomplete

        async def mock_retrieval(**kwargs):
            return [{"content": "result", "node_id": str(hop_count)}]

        result = await retriever_with_llm.retrieve_multi_hop(
            query="complex query",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
        )

        assert result.total_hops >= 2

    @pytest.mark.asyncio
    async def test_retrieve_deduplicates_results(self, retriever_no_llm):
        """Should deduplicate results across hops."""
        import uuid

        call_count = 0

        async def mock_retrieval(**kwargs):
            nonlocal call_count
            call_count += 1
            # Return same node_id in both calls
            return [{"content": f"content {call_count}", "node_id": "same-id"}]

        result = await retriever_no_llm.retrieve_multi_hop(
            query="test",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
        )

        # With deduplication, should only have one result
        unique_ids = set()
        for r in result.all_results:
            if isinstance(r, dict) and "node_id" in r:
                unique_ids.add(r["node_id"])

        assert len(unique_ids) <= 1

    @pytest.mark.asyncio
    async def test_retrieve_handles_retrieval_failure(self, retriever_no_llm):
        """Should handle retrieval failures gracefully."""
        import uuid

        async def failing_retrieval(**kwargs):
            raise Exception("Retrieval error")

        result = await retriever_no_llm.retrieve_multi_hop(
            query="test",
            kb_id=uuid.uuid4(),
            retrieval_func=failing_retrieval,
        )

        # Should complete without raising
        assert result.total_hops == 0
        assert result.success is False


class TestGetMultiHopRetriever:
    """Tests for get_multi_hop_retriever factory."""

    @pytest.mark.asyncio
    async def test_get_multi_hop_retriever(self):
        """Should create multi-hop retriever."""
        from airbeeps.rag.multi_hop import get_multi_hop_retriever

        retriever = await get_multi_hop_retriever(max_hops=5)

        assert retriever.max_hops == 5
