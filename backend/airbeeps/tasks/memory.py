"""
Celery tasks for memory compaction and management.

These tasks handle background memory operations:
- Memory compaction (merging old/similar memories)
- Memory cleanup (removing expired memories)
- Memory export for GDPR requests
"""

import asyncio
import logging
from datetime import UTC

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


try:
    from celery import shared_task

    @shared_task(
        bind=True,
        name="airbeeps.tasks.compact_memories",
        max_retries=2,
        default_retry_delay=300,
        soft_time_limit=1800,  # 30 min
    )
    def compact_memories(
        self,
        user_id: str | None = None,
        strategy: str = "hybrid",
        max_memories: int = 100,
    ):
        """
        Run memory compaction.

        Args:
            user_id: Optional user ID to compact (all users if None)
            strategy: Compaction strategy (age, similarity, importance, hybrid)
            max_memories: Maximum memories to process per run
        """
        logger.info(f"Starting memory compaction: user={user_id}, strategy={strategy}")

        try:
            result = _run_async(
                _compact_memories_async(user_id, strategy, max_memories)
            )
            logger.info(f"Memory compaction completed: {result}")
            return result
        except Exception as e:
            logger.error(f"Memory compaction failed: {e}", exc_info=True)
            raise self.retry(exc=e)

    @shared_task(
        bind=True,
        name="airbeeps.tasks.cleanup_expired_memories",
        max_retries=1,
    )
    def cleanup_expired_memories(self):
        """
        Clean up memories past their retention period.

        This task should run periodically via Celery Beat.
        """
        logger.info("Starting memory cleanup")

        try:
            result = _run_async(_cleanup_memories_async())
            logger.info(f"Memory cleanup completed: {result}")
            return result
        except Exception as e:
            logger.error(f"Memory cleanup failed: {e}", exc_info=True)
            raise

    @shared_task(
        name="airbeeps.tasks.export_user_memories",
        soft_time_limit=600,  # 10 min
    )
    def export_user_memories(user_id: str, format: str = "json"):
        """
        Export all memories for a user (GDPR data export).

        Args:
            user_id: User ID to export
            format: Export format (json, csv)

        Returns:
            Path to exported file
        """
        logger.info(f"Exporting memories for user {user_id}")
        return _run_async(_export_memories_async(user_id, format))

except ImportError:

    def compact_memories(*args, **kwargs):
        raise RuntimeError("Celery is not installed")

    def cleanup_expired_memories(*args, **kwargs):
        raise RuntimeError("Celery is not installed")

    def export_user_memories(*args, **kwargs):
        raise RuntimeError("Celery is not installed")


async def _compact_memories_async(
    user_id: str | None,
    strategy: str,
    max_memories: int,
) -> dict:
    """Async implementation of memory compaction."""
    from uuid import UUID

    from airbeeps.agents.memory.compaction import MemoryCompactionService
    from airbeeps.database import get_async_session_context

    async with get_async_session_context() as session:
        service = MemoryCompactionService(session)

        user_uuid = UUID(user_id) if user_id else None

        if strategy == "hybrid":
            result = await service.run_hybrid_compaction(
                user_id=user_uuid,
                max_memories=max_memories,
            )
        elif strategy == "age":
            result = await service.compact_by_age(
                user_id=user_uuid,
                max_memories=max_memories,
            )
        elif strategy == "similarity":
            result = await service.compact_by_similarity(
                user_id=user_uuid,
                max_memories=max_memories,
            )
        elif strategy == "importance":
            result = await service.compact_by_importance(
                user_id=user_uuid,
                max_memories=max_memories,
            )
        else:
            raise ValueError(f"Unknown compaction strategy: {strategy}")

        return result


async def _cleanup_memories_async() -> dict:
    """Async implementation of memory cleanup."""
    from datetime import datetime

    from sqlalchemy import delete

    from airbeeps.agents.memory.models import AgentMemory
    from airbeeps.database import get_async_session_context

    async with get_async_session_context() as session:
        now = datetime.now(UTC)

        # Find and delete expired memories
        stmt = (
            delete(AgentMemory)
            .where(AgentMemory.expires_at < now)
            .returning(AgentMemory.id)
        )

        result = await session.execute(stmt)
        deleted_ids = result.scalars().all()
        await session.commit()

        return {
            "deleted_count": len(deleted_ids),
            "timestamp": now.isoformat(),
        }


async def _export_memories_async(user_id: str, format: str) -> str:
    """Async implementation of memory export."""
    import json
    from datetime import datetime
    from pathlib import Path
    from uuid import UUID

    from sqlalchemy import select

    from airbeeps.agents.memory.encryption import MemoryEncryption
    from airbeeps.agents.memory.models import AgentMemory
    from airbeeps.config import settings
    from airbeeps.database import get_async_session_context

    user_uuid = UUID(user_id)

    async with get_async_session_context() as session:
        # Fetch all user memories
        stmt = select(AgentMemory).where(AgentMemory.user_id == user_uuid)
        result = await session.execute(stmt)
        memories = result.scalars().all()

        # Decrypt and format
        encryption = MemoryEncryption()
        export_data = []

        for memory in memories:
            content = memory.content
            if memory.encrypted and settings.MEMORY_ENCRYPTION_KEY:
                try:
                    content = encryption.decrypt(content)
                except Exception:
                    content = "[encrypted - decryption failed]"

            export_data.append(
                {
                    "id": str(memory.id),
                    "content": content,
                    "memory_type": memory.memory_type,
                    "importance": memory.importance,
                    "created_at": memory.created_at.isoformat()
                    if memory.created_at
                    else None,
                    "expires_at": memory.expires_at.isoformat()
                    if memory.expires_at
                    else None,
                }
            )

        # Write to file
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        export_dir = Path(settings.LOCAL_STORAGE_ROOT) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        if format == "json":
            export_path = export_dir / f"memories_{user_id}_{timestamp}.json"
            with open(export_path, "w") as f:
                json.dump(export_data, f, indent=2)
        else:
            # CSV format
            import csv

            export_path = export_dir / f"memories_{user_id}_{timestamp}.csv"
            with open(export_path, "w", newline="") as f:
                if export_data:
                    writer = csv.DictWriter(f, fieldnames=export_data[0].keys())
                    writer.writeheader()
                    writer.writerows(export_data)

        return str(export_path)
