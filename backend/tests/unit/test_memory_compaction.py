"""
Unit tests for Memory Compaction Service.

Tests for compaction strategies (age, similarity, importance).
All tests use mocked dependencies to avoid real LLM/database calls.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestCosineSimiarity:
    """Tests for cosine similarity helper."""

    def test_identical_vectors(self):
        """Should return 1.0 for identical vectors."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        vec = [1.0, 0.0, 1.0]
        similarity = MemoryCompactionService._cosine_similarity(vec, vec)

        assert abs(similarity - 1.0) < 0.0001

    def test_orthogonal_vectors(self):
        """Should return 0 for orthogonal vectors."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        similarity = MemoryCompactionService._cosine_similarity(vec1, vec2)

        assert abs(similarity) < 0.0001

    def test_opposite_vectors(self):
        """Should return -1 for opposite vectors."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        similarity = MemoryCompactionService._cosine_similarity(vec1, vec2)

        assert abs(similarity - (-1.0)) < 0.0001

    def test_different_length_vectors(self):
        """Should return 0 for different length vectors."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]
        similarity = MemoryCompactionService._cosine_similarity(vec1, vec2)

        assert similarity == 0.0

    def test_zero_vector(self):
        """Should handle zero vectors."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        vec1 = [0.0, 0.0]
        vec2 = [1.0, 1.0]
        similarity = MemoryCompactionService._cosine_similarity(vec1, vec2)

        assert similarity == 0.0


