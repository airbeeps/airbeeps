"""
Agent Memory Service.

Provides memory storage, retrieval, and management with:
- Encryption at rest
- Semantic search via embeddings
- GDPR compliance (consent, export, delete)
- Retention policies
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.agents.memory.encryption import MemoryEncryption, get_memory_encryption
from airbeeps.agents.memory.models import (
    AgentMemory,
    ConsentActionEnum,
    MemoryConsentLog,
    MemoryTypeEnum,
    RetentionPolicy,
    UserMemoryConsent,
)
from airbeeps.database import async_session_maker
from airbeeps.rag.embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Service for managing agent memories with encryption and governance.
    """

    def __init__(
        self,
        session: AsyncSession,
        encryption: MemoryEncryption | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        """
        Initialize memory service.

        Args:
            session: Database session
            encryption: Encryption handler (uses global if not provided)
            embedding_service: Embedding service for semantic search
        """
        self.session = session
        self._encryption = encryption or get_memory_encryption()
        self._embedding_service = embedding_service

    @property
    def embedding_service(self) -> EmbeddingService:
        """Get embedding service (lazy-loaded)."""
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # =========================================================================
    # Memory Storage
    # =========================================================================

    async def store_memory(
        self,
        assistant_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        memory_type: MemoryTypeEnum,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
        source_conversation_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
        embedding_model_id: str | None = None,
        require_consent: bool = True,
    ) -> AgentMemory:
        """
        Store a new memory with encryption.

        Args:
            assistant_id: Assistant this memory belongs to
            user_id: User this memory belongs to
            content: Memory content (will be encrypted)
            memory_type: Type of memory
            importance: Importance score (0.0 to 1.0)
            metadata: Optional metadata
            source_conversation_id: Conversation this memory came from
            source_message_id: Message this memory came from
            embedding_model_id: Model ID for embedding generation
            require_consent: Whether to check for user consent

        Returns:
            Created AgentMemory instance

        Raises:
            PermissionError: If user hasn't consented and consent is required
        """
        # 1. Check consent if required
        if require_consent:
            has_consent = await self.check_consent(user_id, memory_type)
            if not has_consent:
                raise PermissionError(
                    f"User {user_id} has not consented to {memory_type.value} memory storage"
                )

        # 2. Get retention policy
        policy = await self._get_retention_policy(memory_type)

        # 3. Calculate expiration
        expires_at = None
        if policy and policy.ttl_days > 0:
            # Check for user preference
            user_consent = await self._get_user_consent(user_id)
            ttl_days = policy.ttl_days
            if user_consent and user_consent.preferred_ttl_days:
                ttl_days = min(ttl_days, user_consent.preferred_ttl_days)
            expires_at = datetime.utcnow() + timedelta(days=ttl_days)

        # 4. Generate embedding from plaintext (before encryption)
        embedding = None
        embedding_dim = None
        if embedding_model_id:
            try:
                embed_model = await self.embedding_service.get_embed_model(
                    embedding_model_id
                )
                embedding = await embed_model._aget_text_embedding(content)
                embedding_dim = len(embedding) if embedding else None
            except Exception as e:
                logger.warning(f"Failed to generate embedding for memory: {e}")

        # 5. Encrypt content
        encrypted_content = self._encryption.encrypt(content)

        # 6. Create memory
        memory = AgentMemory(
            assistant_id=assistant_id,
            user_id=user_id,
            memory_type=memory_type,
            content=encrypted_content,
            embedding=embedding,
            embedding_dim=embedding_dim,
            importance_score=max(0.0, min(1.0, importance)),  # Clamp to [0, 1]
            metadata=metadata or {},
            expires_at=expires_at,
            is_encrypted=True,
            retention_policy_id=policy.id if policy else None,
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
        )

        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)

        logger.info(
            f"Stored memory {memory.id} for user {user_id}, type={memory_type.value}"
        )
        return memory

    async def recall_memories(
        self,
        query: str,
        assistant_id: uuid.UUID,
        user_id: uuid.UUID,
        top_k: int = 5,
        memory_types: list[MemoryTypeEnum] | None = None,
        min_importance: float = 0.0,
        embedding_model_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve memories using semantic search.

        Args:
            query: Search query
            assistant_id: Assistant to search memories for
            user_id: User to search memories for
            top_k: Maximum number of results
            memory_types: Filter by memory types (all if None)
            min_importance: Minimum importance score
            embedding_model_id: Model ID for query embedding

        Returns:
            List of memory dicts with decrypted content
        """
        # 1. Build base query
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.assistant_id == assistant_id,
                AgentMemory.user_id == user_id,
                AgentMemory.importance_score >= min_importance,
            )
            .where(
                # Not expired
                (AgentMemory.expires_at.is_(None))
                | (AgentMemory.expires_at > datetime.utcnow())
            )
        )

        # Filter by memory types
        if memory_types:
            stmt = stmt.where(AgentMemory.memory_type.in_(memory_types))

        # 2. If we have a query and embedding model, do semantic search
        if query and embedding_model_id:
            try:
                embed_model = await self.embedding_service.get_embed_model(
                    embedding_model_id
                )
                query_embedding = await embed_model._aget_query_embedding(query)

                # For now, fetch all and sort in memory
                # TODO: Use pgvector or similar for efficient vector search
                stmt = stmt.where(AgentMemory.embedding.isnot(None))

            except Exception as e:
                logger.warning(f"Failed to generate query embedding: {e}")
                query_embedding = None
        else:
            query_embedding = None

        # 3. Execute query
        result = await self.session.execute(
            stmt.limit(top_k * 3)
        )  # Over-fetch for reranking
        memories = result.scalars().all()

        # 4. Score and sort by similarity if we have embeddings
        if query_embedding and memories:
            scored_memories = []
            for memory in memories:
                if memory.embedding:
                    similarity = self._cosine_similarity(
                        query_embedding, memory.embedding
                    )
                    scored_memories.append((memory, similarity))

            # Sort by similarity (descending)
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            memories = [m for m, _ in scored_memories[:top_k]]
        else:
            # Sort by importance and recency
            memories = sorted(
                memories,
                key=lambda m: (m.importance_score, m.created_at),
                reverse=True,
            )[:top_k]

        # 5. Decrypt and format results
        decrypted_memories = []
        for memory in memories:
            try:
                decrypted_content = self._encryption.decrypt(memory.content)
            except ValueError:
                logger.error(f"Failed to decrypt memory {memory.id}")
                continue

            # Update access tracking
            memory.access_count += 1
            memory.last_accessed_at = datetime.utcnow()

            decrypted_memories.append(
                {
                    "id": str(memory.id),
                    "content": decrypted_content,
                    "type": memory.memory_type.value,
                    "importance": memory.importance_score,
                    "metadata": memory.metadata,
                    "created_at": memory.created_at.isoformat()
                    if memory.created_at
                    else None,
                    "access_count": memory.access_count,
                }
            )

        await self.session.commit()

        logger.debug(f"Recalled {len(decrypted_memories)} memories for user {user_id}")
        return decrypted_memories

    async def get_memory_by_id(
        self, memory_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """
        Get a specific memory by ID.

        Args:
            memory_id: Memory ID
            user_id: User ID (for access control)

        Returns:
            Memory dict with decrypted content, or None if not found
        """
        stmt = select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        memory = result.scalars().first()

        if not memory:
            return None

        try:
            decrypted_content = self._encryption.decrypt(memory.content)
        except ValueError:
            return None

        return {
            "id": str(memory.id),
            "content": decrypted_content,
            "type": memory.memory_type.value,
            "importance": memory.importance_score,
            "metadata": memory.metadata,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
            "access_count": memory.access_count,
        }

    async def update_memory_importance(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        importance: float,
    ) -> bool:
        """Update a memory's importance score."""
        stmt = select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        memory = result.scalars().first()

        if not memory:
            return False

        memory.importance_score = max(0.0, min(1.0, importance))
        await self.session.commit()
        return True

    async def delete_memory(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a specific memory."""
        stmt = delete(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    # =========================================================================
    # Consent Management
    # =========================================================================

    async def check_consent(
        self, user_id: uuid.UUID, memory_type: MemoryTypeEnum | None = None
    ) -> bool:
        """
        Check if user has consented to memory storage.

        Args:
            user_id: User to check
            memory_type: Optional specific memory type to check

        Returns:
            True if user has consented
        """
        consent = await self._get_user_consent(user_id)
        if not consent or not consent.has_consented:
            return False

        if memory_type and memory_type.value not in consent.allowed_memory_types:
            return False

        return True

    async def grant_consent(
        self,
        user_id: uuid.UUID,
        allowed_types: list[MemoryTypeEnum] | None = None,
        preferred_ttl_days: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserMemoryConsent:
        """
        Grant consent for memory storage.

        Args:
            user_id: User granting consent
            allowed_types: Memory types to allow (all if None)
            preferred_ttl_days: User's preferred retention period
            ip_address: Request IP
            user_agent: Request user agent

        Returns:
            Updated consent record
        """
        consent = await self._get_user_consent(user_id)

        if allowed_types is None:
            allowed_types = list(MemoryTypeEnum)

        type_names = [t.value for t in allowed_types]

        if consent:
            consent.has_consented = True
            consent.consent_date = datetime.utcnow()
            consent.allowed_memory_types = type_names
            consent.preferred_ttl_days = preferred_ttl_days
        else:
            consent = UserMemoryConsent(
                user_id=user_id,
                has_consented=True,
                consent_date=datetime.utcnow(),
                allowed_memory_types=type_names,
                preferred_ttl_days=preferred_ttl_days,
            )
            self.session.add(consent)

        # Log consent action
        await self._log_consent_action(
            user_id=user_id,
            action=ConsentActionEnum.GRANT,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"allowed_types": type_names},
        )

        await self.session.commit()
        await self.session.refresh(consent)

        logger.info(f"User {user_id} granted memory consent")
        return consent

    async def revoke_consent(
        self,
        user_id: uuid.UUID,
        delete_existing: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """
        Revoke consent for memory storage.

        Args:
            user_id: User revoking consent
            delete_existing: Whether to delete existing memories
            ip_address: Request IP
            user_agent: Request user agent
        """
        consent = await self._get_user_consent(user_id)

        if consent:
            consent.has_consented = False
            consent.consent_date = datetime.utcnow()

        # Optionally delete existing memories
        if delete_existing:
            await self.forget_user(user_id, ip_address, user_agent)

        # Log consent action
        await self._log_consent_action(
            user_id=user_id,
            action=ConsentActionEnum.REVOKE,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"delete_existing": delete_existing},
        )

        await self.session.commit()
        logger.info(f"User {user_id} revoked memory consent")

    # =========================================================================
    # GDPR Compliance
    # =========================================================================

    async def forget_user(
        self,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> int:
        """
        GDPR Right to be Forgotten - delete ALL user memories.

        Args:
            user_id: User requesting deletion
            ip_address: Request IP
            user_agent: Request user agent

        Returns:
            Number of memories deleted
        """
        # Get count before deletion
        count_stmt = select(func.count()).where(AgentMemory.user_id == user_id)
        count_result = await self.session.execute(count_stmt)
        count = count_result.scalar() or 0

        # Delete all memories
        stmt = delete(AgentMemory).where(AgentMemory.user_id == user_id)
        await self.session.execute(stmt)

        # Log consent action
        await self._log_consent_action(
            user_id=user_id,
            action=ConsentActionEnum.DELETE,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"memories_deleted": count},
        )

        await self.session.commit()
        logger.info(f"Deleted {count} memories for user {user_id}")
        return count

    async def export_user_memories(
        self,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """
        GDPR Right to Data Portability - export all user memories.

        Args:
            user_id: User requesting export
            ip_address: Request IP
            user_agent: Request user agent

        Returns:
            Dict with all user memories (decrypted)
        """
        stmt = select(AgentMemory).where(AgentMemory.user_id == user_id)
        result = await self.session.execute(stmt)
        memories = result.scalars().all()

        exported_memories = []
        for memory in memories:
            try:
                decrypted_content = self._encryption.decrypt(memory.content)
            except ValueError:
                decrypted_content = "[DECRYPTION_FAILED]"

            exported_memories.append(
                {
                    "id": str(memory.id),
                    "type": memory.memory_type.value,
                    "content": decrypted_content,
                    "importance": memory.importance_score,
                    "metadata": memory.metadata,
                    "created_at": memory.created_at.isoformat()
                    if memory.created_at
                    else None,
                    "expires_at": memory.expires_at.isoformat()
                    if memory.expires_at
                    else None,
                }
            )

        # Log export action
        await self._log_consent_action(
            user_id=user_id,
            action=ConsentActionEnum.EXPORT,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"memories_exported": len(exported_memories)},
        )

        await self.session.commit()

        return {
            "user_id": str(user_id),
            "exported_at": datetime.utcnow().isoformat(),
            "memory_count": len(exported_memories),
            "memories": exported_memories,
        }

    # =========================================================================
    # Retention Management
    # =========================================================================

    async def prune_expired_memories(self) -> int:
        """
        Delete all expired memories.

        Returns:
            Number of memories pruned
        """
        stmt = delete(AgentMemory).where(
            AgentMemory.expires_at.isnot(None),
            AgentMemory.expires_at < datetime.utcnow(),
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        count = result.rowcount
        if count > 0:
            logger.info(f"Pruned {count} expired memories")
        return count

    async def prune_user_memories_over_quota(
        self, user_id: uuid.UUID, max_memories: int | None = None
    ) -> int:
        """
        Prune memories if user exceeds quota.

        Deletes lowest-importance memories first.

        Args:
            user_id: User to check
            max_memories: Max allowed (uses policy default if None)

        Returns:
            Number of memories pruned
        """
        # Get default from retention policy if not specified
        if max_memories is None:
            policy = await self._get_default_retention_policy()
            max_memories = policy.max_memories_per_user if policy else 1000

        # Count current memories
        count_stmt = select(func.count()).where(AgentMemory.user_id == user_id)
        count_result = await self.session.execute(count_stmt)
        current_count = count_result.scalar() or 0

        if current_count <= max_memories:
            return 0

        # Get IDs of lowest-importance memories to delete
        excess = current_count - max_memories
        subquery = (
            select(AgentMemory.id)
            .where(AgentMemory.user_id == user_id)
            .order_by(AgentMemory.importance_score.asc(), AgentMemory.created_at.asc())
            .limit(excess)
        )
        ids_result = await self.session.execute(subquery)
        ids_to_delete = [row[0] for row in ids_result]

        if ids_to_delete:
            stmt = delete(AgentMemory).where(AgentMemory.id.in_(ids_to_delete))
            await self.session.execute(stmt)
            await self.session.commit()

        logger.info(
            f"Pruned {len(ids_to_delete)} memories for user {user_id} (over quota)"
        )
        return len(ids_to_delete)

    # =========================================================================
    # Retention Policies
    # =========================================================================

    async def create_retention_policy(
        self,
        name: str,
        ttl_days: int = 90,
        max_memories_per_user: int = 1000,
        auto_prune_threshold: float = 0.3,
        applies_to_types: list[str] | None = None,
        description: str | None = None,
        is_default: bool = False,
    ) -> RetentionPolicy:
        """Create a new retention policy."""
        if applies_to_types is None:
            applies_to_types = [t.value for t in MemoryTypeEnum]

        # If setting as default, unset other defaults
        if is_default:
            await self.session.execute(
                RetentionPolicy.__table__.update().values(is_default=False)
            )

        policy = RetentionPolicy(
            name=name,
            description=description,
            ttl_days=ttl_days,
            max_memories_per_user=max_memories_per_user,
            auto_prune_threshold=auto_prune_threshold,
            applies_to_types=applies_to_types,
            is_default=is_default,
        )
        self.session.add(policy)
        await self.session.commit()
        await self.session.refresh(policy)
        return policy

    async def get_retention_policies(self) -> list[RetentionPolicy]:
        """Get all active retention policies."""
        stmt = select(RetentionPolicy).where(RetentionPolicy.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_user_memory_stats(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Get memory statistics for a user."""
        # Total count
        total_stmt = select(func.count()).where(AgentMemory.user_id == user_id)
        total_result = await self.session.execute(total_stmt)
        total = total_result.scalar() or 0

        # Count by type
        type_counts = {}
        for memory_type in MemoryTypeEnum:
            type_stmt = select(func.count()).where(
                AgentMemory.user_id == user_id,
                AgentMemory.memory_type == memory_type,
            )
            type_result = await self.session.execute(type_stmt)
            type_counts[memory_type.value] = type_result.scalar() or 0

        # Average importance
        avg_stmt = select(func.avg(AgentMemory.importance_score)).where(
            AgentMemory.user_id == user_id
        )
        avg_result = await self.session.execute(avg_stmt)
        avg_importance = avg_result.scalar() or 0.0

        # Consent status
        consent = await self._get_user_consent(user_id)

        return {
            "total_memories": total,
            "by_type": type_counts,
            "average_importance": round(avg_importance, 2),
            "has_consent": consent.has_consented if consent else False,
            "allowed_types": consent.allowed_memory_types if consent else [],
        }

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _get_user_consent(self, user_id: uuid.UUID) -> UserMemoryConsent | None:
        """Get user's consent record."""
        stmt = select(UserMemoryConsent).where(UserMemoryConsent.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _get_retention_policy(
        self, memory_type: MemoryTypeEnum
    ) -> RetentionPolicy | None:
        """Get applicable retention policy for memory type."""
        stmt = (
            select(RetentionPolicy)
            .where(
                RetentionPolicy.is_active.is_(True),
                RetentionPolicy.applies_to_types.contains([memory_type.value]),
            )
            .order_by(RetentionPolicy.is_default.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _get_default_retention_policy(self) -> RetentionPolicy | None:
        """Get the default retention policy."""
        stmt = select(RetentionPolicy).where(
            RetentionPolicy.is_active.is_(True),
            RetentionPolicy.is_default.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _log_consent_action(
        self,
        user_id: uuid.UUID,
        action: ConsentActionEnum,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryConsentLog:
        """Log a consent-related action for audit purposes."""
        log = MemoryConsentLog(
            user_id=user_id,
            action=action,
            action_timestamp=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
        )
        self.session.add(log)
        return log

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


# Global service instance (scoped to request in actual usage)
_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """
    Get memory service instance.

    Note: In actual usage, this should be scoped to request with proper session.
    """
    global _memory_service
    if _memory_service is None:
        raise RuntimeError(
            "Memory service not initialized. Use create_memory_service() with a session."
        )
    return _memory_service


async def create_memory_service(session: AsyncSession) -> MemoryService:
    """Create a memory service instance with given session."""
    return MemoryService(session=session)
