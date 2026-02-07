"""
Agent Memory Models.

Database models for agent memory system with data governance.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base

if TYPE_CHECKING:
    from airbeeps.assistants.models import Assistant
    from airbeeps.users.models import User


class MemoryTypeEnum(enum.Enum):
    """Types of agent memories"""

    CONVERSATION = "CONVERSATION"  # Conversation summaries
    EPISODIC = "EPISODIC"  # Specific events/experiences
    SEMANTIC = "SEMANTIC"  # Facts and general knowledge
    PREFERENCE = "PREFERENCE"  # User preferences and patterns


class ConsentActionEnum(enum.Enum):
    """Actions logged for memory consent"""

    GRANT = "GRANT"  # User granted consent
    REVOKE = "REVOKE"  # User revoked consent
    EXPORT = "EXPORT"  # User exported their data
    DELETE = "DELETE"  # User requested deletion


class PoolTypeEnum(enum.Enum):
    """Types of shared memory pools"""

    TEAM = "TEAM"  # Shared within a team
    ORGANIZATION = "ORGANIZATION"  # Shared across organization
    PUBLIC = "PUBLIC"  # Publicly accessible


class PoolAccessLevelEnum(enum.Enum):
    """Access levels for shared memory pools"""

    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"


class CompactionStrategyEnum(enum.Enum):
    """Strategies for memory compaction"""

    AGE = "AGE"  # Compact memories older than threshold
    SIMILARITY = "SIMILARITY"  # Merge similar memories
    IMPORTANCE = "IMPORTANCE"  # Summarize low-importance memories
    HYBRID = "HYBRID"  # Combination of strategies


class RetentionPolicy(Base):
    """
    Data retention policies for agent memories.

    Defines how long memories are kept and when they're pruned.
    """

    __tablename__ = "memory_retention_policies"

    # Policy name
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Time-to-live in days (0 = never expire)
    ttl_days: Mapped[int] = mapped_column(
        Integer,
        default=90,
        server_default="90",
        nullable=False,
        comment="Days before memory expires (0 = never)",
    )

    # Maximum memories per user for this policy
    max_memories_per_user: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        server_default="1000",
        nullable=False,
        comment="Maximum memories per user",
    )

    # Importance threshold for auto-pruning (memories below this get pruned first)
    auto_prune_threshold: Mapped[float] = mapped_column(
        Float,
        default=0.3,
        server_default="0.3",
        nullable=False,
        comment="Importance score below which memories are pruned",
    )

    # Which memory types this policy applies to
    applies_to_types: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default='["CONVERSATION", "EPISODIC", "SEMANTIC", "PREFERENCE"]',
        comment="Memory types this policy applies to",
    )

    # Whether this is the default policy
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether this is the default retention policy",
    )

    # Whether the policy is active
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # Relationships
    memories: Mapped[list["AgentMemory"]] = relationship(
        "AgentMemory", back_populates="retention_policy"
    )

    def __repr__(self) -> str:
        return f"<RetentionPolicy(name='{self.name}', ttl_days={self.ttl_days})>"


class AgentMemory(Base):
    """
    Long-term memory for agents with data governance.

    Stores memories with encryption, retention policies, and consent tracking.
    Embeddings are stored for semantic search while content is encrypted.
    """

    __tablename__ = "agent_memories"

    # Associated assistant
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Associated user
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Memory type
    memory_type: Mapped[MemoryTypeEnum] = mapped_column(
        SQLEnum(MemoryTypeEnum),
        nullable=False,
        index=True,
    )

    # Memory content (encrypted at rest via Fernet)
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Encrypted memory content",
    )

    # Embedding vector (stored as JSON array for portability)
    # Note: For high-performance, consider pgvector column type
    embedding: Mapped[list[float] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Embedding vector for semantic search",
    )

    # Embedding dimension (for validation)
    embedding_dim: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Dimension of embedding vector",
    )

    # Importance score (0.0 to 1.0)
    importance_score: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        server_default="0.5",
        nullable=False,
        comment="Importance score for pruning decisions",
    )

    # Access tracking
    access_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
        comment="Number of times this memory was retrieved",
    )

    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this memory was last retrieved",
    )

    # Metadata (tags, source, etc.)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # Column name in the database
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Additional metadata about the memory",
    )

    # Data governance fields
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="When this memory expires (null = never)",
    )

    is_encrypted: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="Whether content is encrypted",
    )

    # Retention policy
    retention_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memory_retention_policies.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Source tracking
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        comment="Conversation this memory was derived from",
    )

    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="Message this memory was derived from",
    )

    # Compaction tracking fields
    is_compacted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether this memory was created from compaction",
    )

    parent_memory_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
        comment="IDs of memories that were merged into this one",
    )

    compaction_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this memory was created via compaction",
    )

    original_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
        comment="Number of original memories merged into this one",
    )

    # Relationships
    assistant: Mapped["Assistant"] = relationship("Assistant")
    user: Mapped["User"] = relationship("User")
    retention_policy: Mapped["RetentionPolicy | None"] = relationship(
        "RetentionPolicy", back_populates="memories"
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_agent_memories_user_assistant", "user_id", "assistant_id"),
        Index("ix_agent_memories_user_type", "user_id", "memory_type"),
        Index(
            "ix_agent_memories_not_expired",
            "user_id",
            "assistant_id",
            "expires_at",
            postgresql_where="expires_at IS NULL OR expires_at > NOW()",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentMemory(type='{self.memory_type.value}', user_id='{self.user_id}')>"
        )


class UserMemoryConsent(Base):
    """
    User consent for memory storage.

    Tracks whether a user has consented to having memories stored.
    """

    __tablename__ = "user_memory_consents"

    # User
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Consent status
    has_consented: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether user has consented to memory storage",
    )

    # When consent was granted/modified
    consent_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When consent was last modified",
    )

    # Consent scope (which types of memories are allowed)
    allowed_memory_types: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default='["CONVERSATION", "EPISODIC", "SEMANTIC", "PREFERENCE"]',
        comment="Which memory types the user consents to",
    )

    # Retention preference (user's preferred TTL, null = use policy default)
    preferred_ttl_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="User's preferred retention period in days",
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<UserMemoryConsent(user_id='{self.user_id}', consented={self.has_consented})>"


class SharedMemoryPool(Base):
    """
    Shared memory pools for collaborative knowledge.

    Allows memories to be shared across users with access controls.
    """

    __tablename__ = "shared_memory_pools"

    # Pool name
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pool type (team, organization, public)
    pool_type: Mapped[PoolTypeEnum] = mapped_column(
        SQLEnum(PoolTypeEnum),
        nullable=False,
        default=PoolTypeEnum.TEAM,
    )

    # Access level for members
    access_level: Mapped[PoolAccessLevelEnum] = mapped_column(
        SQLEnum(PoolAccessLevelEnum),
        nullable=False,
        default=PoolAccessLevelEnum.READ_ONLY,
    )

    # Owner
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Associated assistant (optional)
    assistant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Whether the pool is active
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # Configuration
    max_memories: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        server_default="1000",
        nullable=False,
        comment="Maximum memories in this pool",
    )

    # Pool policy settings
    auto_share_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Auto-share new memories to this pool",
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])
    assistant: Mapped["Assistant | None"] = relationship("Assistant")
    members: Mapped[list["SharedPoolMember"]] = relationship(
        "SharedPoolMember", back_populates="pool", cascade="all, delete-orphan"
    )
    pool_memories: Mapped[list["SharedPoolMemory"]] = relationship(
        "SharedPoolMemory", back_populates="pool", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SharedMemoryPool(name='{self.name}', type='{self.pool_type.value}')>"


class SharedPoolMember(Base):
    """
    Members of a shared memory pool.
    """

    __tablename__ = "shared_pool_members"

    # Pool
    pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shared_memory_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Member user
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Member access level (can override pool default)
    access_level: Mapped[PoolAccessLevelEnum | None] = mapped_column(
        SQLEnum(PoolAccessLevelEnum),
        nullable=True,
        comment="Override access level for this member",
    )

    # When the member was added
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    pool: Mapped["SharedMemoryPool"] = relationship(
        "SharedMemoryPool", back_populates="members"
    )
    user: Mapped["User"] = relationship("User")

    # Unique constraint
    __table_args__ = (
        Index("ix_shared_pool_members_pool_user", "pool_id", "user_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<SharedPoolMember(pool_id='{self.pool_id}', user_id='{self.user_id}')>"


class SharedPoolMemory(Base):
    """
    Association between shared pools and memories.
    """

    __tablename__ = "shared_pool_memories"

    # Pool
    pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shared_memory_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Memory
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_memories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Who shared this memory
    shared_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # When the memory was shared
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    pool: Mapped["SharedMemoryPool"] = relationship(
        "SharedMemoryPool", back_populates="pool_memories"
    )
    memory: Mapped["AgentMemory"] = relationship("AgentMemory")
    shared_by: Mapped["User | None"] = relationship("User")

    # Unique constraint
    __table_args__ = (
        Index(
            "ix_shared_pool_memories_pool_memory", "pool_id", "memory_id", unique=True
        ),
    )

    def __repr__(self) -> str:
        return f"<SharedPoolMemory(pool_id='{self.pool_id}', memory_id='{self.memory_id}')>"


class MemoryCompactionLog(Base):
    """
    Log of memory compaction operations.
    """

    __tablename__ = "memory_compaction_logs"

    # User whose memories were compacted
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Assistant (optional)
    assistant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Compaction strategy used
    strategy: Mapped[CompactionStrategyEnum] = mapped_column(
        SQLEnum(CompactionStrategyEnum),
        nullable=False,
    )

    # Statistics
    memories_before: Mapped[int] = mapped_column(Integer, nullable=False)
    memories_after: Mapped[int] = mapped_column(Integer, nullable=False)
    memories_merged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memories_summarized: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Duration
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Result memory IDs (the compacted/summarized memories)
    result_memory_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
    )

    # Source memory IDs (memories that were compacted)
    source_memory_ids: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    assistant: Mapped["Assistant | None"] = relationship("Assistant")

    def __repr__(self) -> str:
        return f"<MemoryCompactionLog(user_id='{self.user_id}', strategy='{self.strategy.value}')>"


class MemoryConsentLog(Base):
    """
    Audit log for memory consent changes.

    GDPR compliance: track all consent-related actions.
    """

    __tablename__ = "memory_consent_logs"

    # User
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Action taken
    action: Mapped[ConsentActionEnum] = mapped_column(
        SQLEnum(ConsentActionEnum),
        nullable=False,
    )

    # When the action occurred
    action_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # IP address of the request
    ip_address: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="IP address from which action was taken",
    )

    # User agent of the request
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="User agent of the request",
    )

    # Additional metadata about the action
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # Column name in the database
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Additional action details",
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<MemoryConsentLog(user_id='{self.user_id}', action='{self.action.value}')>"
