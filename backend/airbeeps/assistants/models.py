import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base

if TYPE_CHECKING:
    from airbeeps.agents.models import MCPServerConfig
    from airbeeps.ai_models.models import Model
    from airbeeps.users.models import User


class AssistantStatusEnum(enum.Enum):
    """Assistant status enumeration"""

    ACTIVE = "ACTIVE"  # Active and available
    INACTIVE = "INACTIVE"  # Disabled
    DRAFT = "DRAFT"  # Draft state


class AssistantModeEnum(enum.Enum):
    """Assistant mode enumeration"""

    GENERAL = "GENERAL"  # Regular chatbot (no automatic retrieval)
    RAG = "RAG"  # Retrieval-augmented generation


class ConversationStatusEnum(enum.Enum):
    """Conversation status enumeration"""

    ACTIVE = "ACTIVE"  # Active conversation
    ARCHIVED = "ARCHIVED"  # Archived conversation
    DELETED = "DELETED"  # Deleted conversation


class MessageTypeEnum(enum.Enum):
    """Message type enumeration"""

    USER = "USER"  # User message
    ASSISTANT = "ASSISTANT"  # Assistant response
    SYSTEM = "SYSTEM"  # System message


class ConversationShareScopeEnum(enum.Enum):
    """Scope of conversation sharing"""

    CONVERSATION = "CONVERSATION"
    MESSAGE = "MESSAGE"


