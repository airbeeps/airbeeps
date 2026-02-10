"""
Agent data models - Tool execution engine for Assistants
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base

if TYPE_CHECKING:
    from airbeeps.assistants.models import Assistant, Conversation
    from airbeeps.users.models import User


class AgentExecutionStatusEnum(enum.Enum):
    """Agent execution status enumeration"""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class MCPServerTypeEnum(enum.Enum):
    """MCP server type enumeration"""

    STDIO = "STDIO"  # Standard input/output
    SSE = "SSE"  # Server-sent events
    HTTP = "HTTP"  # HTTP protocol


# Assistant and MCP server many-to-many relationship table
assistant_mcp_servers = Table(
    "assistant_mcp_servers",
    Base.metadata,
    Column(
        "assistant_id",
        GUID,
        ForeignKey("assistants.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "mcp_server_id",
        GUID,
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class AgentExecution(Base):
    """Agent execution record table - tracks tool usage in conversations"""

    __tablename__ = "agent_executions"

    # Conversation ID
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    # Input text
    input_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Output text
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution status
    status: Mapped[AgentExecutionStatusEnum] = mapped_column(
        SQLEnum(AgentExecutionStatusEnum),
        default=AgentExecutionStatusEnum.RUNNING,
        nullable=False,
    )

    # Thought chain (reasoning process, JSON format)
    # Structure: [{"step": 1, "thought": "...", "action": "...", "observation": "..."}]
    thought_chain: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )

    # Token usage statistics
    token_usage: Mapped[dict[str, int]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    # Error message (if failed)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution metadata (use extra_data to avoid SQLAlchemy conflict)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation")

    def __repr__(self):
        return f"<AgentExecution(conversation_id='{self.conversation_id}', status='{self.status}')>"


class MCPServerConfig(Base):
    """MCP server configuration table"""

    __tablename__ = "mcp_servers"

    # Server name (unique)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Server description
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Server type
    server_type: Mapped[MCPServerTypeEnum] = mapped_column(
        SQLEnum(MCPServerTypeEnum), default=MCPServerTypeEnum.STDIO, nullable=False
    )

    # Connection configuration (JSON format)
    # For STDIO: {"command": "npx", "args": [...], "env": {...}}
    # For SSE/HTTP: {"url": "...", "headers": {...}}
    connection_config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False
    )

    # Whether this server is active
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Server metadata (use extra_data to avoid SQLAlchemy conflict)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    # Relationships
    assistants: Mapped[list["Assistant"]] = relationship(
        "Assistant", secondary=assistant_mcp_servers, back_populates="mcp_servers"
    )

    def __repr__(self):
        return f"<MCPServerConfig(name='{self.name}', type='{self.server_type}')>"


class CollaborationStatusEnum(enum.Enum):
    """Multi-agent collaboration status"""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    LOOP_DETECTED = "LOOP_DETECTED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class AgentCollaborationLog(Base):
    """
    Log of multi-agent collaboration sessions.

    Tracks the full history of agent handoffs and results
    for analysis and debugging.
    """

    __tablename__ = "agent_collaboration_logs"

    # Conversation ID (optional - collaboration can happen outside conversations)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # User who initiated the collaboration
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Initial assistant (entry point)
    initial_assistant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"),
        nullable=True,
    )

    # User input that triggered collaboration
    user_input: Mapped[str] = mapped_column(Text, nullable=False)

    # Final output from collaboration
    final_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Collaboration status
    status: Mapped[CollaborationStatusEnum] = mapped_column(
        SQLEnum(CollaborationStatusEnum),
        default=CollaborationStatusEnum.RUNNING,
        nullable=False,
    )

    # Agent chain (ordered list of specialist types used)
    # Format: ["GENERAL", "RESEARCH", "CODE"]
    agent_chain: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # Detailed steps (full history)
    # Format: [{"step": 1, "specialist": "RESEARCH", "assistant_id": "...", "input": "...", "output": "...", ...}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # Total iterations across all agents
    total_iterations: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Total cost in USD
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Total duration in milliseconds
    total_duration_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Number of handoffs that occurred
    handoff_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Error message (if failed)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Error type (if failed)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Additional metadata
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # Timestamp when collaboration ended
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    conversation: Mapped["Conversation | None"] = relationship("Conversation")
    user: Mapped["User"] = relationship("User")
    initial_assistant: Mapped["Assistant | None"] = relationship("Assistant")

    def __repr__(self):
        return (
            f"<AgentCollaborationLog(id='{self.id}', "
            f"status='{self.status.value}', "
            f"handoffs={self.handoff_count})>"
        )


class RoutingRuleTypeEnum(enum.Enum):
    """Types of routing rules"""

    KEYWORD = "KEYWORD"  # Simple keyword matching
    REGEX = "REGEX"  # Regular expression matching
    LLM = "LLM"  # LLM-based classification prompt


class ApprovalStatusEnum(enum.Enum):
    """Status of tool approval requests"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ToolApprovalRequest(Base):
    """
    Tool approval request for high-risk tool usage.

    Tracks requests for using tools that require admin approval.
    """

    __tablename__ = "tool_approval_requests"

    # User requesting approval
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tool name
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Request context
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason/justification for the request",
    )

    # Parameters the user wants to use (for auditing)
    requested_parameters: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # Conversation context (optional)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    status: Mapped[ApprovalStatusEnum] = mapped_column(
        SQLEnum(ApprovalStatusEnum),
        default=ApprovalStatusEnum.PENDING,
        nullable=False,
        index=True,
    )

    # Reviewer info
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reviewer_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Expiration (for time-limited approvals)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When approval expires (null = no expiration)",
    )

    # Number of uses allowed (null = unlimited within expiration)
    max_uses: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum number of uses for this approval",
    )

    uses_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
        comment="Number of times this approval has been used",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    reviewed_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[reviewed_by_id]
    )
    conversation: Mapped["Conversation | None"] = relationship("Conversation")

    def __repr__(self):
        return (
            f"<ToolApprovalRequest(user_id='{self.user_id}', "
            f"tool='{self.tool_name}', status='{self.status.value}')>"
        )

    def is_valid(self) -> bool:
        """Check if approval is still valid (not expired, uses remaining)."""
        if self.status != ApprovalStatusEnum.APPROVED:
            return False

        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False

        if self.max_uses is not None and self.uses_count >= self.max_uses:
            return False

        return True