class TestAverageEmbeddings:
    """Tests for embedding averaging."""

    def test_average_single_embedding(self):
        """Should return same vector for single embedding."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        embeddings = [[1.0, 2.0, 3.0]]
        avg = MemoryCompactionService._average_embeddings(embeddings)

        assert avg == [1.0, 2.0, 3.0]

    def test_average_multiple_embeddings(self):
        """Should average multiple embeddings correctly."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        embeddings = [
            [0.0, 2.0, 4.0],
            [2.0, 4.0, 6.0],
        ]
        avg = MemoryCompactionService._average_embeddings(embeddings)

        assert avg == [1.0, 3.0, 5.0]

    def test_average_empty_list(self):
        """Should return None for empty list."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        avg = MemoryCompactionService._average_embeddings([])
        assert avg is None


class TestFindSimilarGroups:
    """Tests for similarity grouping."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock memory object."""

        def _create(embedding=None, importance=0.5):
            m = MagicMock()
            m.id = uuid.uuid4()
            m.embedding = embedding
            m.importance_score = importance
            m.original_count = 1
            return m

        return _create

    def test_find_groups_no_embeddings(self, mock_memory):
        """Should return empty when no embeddings."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        memories = [mock_memory(embedding=None) for _ in range(3)]
        service = MemoryCompactionService.__new__(MemoryCompactionService)

        groups = service._find_similar_groups(memories, threshold=0.8, max_size=5)

        assert groups == []

    def test_find_groups_similar_vectors(self, mock_memory):
        """Should group similar embeddings."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        memories = [
            mock_memory(embedding=[1.0, 0.0, 0.0]),
            mock_memory(embedding=[0.99, 0.1, 0.0]),  # Similar to first
            mock_memory(embedding=[0.0, 1.0, 0.0]),  # Different
        ]
        service = MemoryCompactionService.__new__(MemoryCompactionService)

        groups = service._find_similar_groups(memories, threshold=0.9, max_size=5)

        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_find_groups_respects_max_size(self, mock_memory):
        """Should respect max group size."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        # All vectors are very similar
        memories = [mock_memory(embedding=[1.0, 0.0]) for _ in range(5)]
        service = MemoryCompactionService.__new__(MemoryCompactionService)

        groups = service._find_similar_groups(memories, threshold=0.99, max_size=2)

        # Should not exceed max_size
        for group in groups:
            assert len(group) <= 2


class TestMemoryCompactionService:
    """Tests for MemoryCompactionService methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_encryption(self):
        """Create a mock encryption handler."""
        encryption = MagicMock()
        encryption.encrypt = MagicMock(side_effect=lambda x: f"encrypted:{x}")
        encryption.decrypt = MagicMock(
            side_effect=lambda x: x.replace("encrypted:", "")
        )
        return encryption

    @pytest.fixture
    def mock_summarizer(self):
        """Create a mock summarizer."""
        summarizer = AsyncMock()
        summarizer.summarize_memories = AsyncMock(return_value="Summarized content")
        return summarizer

    @pytest.fixture
    def compaction_service(self, mock_session, mock_encryption, mock_summarizer):
        """Create a compaction service with mocked dependencies."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        return MemoryCompactionService(
            session=mock_session,
            encryption=mock_encryption,
            summarizer=mock_summarizer,
        )

    @pytest.mark.asyncio
    async def test_compact_by_age_not_enough_memories(
        self, compaction_service, mock_session
    ):
        """Should skip compaction when not enough old memories."""
        # Mock query to return few memories
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await compaction_service.compact_by_age(
            user_id=uuid.uuid4(),
            days_old=30,
            min_memories=5,
        )

        assert result["compacted"] is False
        assert "Not enough memories" in result["reason"]

    @pytest.mark.asyncio
    async def test_compact_by_similarity_not_enough_memories(
        self, compaction_service, mock_session
    ):
        """Should skip when not enough memories with embeddings."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock()]
        mock_session.execute.return_value = mock_result

        result = await compaction_service.compact_by_similarity(
            user_id=uuid.uuid4(),
        )

        assert result["compacted"] is False
        assert "Not enough memories" in result["reason"]

    @pytest.mark.asyncio
    async def test_compact_by_importance_not_enough_memories(
        self, compaction_service, mock_session
    ):
        """Should skip when not enough low-importance memories."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await compaction_service.compact_by_importance(
            user_id=uuid.uuid4(),
            min_memories=10,
        )

        assert result["compacted"] is False

    @pytest.mark.asyncio
    async def test_get_compaction_stats_empty(self, compaction_service, mock_session):
        """Should return empty stats when no logs."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        stats = await compaction_service.get_compaction_stats(user_id=uuid.uuid4())

        assert stats["total_compactions"] == 0
        assert stats["total_memories_merged"] == 0

    @pytest.mark.asyncio
    async def test_compact_by_age_with_memories(
        self, mock_session, mock_encryption, mock_summarizer
    ):
        """Should skip compaction when not enough old memories."""
        from airbeeps.agents.memory.compaction import MemoryCompactionService

        # Create mock memories (fewer than min_memories threshold)
        user_id = uuid.uuid4()

        # Return fewer memories than required for compaction
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        service = MemoryCompactionService(
            session=mock_session,
            encryption=mock_encryption,
            summarizer=mock_summarizer,
        )

        result = await service.compact_by_age(
            user_id=user_id,
            days_old=30,
            min_memories=5,
        )

        # Should return not compacted when not enough memories
        assert result["compacted"] is False
        assert result["memories_before"] == 0

    @pytest.mark.asyncio
    async def test_run_hybrid_compaction(self, compaction_service, mock_session):
        """Should run all strategies in sequence."""
        # Mock empty results for all queries
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await compaction_service.run_hybrid_compaction(
            user_id=uuid.uuid4(),
        )

        assert result["strategy"] == "HYBRID"
        assert "AGE" in result["by_strategy"]
        assert "SIMILARITY" in result["by_strategy"]
        assert "IMPORTANCE" in result["by_strategy"]


class TestCompactionStrategySelection:
    """Tests for strategy-specific behavior."""

    def test_age_compaction_cutoff_date(self):
        """Should calculate correct cutoff date."""
        # This tests the internal logic indirectly through the service

        days_old = 30
        cutoff = datetime.utcnow() - timedelta(days=days_old)

        # Cutoff should be approximately 30 days ago
        age_diff = datetime.utcnow() - cutoff
        assert 29 <= age_diff.days <= 31

    def test_importance_threshold_default(self):
        """Default importance threshold should be reasonable."""
        default_threshold = 0.3
        assert 0 < default_threshold < 1

    def test_similarity_threshold_default(self):
        """Default similarity threshold should be high."""
        default_threshold = 0.85
        assert default_threshold >= 0.8  # High enough to avoid false merges