class ConversationShareStatusEnum(enum.Enum):
    """Status of a conversation share link"""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class Assistant(Base):
    """Assistant table - represents AI assistants"""

    __tablename__ = "assistants"

    # Assistant name
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Assistant description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # System prompt/instructions for the assistant
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Assistant avatar file ID (foreign key to file_records)
    avatar_file_path: Mapped[str | None] = mapped_column(String(1000))

    # Assistant status
    status: Mapped[AssistantStatusEnum] = mapped_column(
        SQLEnum(AssistantStatusEnum), default=AssistantStatusEnum.DRAFT, nullable=False
    )

    # Assistant mode (GENERAL or RAG)
    mode: Mapped[AssistantModeEnum] = mapped_column(
        SQLEnum(AssistantModeEnum),
        default=AssistantModeEnum.GENERAL,
        server_default="GENERAL",
        nullable=False,
        comment="Assistant mode: GENERAL or RAG",
    )

    # Model ID (foreign key to ai_models.models)
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )

    # Owner user ID (foreign key to users table)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Model configuration (temperature, max_tokens, etc.)
    config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    # Follow-up question suggestions (chat UX feature)
    # Global config gates this feature; this flag only allows disabling per assistant.
    followup_questions_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="If true, allow follow-up question suggestions for this assistant (when globally enabled)",
    )

    # Optional assistant-preferred count; effective count is capped by global max.
    followup_questions_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Preferred follow-up question count (capped by global setting)",
    )

    # Global defaults inheritance flags
    # If true: resolve generation settings from global admin defaults unless overridden elsewhere.
    # If false: use assistant-specific values stored on this record.
    use_global_generation_defaults: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="If true, inherit global generation defaults; if false, use assistant overrides",
    )

    # If true: resolve RAG settings from global admin defaults; if false use assistant.rag_config.
    use_global_rag_defaults: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="If true, inherit global RAG defaults; if false, use assistant overrides",
    )

    # Temperature setting for the assistant (0.0 to 2.0, default 1.0)
    temperature: Mapped[float] = mapped_column(
        default=1.0,
        server_default="1.0",
        nullable=False,
        comment="Temperature for text generation (0.0-2.0)",
    )

    # Maximum tokens for response generation
    max_tokens: Mapped[int] = mapped_column(
        Integer,
        default=2048,
        server_default="2048",
        nullable=False,
        comment="Maximum number of tokens to generate",
    )

    # Maximum number of history messages to include in context (None for no limit)
    max_history_messages: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum number of history messages to include in context",
    )

    # Whether this assistant is public (visible to other users)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Usage count - number of times this assistant has been used (conversation created)
    usage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
        comment="Number of times this assistant has been used",
    )

    # Agent configuration - Enable tool calling capabilities
    enable_agent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether to enable agent (tool calling) capabilities",
    )

    # Agent maximum iterations
    agent_max_iterations: Mapped[int] = mapped_column(
        Integer,
        default=5,
        server_default="5",
        nullable=False,
        comment="Maximum iterations for agent reasoning",
    )

    # Agent enabled tools (JSON list of tool names)
    agent_enabled_tools: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
        comment="List of enabled tool names for agent",
    )

    # Agent tool configuration (JSON)
    agent_tool_config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Tool configuration parameters for agent",
    )

    # Agent behavior - Planning and reflection
    agent_enable_planning: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="Enable LLM-based task planning",
    )

    agent_enable_reflection: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
        comment="Enable quality reflection after tool use",
    )

    agent_reflection_threshold: Mapped[float] = mapped_column(
        default=7.0,
        server_default="7.0",
        nullable=False,
        comment="Quality threshold (0-10) for reflection pass",
    )

    # Budget controls
    agent_token_budget: Mapped[int] = mapped_column(
        Integer,
        default=8000,
        server_default="8000",
        nullable=False,
        comment="Maximum tokens per conversation turn",
    )

    agent_max_tool_calls: Mapped[int] = mapped_column(
        Integer,
        default=20,
        server_default="20",
        nullable=False,
        comment="Maximum tool calls per conversation",
    )

    agent_cost_limit_usd: Mapped[float] = mapped_column(
        default=0.50,
        server_default="0.50",
        nullable=False,
        comment="Maximum cost per conversation in USD",
    )

    agent_max_parallel_tools: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
        nullable=False,
        comment="Maximum concurrent tool calls",
    )

    # Memory feature toggle
    enable_memory: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether to enable long-term memory for this assistant",
    )

    # Agentic RAG configuration (Phase 5)
    agent_rag_mode: Mapped[str] = mapped_column(
        String(50),
        default="standard",
        server_default="standard",
        nullable=False,
        comment="Agentic RAG mode: standard, query_planning, self_rag, multi_hop",
    )

    agent_enable_query_planning: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Enable query decomposition for complex queries",
    )

    agent_enable_self_rag: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Enable self-critique and retry for retrieval",
    )

    agent_enable_multi_hop: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Enable multi-hop retrieval for complex reasoning",
    )

    agent_self_rag_min_confidence: Mapped[int] = mapped_column(
        Integer,
        default=50,
        server_default="50",
        nullable=False,
        comment="Minimum confidence score (0-100) for self-RAG to accept results",
    )

    agent_multi_hop_max_hops: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
        nullable=False,
        comment="Maximum number of retrieval hops for multi-hop mode",
    )

    agent_tool_timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=30,
        server_default="30",
        nullable=False,
        comment="Default timeout for tool execution in seconds",
    )

    agent_tool_max_retries: Mapped[int] = mapped_column(
        Integer,
        default=2,
        server_default="2",
        nullable=False,
        comment="Maximum retries for failed tool calls",
    )

    # Multi-Agent configuration (Phase 6)
    specialist_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Specialist type: RESEARCH, CODE, DATA, GENERAL",
    )

    can_collaborate: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether this assistant can participate in multi-agent collaboration",
    )

    collaboration_max_handoffs: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
        nullable=False,
        comment="Maximum handoffs allowed during collaboration",
    )

    collaboration_cost_limit_per_handoff: Mapped[float] = mapped_column(
        default=0.25,
        server_default="0.25",
        nullable=False,
        comment="Cost limit per handoff in USD",
    )

    collaboration_allowed_specialists: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
        comment="List of specialist types this assistant can collaborate with",
    )

    # RAG configuration (retrieval count, similarity threshold, etc.)
    rag_config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    # Associated knowledge base IDs
    knowledge_base_ids: Mapped[list[uuid.UUID]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    # Translations for multi-language support
    # Format: {"locale": {"field_name": "translated_value"}}
    translations: Mapped[dict[str, dict[str, str]] | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
        default=dict,
        comment="Multi-language translations for name, description, and system_prompt",
    )

    # Assistant category (e.g., "coding", "writing", "general")
    category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Primary category of the assistant",
    )

    # Assistant tags (JSON list of strings)
    tags: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
        server_default="[]",
        comment="List of tags for filtering",
    )

    # Associated model
    model: Mapped["Model"] = relationship("Model", back_populates="assistants")

    # Associated owner - relationship defined in User model
    owner: Mapped["User"] = relationship("User")

    # Associated conversations
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="assistant", cascade="all, delete-orphan"
    )

    # Associated MCP servers
    mcp_servers: Mapped[list["MCPServerConfig"]] = relationship(
        "MCPServerConfig",
        secondary="assistant_mcp_servers",
        back_populates="assistants",
    )

    @property
    def mcp_server_ids(self) -> list[uuid.UUID]:
        """Safely get MCP server IDs without triggering lazy load"""
        from sqlalchemy import inspect
        from sqlalchemy.orm.base import NO_VALUE

        try:
            insp = inspect(self)
            if "mcp_servers" in insp.mapper.relationships:
                mcp_servers_state = insp.attrs.mcp_servers
                loaded_value = mcp_servers_state.loaded_value
                if loaded_value is not NO_VALUE and loaded_value is not None:
                    return [mcp.id for mcp in loaded_value]
        except Exception:
            pass
        return []

    @property
    def owner_name(self) -> str | None:
        """Get owner display name or email if owner relationship is loaded"""
        from sqlalchemy import inspect
        from sqlalchemy.orm.base import NO_VALUE

        try:
            insp = inspect(self)
            if "owner" in insp.mapper.relationships:
                owner_state = insp.attrs.owner
                loaded_value = owner_state.loaded_value
                if loaded_value is not NO_VALUE and loaded_value is not None:
                    # Return name if available, otherwise email
                    if hasattr(loaded_value, "name") and loaded_value.name:
                        return loaded_value.name
                    if hasattr(loaded_value, "email"):
                        return loaded_value.email
        except Exception:
            pass
        return None

    def __repr__(self):
        return f"<Assistant(name='{self.name}', owner_id='{self.owner_id}')>"


