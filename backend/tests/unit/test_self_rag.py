"""
Unit tests for Self-RAG Module.

Tests for SelfRAG with mocked LLM to ensure no real API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestRelevanceJudgement:
    """Tests for RelevanceJudgement dataclass."""

    def test_create_judgement(self):
        """Should create judgement with expected fields."""
        from airbeeps.rag.self_rag import RelevanceJudgement

        judgement = RelevanceJudgement(
            is_relevant=True,
            is_sufficient="YES",
            confidence=85,
            reasoning="Documents are highly relevant",
        )

        assert judgement.is_relevant is True
        assert judgement.is_sufficient == "YES"
        assert judgement.confidence == 85


class TestSelfRAGResult:
    """Tests for SelfRAGResult dataclass."""

    def test_create_result(self):
        """Should create result with expected fields."""
        from airbeeps.rag.self_rag import RelevanceJudgement, SelfRAGResult

        result = SelfRAGResult(
            query="test query",
            final_query="rephrased query",
            results=[{"content": "test"}],
            attempts=2,
            success=True,
        )

        assert result.query == "test query"
        assert result.final_query == "rephrased query"
        assert result.attempts == 2


class TestSelfRAG:
    """Tests for SelfRAG class."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mocked LLM."""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def self_rag_no_llm(self):
        """Create SelfRAG without LLM."""
        from airbeeps.rag.self_rag import SelfRAG

        return SelfRAG(llm=None, max_attempts=3, min_confidence=50)

    @pytest.fixture
    def self_rag_with_llm(self, mock_llm):
        """Create SelfRAG with mocked LLM."""
        from airbeeps.rag.self_rag import SelfRAG

        return SelfRAG(llm=mock_llm, max_attempts=3, min_confidence=50)

    @pytest.mark.asyncio
    async def test_judge_relevance_no_llm_with_results(self, self_rag_no_llm):
        """Should return positive judgement when results exist."""
        results = [{"content": "doc1"}, {"content": "doc2"}, {"content": "doc3"}]

        judgement = await self_rag_no_llm.judge_relevance("test query", results)

        assert judgement.is_relevant is True
        assert judgement.is_sufficient == "YES"

    @pytest.mark.asyncio
    async def test_judge_relevance_no_llm_no_results(self, self_rag_no_llm):
        """Should return negative judgement when no results."""
        judgement = await self_rag_no_llm.judge_relevance("test query", [])

        assert judgement.is_relevant is False
        assert judgement.confidence == 0

    @pytest.mark.asyncio
    async def test_judge_relevance_with_llm(self, self_rag_with_llm, mock_llm):
        """Should use LLM for judgement."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(
                text="RELEVANT: YES\nSUFFICIENT: YES\nCONFIDENCE: 90\nREASONING: Good match"
            )
        )

        results = [MagicMock(content="Document about Python programming")]

        judgement = await self_rag_with_llm.judge_relevance("Python", results)

        assert judgement.is_relevant is True
        assert judgement.is_sufficient == "YES"
        assert judgement.confidence == 90
        mock_llm.acomplete.assert_called_once()

    @pytest.mark.asyncio
    async def test_judge_relevance_llm_failure(self, self_rag_with_llm, mock_llm):
        """Should fallback on LLM failure."""
        mock_llm.acomplete = AsyncMock(side_effect=Exception("LLM error"))

        results = [{"content": "test"}]

        judgement = await self_rag_with_llm.judge_relevance("test", results)

        assert judgement.is_relevant is True  # Fallback behavior
        assert "error" in judgement.reasoning.lower()

    @pytest.mark.asyncio
    async def test_rephrase_query_no_llm(self, self_rag_no_llm):
        """Should return original query without LLM."""
        result = await self_rag_no_llm.rephrase_query("original query")

        assert result == "original query"

    @pytest.mark.asyncio
    async def test_rephrase_query_with_llm(self, self_rag_with_llm, mock_llm):
        """Should use LLM for rephrasing."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="improved search query")
        )

        result = await self_rag_with_llm.rephrase_query(
            "original", "Results were not relevant"
        )

        assert result == "improved search query"

    @pytest.mark.asyncio
    async def test_generate_answer_no_llm(self, self_rag_no_llm):
        """Should concatenate results without LLM."""
        results = [
            MagicMock(content="First doc content"),
            MagicMock(content="Second doc content"),
        ]

        answer = await self_rag_no_llm.generate_answer_from_context("query", results)

        assert "First doc content" in answer
        assert "Second doc content" in answer

    @pytest.mark.asyncio
    async def test_generate_answer_with_llm(self, self_rag_with_llm, mock_llm):
        """Should use LLM for answer generation."""
        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(text="Generated comprehensive answer")
        )

        results = [MagicMock(content="Context")]

        answer = await self_rag_with_llm.generate_answer_from_context("query", results)

        assert answer == "Generated comprehensive answer"

    @pytest.mark.asyncio
    async def test_retrieve_with_self_critique_success(
        self, self_rag_with_llm, mock_llm
    ):
        """Should return results when confidence is high."""
        import uuid

        mock_llm.acomplete = AsyncMock(
            return_value=MagicMock(
                text="RELEVANT: YES\nSUFFICIENT: YES\nCONFIDENCE: 80\nREASONING: Good"
            )
        )

        async def mock_retrieval(**kwargs):
            return [{"content": "result", "node_id": "1"}]

        result = await self_rag_with_llm.retrieve_with_self_critique(
            query="test query",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
            top_k=5,
        )

        assert result.success is True
        assert result.attempts == 1
        assert len(result.results) > 0

    @pytest.mark.asyncio
    async def test_retrieve_with_retry(self, self_rag_with_llm, mock_llm):
        """Should retry when confidence is low."""
        import uuid

        # First attempt: low confidence, second: high confidence
        call_count = 0

        async def mock_acomplete(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First judgement
                return MagicMock(
                    text="RELEVANT: NO\nSUFFICIENT: NO\nCONFIDENCE: 20\nREASONING: Not relevant"
                )
            elif call_count == 2:  # Rephrase
                return MagicMock(text="rephrased query")
            else:  # Second judgement
                return MagicMock(
                    text="RELEVANT: YES\nSUFFICIENT: YES\nCONFIDENCE: 85\nREASONING: Good"
                )

        mock_llm.acomplete = mock_acomplete

        async def mock_retrieval(**kwargs):
            return [{"content": "result"}]

        result = await self_rag_with_llm.retrieve_with_self_critique(
            query="test",
            kb_id=uuid.uuid4(),
            retrieval_func=mock_retrieval,
        )

        assert result.attempts >= 1


class TestGetSelfRAG:
    """Tests for get_self_rag factory function."""

    @pytest.mark.asyncio
    async def test_get_self_rag_defaults(self):
        """Should create SelfRAG with defaults."""
        from airbeeps.rag.self_rag import get_self_rag

        self_rag = await get_self_rag()

        assert self_rag.max_attempts == 3
        assert self_rag.min_confidence == 50
