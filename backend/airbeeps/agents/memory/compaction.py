"""
Memory Compaction Service.

Provides automated compaction of memories to reduce storage and improve retrieval.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.memory.encryption import MemoryEncryption, get_memory_encryption
from airbeeps.agents.memory.models import (
    AgentMemory,
    CompactionStrategyEnum,
    MemoryCompactionLog,
    MemoryTypeEnum,
)
from airbeeps.agents.memory.summarization import MemorySummarizer, get_memory_summarizer
from airbeeps.rag.embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


class MemoryCompactionService:
    """
    Service for compacting and consolidating memories.
    """

    def __init__(
        self,
        session: AsyncSession,
        encryption: MemoryEncryption | None = None,
        summarizer: MemorySummarizer | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        """
        Initialize compaction service.

        Args:
            session: Database session
            encryption: Encryption handler
            summarizer: Memory summarizer
            embedding_service: Service for generating embeddings
        """
        self.session = session
        self._encryption = encryption or get_memory_encryption()
        self._summarizer = summarizer or get_memory_summarizer()
        self._embedding_service = embedding_service

    @property
    def embedding_service(self) -> EmbeddingService:
        """Get embedding service (lazy-loaded)."""
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    async def compact_by_age(
        self,
        user_id: uuid.UUID,
        assistant_id: uuid.UUID | None = None,
        days_old: int = 30,
        memory_types: list[MemoryTypeEnum] | None = None,
        min_memories: int = 5,
        embedding_model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Compact memories older than specified days.

        Args:
            user_id: User whose memories to compact
            assistant_id: Optional assistant filter
            days_old: Minimum age in days for compaction
            memory_types: Types to compact (all if None)
            min_memories: Minimum memories required to trigger compaction
            embedding_model_id: Model for generating embeddings

        Returns:
            Compaction statistics
        """
        start_time = time.time()

        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        # Build query for old memories
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.created_at < cutoff_date,
            AgentMemory.is_compacted.is_(False),
        )

        if assistant_id:
            stmt = stmt.where(AgentMemory.assistant_id == assistant_id)

        if memory_types:
            stmt = stmt.where(AgentMemory.memory_type.in_(memory_types))

        result = await self.session.execute(stmt)
        old_memories = list(result.scalars().all())

        if len(old_memories) < min_memories:
            return {
                "strategy": "AGE",
                "memories_before": len(old_memories),
                "memories_after": len(old_memories),
                "compacted": False,
                "reason": f"Not enough memories ({len(old_memories)} < {min_memories})",
            }

        # Group by memory type for separate summarization
        grouped = {}
        for memory in old_memories:
            key = memory.memory_type
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(memory)

        # Compact each group
        result_memories = []
        source_memory_ids = []

        for memory_type, memories in grouped.items():
            if len(memories) < 2:
                continue

            # Decrypt and prepare for summarization
            decrypted = []
            for m in memories:
                try:
                    content = self._encryption.decrypt(m.content)
                    decrypted.append(
                        {
                            "id": str(m.id),
                            "content": content,
                            "type": m.memory_type.value,
                            "importance": m.importance_score,
                            "created_at": m.created_at.isoformat()
                            if m.created_at
                            else None,
                        }
                    )
                    source_memory_ids.append(str(m.id))
                except ValueError:
                    logger.warning(f"Failed to decrypt memory {m.id}")
                    continue

            if not decrypted:
                continue

            # Summarize
            summary = await self._summarizer.summarize_memories(decrypted)

            # Calculate average importance (weighted by original count)
            total_importance = sum(
                m.importance_score * m.original_count for m in memories
            )
            total_count = sum(m.original_count for m in memories)
            avg_importance = total_importance / total_count if total_count > 0 else 0.5

            # Generate embedding for summary
            embedding = None
            embedding_dim = None
            if embedding_model_id:
                try:
                    embed_model = await self.embedding_service.get_embed_model(
                        embedding_model_id
                    )
                    embedding = await embed_model._aget_text_embedding(summary)
                    embedding_dim = len(embedding) if embedding else None
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {e}")

            # Create compacted memory
            encrypted_summary = self._encryption.encrypt(summary)
            compacted_memory = AgentMemory(
                assistant_id=memories[0].assistant_id,
                user_id=user_id,
                memory_type=memory_type,
                content=encrypted_summary,
                embedding=embedding,
                embedding_dim=embedding_dim,
                importance_score=min(1.0, avg_importance + 0.1),  # Boost importance
                metadata={
                    "compaction_strategy": "AGE",
                    "source_count": len(memories),
                    "compacted_from_date": cutoff_date.isoformat(),
                },
                is_encrypted=True,
                is_compacted=True,
                parent_memory_ids=[str(m.id) for m in memories],
                compaction_date=datetime.utcnow(),
                original_count=total_count,
            )

            self.session.add(compacted_memory)
            result_memories.append(compacted_memory)

            # Delete original memories
            delete_stmt = delete(AgentMemory).where(
                AgentMemory.id.in_([m.id for m in memories])
            )
            await self.session.execute(delete_stmt)

        # Log compaction
        duration_ms = int((time.time() - start_time) * 1000)
        log = MemoryCompactionLog(
            user_id=user_id,
            assistant_id=assistant_id,
            strategy=CompactionStrategyEnum.AGE,
            memories_before=len(old_memories),
            memories_after=len(result_memories),
            memories_merged=len(old_memories) - len(result_memories),
            memories_summarized=len(result_memories),
            duration_ms=duration_ms,
            result_memory_ids=[str(m.id) for m in result_memories],
            source_memory_ids=source_memory_ids,
        )
        self.session.add(log)

        await self.session.commit()

        return {
            "strategy": "AGE",
            "memories_before": len(old_memories),
            "memories_after": len(result_memories),
            "memories_merged": len(old_memories) - len(result_memories),
            "compacted": True,
            "duration_ms": duration_ms,
        }

    async def compact_by_similarity(
        self,
        user_id: uuid.UUID,
        assistant_id: uuid.UUID | None = None,
        similarity_threshold: float = 0.85,
        max_group_size: int = 10,
        embedding_model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Merge semantically similar memories.

        Args:
            user_id: User whose memories to compact
            assistant_id: Optional assistant filter
            similarity_threshold: Minimum similarity for merging (0-1)
            max_group_size: Maximum memories per merged group
            embedding_model_id: Model for embeddings

        Returns:
            Compaction statistics
        """
        start_time = time.time()

        # Get memories with embeddings
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.embedding.isnot(None),
            AgentMemory.is_compacted.is_(False),
        )

        if assistant_id:
            stmt = stmt.where(AgentMemory.assistant_id == assistant_id)

        result = await self.session.execute(stmt)
        memories = list(result.scalars().all())

        if len(memories) < 2:
            return {
                "strategy": "SIMILARITY",
                "memories_before": len(memories),
                "memories_after": len(memories),
                "compacted": False,
                "reason": "Not enough memories with embeddings",
            }

        # Find similar groups using greedy clustering
        groups = self._find_similar_groups(
            memories, similarity_threshold, max_group_size
        )

        if not groups:
            return {
                "strategy": "SIMILARITY",
                "memories_before": len(memories),
                "memories_after": len(memories),
                "compacted": False,
                "reason": "No similar groups found",
            }

        # Merge each group
        result_memories = []
        source_memory_ids = []
        deleted_count = 0

        for group in groups:
            if len(group) < 2:
                continue

            # Decrypt memories
            decrypted = []
            for m in group:
                try:
                    content = self._encryption.decrypt(m.content)
                    decrypted.append(
                        {
                            "id": str(m.id),
                            "content": content,
                            "type": m.memory_type.value,
                            "importance": m.importance_score,
                        }
                    )
                    source_memory_ids.append(str(m.id))
                except ValueError:
                    continue

            if len(decrypted) < 2:
                continue

            # Summarize
            summary = await self._summarizer.summarize_memories(decrypted)

            # Calculate weighted average importance
            total_importance = sum(m.importance_score * m.original_count for m in group)
            total_count = sum(m.original_count for m in group)
            avg_importance = total_importance / total_count if total_count > 0 else 0.5

            # Average embeddings
            avg_embedding = self._average_embeddings(
                [m.embedding for m in group if m.embedding]
            )

            # Create merged memory
            encrypted_summary = self._encryption.encrypt(summary)
            merged_memory = AgentMemory(
                assistant_id=group[0].assistant_id,
                user_id=user_id,
                memory_type=group[0].memory_type,
                content=encrypted_summary,
                embedding=avg_embedding,
                embedding_dim=len(avg_embedding) if avg_embedding else None,
                importance_score=min(1.0, avg_importance + 0.05),
                metadata={
                    "compaction_strategy": "SIMILARITY",
                    "source_count": len(group),
                    "similarity_threshold": similarity_threshold,
                },
                is_encrypted=True,
                is_compacted=True,
                parent_memory_ids=[str(m.id) for m in group],
                compaction_date=datetime.utcnow(),
                original_count=total_count,
            )

            self.session.add(merged_memory)
            result_memories.append(merged_memory)

            # Delete original memories
            delete_stmt = delete(AgentMemory).where(
                AgentMemory.id.in_([m.id for m in group])
            )
            await self.session.execute(delete_stmt)
            deleted_count += len(group)

        # Log compaction
        duration_ms = int((time.time() - start_time) * 1000)
        log = MemoryCompactionLog(
            user_id=user_id,
            assistant_id=assistant_id,
            strategy=CompactionStrategyEnum.SIMILARITY,
            memories_before=len(memories),
            memories_after=len(memories) - deleted_count + len(result_memories),
            memories_merged=deleted_count,
            memories_summarized=len(result_memories),
            duration_ms=duration_ms,
            result_memory_ids=[str(m.id) for m in result_memories],
            source_memory_ids=source_memory_ids,
        )
        self.session.add(log)

        await self.session.commit()

        return {
            "strategy": "SIMILARITY",
            "memories_before": len(memories),
            "memories_after": len(memories) - deleted_count + len(result_memories),
            "memories_merged": deleted_count,
            "groups_created": len(result_memories),
            "compacted": True,
            "duration_ms": duration_ms,
        }

    async def compact_by_importance(
        self,
        user_id: uuid.UUID,
        assistant_id: uuid.UUID | None = None,
        importance_threshold: float = 0.3,
        min_memories: int = 10,
        embedding_model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Summarize low-importance memories.

        Args:
            user_id: User whose memories to compact
            assistant_id: Optional assistant filter
            importance_threshold: Maximum importance for compaction
            min_memories: Minimum low-importance memories required
            embedding_model_id: Model for embeddings

        Returns:
            Compaction statistics
        """
        start_time = time.time()

        # Get low-importance memories
        stmt = select(AgentMemory).where(
            AgentMemory.user_id == user_id,
            AgentMemory.importance_score < importance_threshold,
            AgentMemory.is_compacted.is_(False),
        )

        if assistant_id:
            stmt = stmt.where(AgentMemory.assistant_id == assistant_id)

        result = await self.session.execute(stmt)
        low_importance = list(result.scalars().all())

        if len(low_importance) < min_memories:
            return {
                "strategy": "IMPORTANCE",
                "memories_before": len(low_importance),
                "memories_after": len(low_importance),
                "compacted": False,
                "reason": f"Not enough low-importance memories ({len(low_importance)} < {min_memories})",
            }

        # Group by type
        grouped = {}
        for memory in low_importance:
            key = memory.memory_type
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(memory)

        result_memories = []
        source_memory_ids = []

        for memory_type, memories in grouped.items():
            if len(memories) < 3:
                continue

            # Decrypt and prepare
            decrypted = []
            for m in memories:
                try:
                    content = self._encryption.decrypt(m.content)
                    decrypted.append(
                        {
                            "id": str(m.id),
                            "content": content,
                            "type": m.memory_type.value,
                            "importance": m.importance_score,
                        }
                    )
                    source_memory_ids.append(str(m.id))
                except ValueError:
                    continue

            if not decrypted:
                continue

            # Summarize
            summary = await self._summarizer.summarize_memories(decrypted)

            # Generate embedding
            embedding = None
            embedding_dim = None
            if embedding_model_id:
                try:
                    embed_model = await self.embedding_service.get_embed_model(
                        embedding_model_id
                    )
                    embedding = await embed_model._aget_text_embedding(summary)
                    embedding_dim = len(embedding) if embedding else None
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {e}")

            # Create summary memory with boosted importance
            encrypted_summary = self._encryption.encrypt(summary)
            summary_memory = AgentMemory(
                assistant_id=memories[0].assistant_id,
                user_id=user_id,
                memory_type=memory_type,
                content=encrypted_summary,
                embedding=embedding,
                embedding_dim=embedding_dim,
                importance_score=0.4,  # Slight boost from low-importance
                metadata={
                    "compaction_strategy": "IMPORTANCE",
                    "source_count": len(memories),
                    "original_importance_range": f"{min(m.importance_score for m in memories):.2f}-{max(m.importance_score for m in memories):.2f}",
                },
                is_encrypted=True,
                is_compacted=True,
                parent_memory_ids=[str(m.id) for m in memories],
                compaction_date=datetime.utcnow(),
                original_count=sum(m.original_count for m in memories),
            )

            self.session.add(summary_memory)
            result_memories.append(summary_memory)

            # Delete original memories
            delete_stmt = delete(AgentMemory).where(
                AgentMemory.id.in_([m.id for m in memories])
            )
            await self.session.execute(delete_stmt)

        # Log compaction
        duration_ms = int((time.time() - start_time) * 1000)
        log = MemoryCompactionLog(
            user_id=user_id,
            assistant_id=assistant_id,
            strategy=CompactionStrategyEnum.IMPORTANCE,
            memories_before=len(low_importance),
            memories_after=len(result_memories),
            memories_merged=len(low_importance) - len(result_memories),
            memories_summarized=len(result_memories),
            duration_ms=duration_ms,
            result_memory_ids=[str(m.id) for m in result_memories],
            source_memory_ids=source_memory_ids,
        )
        self.session.add(log)

        await self.session.commit()

        return {
            "strategy": "IMPORTANCE",
            "memories_before": len(low_importance),
            "memories_after": len(result_memories),
            "memories_merged": len(low_importance) - len(result_memories),
            "compacted": True,
            "duration_ms": duration_ms,
        }

    async def run_hybrid_compaction(
        self,
        user_id: uuid.UUID,
        assistant_id: uuid.UUID | None = None,
        embedding_model_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run all compaction strategies in sequence.

        Args:
            user_id: User whose memories to compact
            assistant_id: Optional assistant filter
            embedding_model_id: Model for embeddings

        Returns:
            Combined compaction statistics
        """
        results = []

        # 1. Age-based compaction first
        age_result = await self.compact_by_age(
            user_id=user_id,
            assistant_id=assistant_id,
            days_old=30,
            embedding_model_id=embedding_model_id,
        )
        results.append(age_result)

        # 2. Similarity-based compaction
        similarity_result = await self.compact_by_similarity(
            user_id=user_id,
            assistant_id=assistant_id,
            embedding_model_id=embedding_model_id,
        )
        results.append(similarity_result)

        # 3. Importance-based compaction
        importance_result = await self.compact_by_importance(
            user_id=user_id,
            assistant_id=assistant_id,
            embedding_model_id=embedding_model_id,
        )
        results.append(importance_result)

        # Combine statistics
        total_merged = sum(r.get("memories_merged", 0) for r in results)
        any_compacted = any(r.get("compacted", False) for r in results)

        return {
            "strategy": "HYBRID",
            "compacted": any_compacted,
            "total_memories_merged": total_merged,
            "by_strategy": {
                "AGE": age_result,
                "SIMILARITY": similarity_result,
                "IMPORTANCE": importance_result,
            },
        }

    async def get_compaction_stats(
        self, user_id: uuid.UUID, assistant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """Get compaction statistics for a user."""
        stmt = select(MemoryCompactionLog).where(MemoryCompactionLog.user_id == user_id)

        if assistant_id:
            stmt = stmt.where(MemoryCompactionLog.assistant_id == assistant_id)

        result = await self.session.execute(stmt)
        logs = list(result.scalars().all())

        if not logs:
            return {
                "total_compactions": 0,
                "total_memories_merged": 0,
                "by_strategy": {},
            }

        by_strategy = {}
        for log in logs:
            strategy = log.strategy.value
            if strategy not in by_strategy:
                by_strategy[strategy] = {
                    "count": 0,
                    "memories_merged": 0,
                    "avg_duration_ms": 0,
                }
            by_strategy[strategy]["count"] += 1
            by_strategy[strategy]["memories_merged"] += log.memories_merged
            by_strategy[strategy]["avg_duration_ms"] = (
                by_strategy[strategy]["avg_duration_ms"] + (log.duration_ms or 0)
            ) / by_strategy[strategy]["count"]

        return {
            "total_compactions": len(logs),
            "total_memories_merged": sum(l.memories_merged for l in logs),
            "by_strategy": by_strategy,
            "last_compaction": max(l.created_at for l in logs).isoformat()
            if logs
            else None,
        }

    def _find_similar_groups(
        self,
        memories: list[AgentMemory],
        threshold: float,
        max_size: int,
    ) -> list[list[AgentMemory]]:
        """Find groups of similar memories using greedy clustering."""
        if not memories:
            return []

        groups = []
        used = set()

        for i, memory in enumerate(memories):
            if i in used:
                continue

            group = [memory]
            used.add(i)

            for j, other in enumerate(memories[i + 1 :], start=i + 1):
                if j in used or len(group) >= max_size:
                    continue

                if memory.embedding and other.embedding:
                    sim = self._cosine_similarity(memory.embedding, other.embedding)
                    if sim >= threshold:
                        group.append(other)
                        used.add(j)

            if len(group) >= 2:
                groups.append(group)

        return groups

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    @staticmethod
    def _average_embeddings(embeddings: list[list[float]]) -> list[float] | None:
        """Average multiple embedding vectors."""
        if not embeddings:
            return None

        dim = len(embeddings[0])
        avg = [0.0] * dim

        for emb in embeddings:
            if len(emb) != dim:
                continue
            for i, v in enumerate(emb):
                avg[i] += v

        n = len(embeddings)
        return [v / n for v in avg]


async def create_compaction_service(session: AsyncSession) -> MemoryCompactionService:
    """Create a compaction service instance with given session."""
    return MemoryCompactionService(session=session)