class Conversation(Base):
    """Conversation table - represents chat conversations"""

    __tablename__ = "conversations"

    # Conversation title
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Conversation status
    status: Mapped[ConversationStatusEnum] = mapped_column(
        SQLEnum(ConversationStatusEnum),
        default=ConversationStatusEnum.ACTIVE,
        nullable=False,
    )

    # Assistant ID (foreign key)
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False
    )

    # User ID (foreign key)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Last message time
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Message count in this conversation
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Conversation metadata (custom data)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Associated assistant
    assistant: Mapped["Assistant"] = relationship(
        "Assistant", back_populates="conversations"
    )

    # Associated user
    user: Mapped["User"] = relationship("User")

    # Associated messages
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    # Associated share links
    shares: Mapped[list["ConversationShare"]] = relationship(
        "ConversationShare", back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Conversation(title='{self.title}', user_id='{self.user_id}')>"


class Message(Base):
    """Message table - represents individual messages in conversations"""

    __tablename__ = "messages"

    # Message content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Message type
    message_type: Mapped[MessageTypeEnum] = mapped_column(
        SQLEnum(MessageTypeEnum), nullable=False
    )

    # Conversation ID (foreign key)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    # User ID (foreign key) - for user messages
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    # Message metadata (custom data, model response info, etc.)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Message editing fields
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when message was last edited",
    )

    original_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Original content before first edit (preserved for history)",
    )

    is_regenerated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Whether this is a regenerated assistant response",
    )

    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="Parent message ID for regenerated responses",
    )

    # Associated conversation
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    # Associated user (for user messages)
    user: Mapped["User | None"] = relationship("User")

    # Self-referential relationship for regenerated messages
    parent_message: Mapped["Message | None"] = relationship(
        "Message", remote_side="Message.id", foreign_keys=[parent_message_id]
    )

    def __repr__(self):
        return f"<Message(type='{self.message_type}', conversation_id='{self.conversation_id}')>"


class ConversationShare(Base):
    """Conversation share table - stores shareable links for conversations or messages"""

    __tablename__ = "conversation_shares"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    scope: Mapped[ConversationShareScopeEnum] = mapped_column(
        SQLEnum(ConversationShareScopeEnum), nullable=False
    )

    start_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )

    end_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )

    status: Mapped[ConversationShareStatusEnum] = mapped_column(
        SQLEnum(ConversationShareStatusEnum),
        default=ConversationShareStatusEnum.ACTIVE,
        nullable=False,
    )

    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    extra_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="shares"
    )

    creator: Mapped["User"] = relationship("User")

    start_message: Mapped["Message | None"] = relationship(
        "Message", foreign_keys=[start_message_id]
    )

    end_message: Mapped["Message | None"] = relationship(
        "Message", foreign_keys=[end_message_id]
    )

    def __repr__(self):
        return f"<ConversationShare(conversation_id='{self.conversation_id}', scope='{self.scope.value}')>"


class PinnedAssistant(Base):
    """Pinned assistants for users"""

    __tablename__ = "pinned_assistants"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    assistant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="pinned_assistants")
    assistant: Mapped["Assistant"] = relationship("Assistant")

    __table_args__ = (
        UniqueConstraint("user_id", "assistant_id", name="uq_user_assistant_pin"),
    )
