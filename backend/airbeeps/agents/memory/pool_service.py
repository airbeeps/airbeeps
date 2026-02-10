"""
Shared Memory Pool Service.

Provides management of shared memory pools for collaborative knowledge.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.agents.memory.encryption import MemoryEncryption, get_memory_encryption
from airbeeps.agents.memory.models import (
    AgentMemory,
    PoolAccessLevelEnum,
    PoolTypeEnum,
    SharedMemoryPool,
    SharedPoolMember,
    SharedPoolMemory,
)

logger = logging.getLogger(__name__)


class SharedPoolService:
    """
    Service for managing shared memory pools.
    """

    def __init__(
        self,
        session: AsyncSession,
        encryption: MemoryEncryption | None = None,
    ):
        """
        Initialize shared pool service.

        Args:
            session: Database session
            encryption: Encryption handler
        """
        self.session = session
        self._encryption = encryption or get_memory_encryption()

    # =========================================================================
    # Pool Management
    # =========================================================================

    async def create_pool(
        self,
        name: str,
        owner_id: uuid.UUID,
        pool_type: PoolTypeEnum = PoolTypeEnum.TEAM,
        access_level: PoolAccessLevelEnum = PoolAccessLevelEnum.READ_ONLY,
        description: str | None = None,
        assistant_id: uuid.UUID | None = None,
        max_memories: int = 1000,
        auto_share_enabled: bool = False,
    ) -> SharedMemoryPool:
        """
        Create a new shared memory pool.

        Args:
            name: Pool name
            owner_id: Owner user ID
            pool_type: Type of pool
            access_level: Default access level for members
            description: Pool description
            assistant_id: Associated assistant
            max_memories: Maximum memories in pool
            auto_share_enabled: Whether to auto-share new memories

        Returns:
            Created pool
        """
        pool = SharedMemoryPool(
            name=name,
            description=description,
            pool_type=pool_type,
            access_level=access_level,
            owner_id=owner_id,
            assistant_id=assistant_id,
            max_memories=max_memories,
            auto_share_enabled=auto_share_enabled,
        )

        self.session.add(pool)

        # Add owner as a member with READ_WRITE access
        owner_member = SharedPoolMember(
            pool_id=pool.id,
            user_id=owner_id,
            access_level=PoolAccessLevelEnum.READ_WRITE,
        )
        self.session.add(owner_member)

        await self.session.commit()
        await self.session.refresh(pool)

        logger.info(f"Created shared pool '{name}' (id={pool.id})")
        return pool

    async def get_pool(
        self, pool_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SharedMemoryPool | None:
        """
        Get a pool by ID.

        Args:
            pool_id: Pool ID
            user_id: Optional user for access check

        Returns:
            Pool if found and accessible, None otherwise
        """
        stmt = (
            select(SharedMemoryPool)
            .options(selectinload(SharedMemoryPool.members))
            .where(SharedMemoryPool.id == pool_id, SharedMemoryPool.is_active.is_(True))
        )
        result = await self.session.execute(stmt)
        pool = result.scalars().first()

        if not pool:
            return None

        # Check access if user_id provided
        if user_id and not await self._can_access_pool(pool, user_id):
            return None

        return pool

    async def list_pools(
        self,
        user_id: uuid.UUID,
        pool_type: PoolTypeEnum | None = None,
        include_public: bool = True,
    ) -> list[SharedMemoryPool]:
        """
        List pools accessible to a user.

        Args:
            user_id: User ID
            pool_type: Filter by pool type
            include_public: Include public pools

        Returns:
            List of accessible pools
        """
        # Get pools where user is a member
        member_stmt = select(SharedPoolMember.pool_id).where(
            SharedPoolMember.user_id == user_id
        )
        member_result = await self.session.execute(member_stmt)
        member_pool_ids = [row[0] for row in member_result]

        # Build main query
        conditions = [
            SharedMemoryPool.is_active.is_(True),
        ]

        if pool_type:
            conditions.append(SharedMemoryPool.pool_type == pool_type)

        # User is member, owner, or pool is public
        access_conditions = [
            SharedMemoryPool.id.in_(member_pool_ids),
            SharedMemoryPool.owner_id == user_id,
        ]
        if include_public:
            access_conditions.append(SharedMemoryPool.pool_type == PoolTypeEnum.PUBLIC)

        from sqlalchemy import or_

        conditions.append(or_(*access_conditions))

        stmt = (
            select(SharedMemoryPool)
            .options(selectinload(SharedMemoryPool.members))
            .where(*conditions)
            .order_by(SharedMemoryPool.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_pool(
        self,
        pool_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        access_level: PoolAccessLevelEnum | None = None,
        max_memories: int | None = None,
        auto_share_enabled: bool | None = None,
    ) -> SharedMemoryPool | None:
        """
        Update a pool (owner only).

        Returns:
            Updated pool or None if not found/unauthorized
        """
        pool = await self.get_pool(pool_id)
        if not pool or pool.owner_id != user_id:
            return None

        if name is not None:
            pool.name = name
        if description is not None:
            pool.description = description
        if access_level is not None:
            pool.access_level = access_level
        if max_memories is not None:
            pool.max_memories = max_memories
        if auto_share_enabled is not None:
            pool.auto_share_enabled = auto_share_enabled

        await self.session.commit()
        await self.session.refresh(pool)
        return pool

    async def delete_pool(self, pool_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Delete a pool (owner only).

        Returns:
            True if deleted, False otherwise
        """
        pool = await self.get_pool(pool_id)
        if not pool or pool.owner_id != user_id:
            return False

        # Soft delete
        pool.is_active = False
        await self.session.commit()

        logger.info(f"Deleted shared pool {pool_id}")
        return True

    # =========================================================================
    # Member Management
    # =========================================================================

    async def add_member(
        self,
        pool_id: uuid.UUID,
        user_id: uuid.UUID,
        added_by_id: uuid.UUID,
        access_level: PoolAccessLevelEnum | None = None,
    ) -> SharedPoolMember | None:
        """
        Add a member to a pool.

        Args:
            pool_id: Pool ID
            user_id: User to add
            added_by_id: User adding the member (must be owner)
            access_level: Optional access level override

        Returns:
            Created member or None if unauthorized
        """
        pool = await self.get_pool(pool_id)
        if not pool or pool.owner_id != added_by_id:
            return None

        # Check if already a member
        existing = await self._get_member(pool_id, user_id)
        if existing:
            return existing

        member = SharedPoolMember(
            pool_id=pool_id,
            user_id=user_id,
            access_level=access_level,
        )
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)

        logger.info(f"Added user {user_id} to pool {pool_id}")
        return member

    async def remove_member(
        self,
        pool_id: uuid.UUID,
        user_id: uuid.UUID,
        removed_by_id: uuid.UUID,
    ) -> bool:
        """
        Remove a member from a pool.

        Args:
            pool_id: Pool ID
            user_id: User to remove
            removed_by_id: User removing (must be owner or self)

        Returns:
            True if removed
        """
        pool = await self.get_pool(pool_id)
        if not pool:
            return False

        # Can remove if owner or removing self
        if pool.owner_id != removed_by_id and user_id != removed_by_id:
            return False

        # Cannot remove owner
        if user_id == pool.owner_id:
            return False

        stmt = delete(SharedPoolMember).where(
            SharedPoolMember.pool_id == pool_id,
            SharedPoolMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount > 0

    async def list_members(self, pool_id: uuid.UUID) -> list[SharedPoolMember]:
        """List all members of a pool."""
        stmt = (
            select(SharedPoolMember)
            .where(SharedPoolMember.pool_id == pool_id)
            .order_by(SharedPoolMember.joined_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Memory Sharing
    # =========================================================================

    async def add_memory_to_pool(
        self,
        pool_id: uuid.UUID,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SharedPoolMemory | None:
        """
        Add a memory to a shared pool.

        Args:
            pool_id: Pool ID
            memory_id: Memory to share
            user_id: User sharing (must own memory and have write access)

        Returns:
            Created association or None if unauthorized
        """
        # Check pool access
        pool = await self.get_pool(pool_id, user_id)
        if not pool:
            return None

        access = await self._get_user_access_level(pool, user_id)
        if access != PoolAccessLevelEnum.READ_WRITE:
            return None

        # Check memory ownership
        memory_stmt = select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.user_id == user_id,
        )
        memory_result = await self.session.execute(memory_stmt)
        memory = memory_result.scalars().first()
        if not memory:
            return None

        # Check pool capacity
        count_stmt = select(func.count()).where(SharedPoolMemory.pool_id == pool_id)
        count_result = await self.session.execute(count_stmt)
        current_count = count_result.scalar() or 0
        if current_count >= pool.max_memories:
            logger.warning(f"Pool {pool_id} at capacity ({pool.max_memories})")
            return None

        # Check if already shared
        existing_stmt = select(SharedPoolMemory).where(
            SharedPoolMemory.pool_id == pool_id,
            SharedPoolMemory.memory_id == memory_id,
        )
        existing_result = await self.session.execute(existing_stmt)
        if existing_result.scalars().first():
            return None  # Already shared

        # Create association
        pool_memory = SharedPoolMemory(
            pool_id=pool_id,
            memory_id=memory_id,
            shared_by_id=user_id,
        )
        self.session.add(pool_memory)
        await self.session.commit()
        await self.session.refresh(pool_memory)

        logger.info(f"Shared memory {memory_id} to pool {pool_id}")
        return pool_memory

    async def remove_memory_from_pool(
        self,
        pool_id: uuid.UUID,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """
        Remove a memory from a shared pool.

        Args:
            pool_id: Pool ID
            memory_id: Memory to remove
            user_id: User removing (must be pool owner or sharer)

        Returns:
            True if removed
        """
        pool = await self.get_pool(pool_id)
        if not pool:
            return False

        # Get the shared memory entry
        stmt = select(SharedPoolMemory).where(
            SharedPoolMemory.pool_id == pool_id,
            SharedPoolMemory.memory_id == memory_id,
        )
        result = await self.session.execute(stmt)
        pool_memory = result.scalars().first()

        if not pool_memory:
            return False

        # Can remove if pool owner or original sharer
        if pool.owner_id != user_id and pool_memory.shared_by_id != user_id:
            return False

        await self.session.delete(pool_memory)
        await self.session.commit()

        return True

    async def recall_pool_memories(
        self,
        pool_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str = "",
        top_k: int = 10,
        embedding_model_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve memories from a shared pool.

        Args:
            pool_id: Pool ID
            user_id: User retrieving (must have access)
            query: Optional search query
            top_k: Maximum results
            embedding_model_id: Model for query embedding

        Returns:
            List of memory dicts
        """
        # Check access
        pool = await self.get_pool(pool_id, user_id)
        if not pool:
            return []

        # Get shared memory IDs
        shared_stmt = select(SharedPoolMemory.memory_id).where(
            SharedPoolMemory.pool_id == pool_id
        )
        shared_result = await self.session.execute(shared_stmt)
        memory_ids = [row[0] for row in shared_result]

        if not memory_ids:
            return []

        # Get memories
        stmt = select(AgentMemory).where(AgentMemory.id.in_(memory_ids))
        result = await self.session.execute(stmt)
        memories = list(result.scalars().all())

        # If query provided and memories have embeddings, do semantic search
        if query and embedding_model_id:
            from airbeeps.rag.embeddings import get_embedding_service

            try:
                embedding_service = get_embedding_service()
                embed_model = await embedding_service.get_embed_model(
                    embedding_model_id
                )
                query_embedding = await embed_model._aget_query_embedding(query)

                # Score and sort by similarity
                scored = []
                for m in memories:
                    if m.embedding:
                        sim = self._cosine_similarity(query_embedding, m.embedding)
                        scored.append((m, sim))

                scored.sort(key=lambda x: x[1], reverse=True)
                memories = [m for m, _ in scored[:top_k]]
            except Exception as e:
                logger.warning(f"Semantic search failed: {e}")
                memories = memories[:top_k]
        else:
            memories = memories[:top_k]

        # Decrypt and format results
        decrypted = []
        for memory in memories:
            try:
                content = self._encryption.decrypt(memory.content)
                decrypted.append(
                    {
                        "id": str(memory.id),
                        "content": content,
                        "type": memory.memory_type.value,
                        "importance": memory.importance_score,
                        "metadata": memory.metadata,
                        "created_at": memory.created_at.isoformat()
                        if memory.created_at
                        else None,
                        "pool_id": str(pool_id),
                    }
                )
            except ValueError:
                logger.warning(f"Failed to decrypt memory {memory.id}")
                continue

        return decrypted

    async def get_pool_stats(
        self, pool_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Get statistics for a pool."""
        pool = await self.get_pool(pool_id, user_id)
        if not pool:
            return None

        # Count memories
        memory_count_stmt = select(func.count()).where(
            SharedPoolMemory.pool_id == pool_id
        )
        memory_result = await self.session.execute(memory_count_stmt)
        memory_count = memory_result.scalar() or 0

        # Count members
        member_count_stmt = select(func.count()).where(
            SharedPoolMember.pool_id == pool_id
        )
        member_result = await self.session.execute(member_count_stmt)
        member_count = member_result.scalar() or 0

        return {
            "pool_id": str(pool_id),
            "name": pool.name,
            "pool_type": pool.pool_type.value,
            "access_level": pool.access_level.value,
            "memory_count": memory_count,
            "member_count": member_count,
            "max_memories": pool.max_memories,
            "capacity_used_percent": round(memory_count / pool.max_memories * 100, 1),
            "auto_share_enabled": pool.auto_share_enabled,
        }

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _can_access_pool(
        self, pool: SharedMemoryPool, user_id: uuid.UUID
    ) -> bool:
        """Check if user can access a pool."""
        # Owner always has access
        if pool.owner_id == user_id:
            return True

        # Public pools are accessible to all
        if pool.pool_type == PoolTypeEnum.PUBLIC:
            return True

        # Check membership
        member = await self._get_member(pool.id, user_id)
        return member is not None

    async def _get_member(
        self, pool_id: uuid.UUID, user_id: uuid.UUID
    ) -> SharedPoolMember | None:
        """Get member record for a user in a pool."""
        stmt = select(SharedPoolMember).where(
            SharedPoolMember.pool_id == pool_id,
            SharedPoolMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _get_user_access_level(
        self, pool: SharedMemoryPool, user_id: uuid.UUID
    ) -> PoolAccessLevelEnum:
        """Get user's access level for a pool."""
        # Owner always has READ_WRITE
        if pool.owner_id == user_id:
            return PoolAccessLevelEnum.READ_WRITE

        # Check member-specific access level
        member = await self._get_member(pool.id, user_id)
        if member and member.access_level:
            return member.access_level

        # Use pool default
        return pool.access_level

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


async def create_shared_pool_service(session: AsyncSession) -> SharedPoolService:
    """Create a shared pool service instance with given session."""
    return SharedPoolService(session=session)