class ToolApprovalPolicy(Base):
    """
    Approval policy for tools.

    Defines auto-approval rules and default settings for tool approvals.
    """

    __tablename__ = "tool_approval_policies"

    # Tool name (or "*" for default)
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    # Whether auto-approval is enabled
    auto_approve_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    # Auto-approve conditions (JSON)
    # e.g., {"max_daily_uses": 5, "allowed_users": ["uuid1", "uuid2"]}
    auto_approve_conditions: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # Default expiration hours for approvals (null = no expiration)
    default_expiration_hours: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Default max uses for approvals
    default_max_uses: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Whether notifications are sent
    notify_on_request: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    def __repr__(self):
        return f"<ToolApprovalPolicy(tool='{self.tool_name}', auto_approve={self.auto_approve_enabled})>"


class CustomSpecialistType(Base):
    """
    Custom specialist type configuration.

    Allows administrators to define new specialist types beyond the built-in ones.
    """

    __tablename__ = "custom_specialist_types"

    # Unique name for the specialist type (e.g., "LEGAL", "MEDICAL")
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    # Display name
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tools available to this specialist
    tools: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # System prompt suffix for this specialist
    system_prompt_suffix: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    # Configuration
    max_iterations: Mapped[int] = mapped_column(
        Integer,
        default=5,
        server_default="5",
        nullable=False,
    )

    cost_limit_usd: Mapped[float] = mapped_column(
        Float,
        default=0.25,
        server_default="0.25",
        nullable=False,
    )

    # Which specialists this can hand off to (list of specialist names)
    can_handoff_to: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # Priority keywords for routing
    priority_keywords: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON),
        nullable=False,
        default=list,
    )

    # Whether this specialist is enabled
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # Creator
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    created_by: Mapped["User | None"] = relationship("User")
    routing_rules: Mapped[list["SpecialistRoutingRule"]] = relationship(
        "SpecialistRoutingRule",
        back_populates="specialist",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<CustomSpecialistType(name='{self.name}')>"


class SpecialistRoutingRule(Base):
    """
    Routing rule for specialist selection.

    Defines rules for routing requests to specific specialists.
    """

    __tablename__ = "specialist_routing_rules"

    # Specialist type (either built-in name or custom specialist ID)
    specialist_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Optional link to custom specialist
    custom_specialist_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("custom_specialist_types.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Rule type
    rule_type: Mapped[RoutingRuleTypeEnum] = mapped_column(
        SQLEnum(RoutingRuleTypeEnum),
        nullable=False,
    )

    # Rule value/pattern
    # For KEYWORD: comma-separated keywords
    # For REGEX: regular expression pattern
    # For LLM: classification prompt
    rule_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Priority (higher = checked first)
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    # Whether this rule is enabled
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # Description/notes
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    specialist: Mapped["CustomSpecialistType | None"] = relationship(
        "CustomSpecialistType",
        back_populates="routing_rules",
    )

    def __repr__(self):
        return (
            f"<SpecialistRoutingRule(specialist='{self.specialist_name}', "
            f"type='{self.rule_type.value}', priority={self.priority})>"
        )


class SpecialistPerformanceMetric(Base):
    """
    Performance metrics for specialist agents.

    Aggregated statistics for analytics dashboards.
    """

    __tablename__ = "specialist_performance_metrics"

    # Specialist name (built-in or custom)
    specialist_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Time period (date for daily aggregation)
    period_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Metrics
    total_invocations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_invocations: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    failed_invocations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_handoffs_from: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_handoffs_to: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_iterations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Tool usage counts
    tool_usage: Mapped[dict[str, int]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    # Unique constraint on specialist + date
    __table_args__ = (
        UniqueConstraint("specialist_name", "period_date", name="uq_specialist_period"),
    )

    def __repr__(self):
        return (
            f"<SpecialistPerformanceMetric(specialist='{self.specialist_name}', "
            f"date='{self.period_date.date()}')>"
        )
