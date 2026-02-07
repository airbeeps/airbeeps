"""
Agent Memory System.

Provides long-term memory capabilities for agents with:
- Multiple memory types (conversation, episodic, semantic, preference)
- Encryption at rest
- GDPR compliance (consent, export, delete)
- Retention policies
- Semantic search via embeddings
- Memory compaction and summarization
- Shared memory pools for collaboration
"""

from airbeeps.agents.memory.api import admin_router as memory_admin_router
from airbeeps.agents.memory.api import router as memory_router
from airbeeps.agents.memory.compaction import (
    MemoryCompactionService,
    create_compaction_service,
)
from airbeeps.agents.memory.encryption import MemoryEncryption, get_memory_encryption
from airbeeps.agents.memory.models import (
    AgentMemory,
    CompactionStrategyEnum,
    ConsentActionEnum,
    MemoryCompactionLog,
    MemoryConsentLog,
    MemoryTypeEnum,
    PoolAccessLevelEnum,
    PoolTypeEnum,
    RetentionPolicy,
    SharedMemoryPool,
    SharedPoolMember,
    SharedPoolMemory,
    UserMemoryConsent,
)
from airbeeps.agents.memory.pool_service import (
    SharedPoolService,
    create_shared_pool_service,
)
from airbeeps.agents.memory.service import MemoryService, create_memory_service
from airbeeps.agents.memory.summarization import MemorySummarizer, get_memory_summarizer

__all__ = [
    # Models
    "AgentMemory",
    "CompactionStrategyEnum",
    "ConsentActionEnum",
    "MemoryCompactionLog",
    "MemoryConsentLog",
    "MemoryTypeEnum",
    "PoolAccessLevelEnum",
    "PoolTypeEnum",
    "RetentionPolicy",
    "SharedMemoryPool",
    "SharedPoolMember",
    "SharedPoolMemory",
    "UserMemoryConsent",
    # Services
    "MemoryCompactionService",
    "MemoryEncryption",
    "MemoryService",
    "MemorySummarizer",
    "SharedPoolService",
    # Factory functions
    "create_compaction_service",
    "create_memory_service",
    "create_shared_pool_service",
    "get_memory_encryption",
    "get_memory_summarizer",
    # Routers
    "memory_admin_router",
    "memory_router",
]
