import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from airbeeps.ai_models.api.v1.schemas import ModelBase
from airbeeps.assistants.models import (
    AssistantStatusEnum,
    ConversationShareScopeEnum,
    ConversationShareStatusEnum,
    ConversationStatusEnum,
    MessageTypeEnum,
)
from airbeeps.feedback.models import MessageFeedbackRatingEnum


class GenerateTitleResponse(BaseModel):
    """Generate Title Response"""

    conversation_id: uuid.UUID = Field(..., description="Conversation ID")
    title: str = Field(..., description="Generated title")
    model_used: str = Field(..., description="Model used")
    updated: bool = Field(..., description="Whether updated in database")


# RAG configuration schema
class RAGConfig(BaseModel):
    """Retrieval configuration for assistants"""

    retrieval_count: int = Field(
        default=5, ge=1, le=50, description="Number of chunks to retrieve"
    )
    fetch_k: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Initial fetch size before filtering/dedup (defaults to 3x retrieval_count)",
    )
    similarity_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Similarity threshold for retrieval"
    )
    context_max_tokens: int | None = Field(
        default=1200,
        ge=200,
        le=6000,
        description="Max tokens to allocate to RAG context in the prompt",
    )
    search_type: str = Field(
        default="similarity",
        description="Retriever search type: similarity|mmr",
    )
    mmr_lambda: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="MMR lambda (only used when search_type=mmr)",
    )
    rerank_model_id: uuid.UUID | None = Field(
        default=None,
        description="Optional model ID to use for reranking (fallback to embedding model if not set).",
    )
    skip_smalltalk: bool = Field(
        default=False,
        description="If true, skip RAG for greetings/acks/short small-talk messages.",
    )
    skip_patterns: list[str] = Field(
        default_factory=list,
        description="Optional list of phrases to treat as small-talk (case-insensitive).",
    )


# Assistant schemas
class AssistantBase(BaseModel):
    """Base assistant schema"""

    name: str = Field(..., max_length=200, description="Assistant name")
    description: str | None = Field(None, description="Assistant description")
    system_prompt: str | None = Field(
        None, description="System prompt for the assistant"
    )
    avatar_file_path: str | None = Field(None, max_length=500, description="Avatar URL")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Model configuration"
    )
    is_public: bool = Field(default=False, description="Whether assistant is public")
    rag_config: RAGConfig = Field(
        default_factory=RAGConfig, description="RAG configuration"
    )


class AssistantCreate(AssistantBase):
    """Schema for creating an assistant"""

    model_id: uuid.UUID = Field(..., description="Model ID to use")
    status: AssistantStatusEnum = Field(
        default=AssistantStatusEnum.DRAFT, description="Assistant status"
    )
    knowledge_base_ids: list[uuid.UUID] | None = Field(
        default_factory=list, description="Knowledge base IDs to associate"
    )


class AssistantUpdate(BaseModel):
    """Schema for updating an assistant"""

    name: str | None = Field(None, max_length=200, description="Assistant name")
    description: str | None = Field(None, description="Assistant description")
    system_prompt: str | None = Field(
        None, description="System prompt for the assistant"
    )
    avatar_file_path: str | None = Field(None, max_length=500, description="Avatar URL")
    model_id: uuid.UUID | None = Field(None, description="Model ID to use")
    config: dict[str, Any] | None = Field(None, description="Model configuration")
    status: AssistantStatusEnum | None = Field(None, description="Assistant status")
    is_public: bool | None = Field(None, description="Whether assistant is public")
    rag_config: RAGConfig | None = Field(None, description="RAG configuration")
    knowledge_base_ids: list[uuid.UUID] | None = Field(
        None, description="Knowledge base IDs to associate"
    )


class AssistantResponse(AssistantBase):
    """Schema for assistant response"""

    id: uuid.UUID
    model_id: uuid.UUID
    owner_id: uuid.UUID
    status: AssistantStatusEnum
    created_at: datetime
    updated_at: datetime
    knowledge_base_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Associated knowledge base IDs"
    )

    # Related objects
    model: ModelBase | None = None

    # Computed field for avatar URL
    avatar_url: str | None = Field(None, description="Full avatar URL")

    model_config = ConfigDict(from_attributes=True)


# Conversation schemas
class ConversationBase(BaseModel):
    """Base conversation schema"""

    title: str = Field(..., max_length=500, description="Conversation title")


class ConversationCreate(ConversationBase):
    """Schema for creating a conversation"""

    assistant_id: uuid.UUID = Field(..., description="Assistant ID")


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation"""

    title: str | None = Field(None, max_length=500, description="Conversation title")
    status: ConversationStatusEnum | None = Field(
        None, description="Conversation status"
    )


class ConversationResponse(ConversationBase):
    """Schema for conversation response"""

    id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID
    status: ConversationStatusEnum
    last_message_at: datetime | None
    message_count: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    # Related objects
    assistant_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("extra_data", mode="before")
    @classmethod
    def _default_extra_data(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        return value or {}


# Message schemas
class MessageBase(BaseModel):
    """Base message schema"""

    content: str = Field(..., description="Message content")


class MessageCreate(MessageBase):
    """Schema for creating a message"""

    message_type: MessageTypeEnum = Field(..., description="Message type")
    conversation_id: uuid.UUID = Field(..., description="Conversation ID")
    extra_data: dict[str, Any] = Field(
        default_factory=dict, description="Message metadata"
    )


class MessageResponse(MessageBase):
    """Schema for message response"""

    id: uuid.UUID
    message_type: MessageTypeEnum
    conversation_id: uuid.UUID
    user_id: uuid.UUID | None = None
    token_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("extra_data", mode="before")
    @classmethod
    def _default_extra_data(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        return value or {}


# Message feedback schemas
class MessageFeedbackCreate(BaseModel):
    """Schema for creating/updating feedback for a message."""

    rating: MessageFeedbackRatingEnum = Field(..., description="Thumb rating (UP/DOWN)")
    reasons: list[str] = Field(
        default_factory=list,
        description="User-selected reason tags (quick options)",
        max_length=20,
    )
    comment: str | None = Field(
        default=None, description="Optional free-text feedback", max_length=5000
    )
    extra_data: dict[str, Any] = Field(
        default_factory=dict, description="Optional structured metadata"
    )


class MessageFeedbackResponse(BaseModel):
    """Schema for message feedback response."""

    id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    assistant_id: uuid.UUID
    user_id: uuid.UUID
    rating: MessageFeedbackRatingEnum
    reasons: list[str] = Field(default_factory=list)
    comment: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("reasons", mode="before")
    @classmethod
    def _default_reasons(cls, value: list[str] | None) -> list[str]:
        return value or []

    @field_validator("extra_data", mode="before")
    @classmethod
    def _default_feedback_extra_data(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any]:
        return value or {}


# Conversation share schemas
class ConversationShareCreateRequest(BaseModel):
    """Request body for creating a conversation share link"""

    conversation_id: uuid.UUID = Field(..., description="Conversation ID")
    scope: ConversationShareScopeEnum = Field(..., description="Share scope")
    start_message_id: uuid.UUID | None = Field(
        None, description="Start message ID when sharing a specific Q/A pair"
    )
    end_message_id: uuid.UUID | None = Field(
        None, description="End message ID when sharing a specific Q/A pair"
    )


class ConversationShareResponse(BaseModel):
    """Response for share creation"""

    id: uuid.UUID
    conversation_id: uuid.UUID
    scope: ConversationShareScopeEnum
    status: ConversationShareStatusEnum
    start_message_id: uuid.UUID | None
    end_message_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SharedMessage(BaseModel):
    """Simplified message for public share response"""

    id: uuid.UUID
    message_type: MessageTypeEnum
    content: str
    extra_data: dict[str, Any] = Field(
        default_factory=dict, description="Message metadata"
    )
    created_at: datetime


class AssistantShareInfo(BaseModel):
    """Assistant metadata exposed via public share"""

    id: uuid.UUID
    name: str
    description: str | None = None
    avatar_file_path: str | None = Field(
        None, description="Assistant avatar storage path"
    )
    avatar_url: str | None = Field(None, description="Public URL for avatar image")
    translations: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Localized fields"
    )


class ConversationSharePublicResponse(BaseModel):
    """Public share payload that is accessible without auth"""

    id: uuid.UUID
    conversation_id: uuid.UUID
    scope: ConversationShareScopeEnum
    assistant_id: uuid.UUID | None = None
    assistant_name: str
    assistant_description: str | None = None
    assistant: AssistantShareInfo | None = None
    conversation_title: str
    messages: list[SharedMessage]
    created_at: datetime


# Chat schemas for API
class ImageAttachment(BaseModel):
    """Image attachment for chat message"""

    data_url: str | None = Field(
        None, description="Base64 encoded image data URL (data:image/...;base64,...)"
    )
    url: str | None = Field(None, description="Server URL for uploaded image")
    alt: str | None = Field(None, description="Alternative text for image")
    mime_type: str | None = Field(
        None, alias="mimeType", description="MIME type for the attachment"
    )
    size: int | None = Field(None, description="File size in bytes")
    file_key: str | None = Field(
        None,
        alias="fileKey",
        description="Internal storage key (S3 object path)",
    )

    model_config = ConfigDict(populate_by_name=True)


class ChatRequest(BaseModel):
    """Chat message request"""

    content: str = Field(..., description="Message content")
    conversation_id: uuid.UUID = Field(..., description="Conversation ID")
    images: list[ImageAttachment] | None = Field(
        None, description="Image attachments (for vision models)"
    )
    language: str | None = Field(
        None, description="Language code for localization (e.g. en-US)"
    )


class ChatMessageResponse(BaseModel):
    """Chat message response"""

    conversation_id: uuid.UUID
    user_message: MessageResponse
    assistant_message: MessageResponse


# Streaming chat schemas
class StreamEventType(str, Enum):
    """Stream event types"""

    ASSISTANT_MESSAGE_START = "assistant_message_start"
    CONTENT_CHUNK = "content_chunk"
    ASSISTANT_MESSAGE_COMPLETE = "assistant_message_complete"
    ERROR = "error"


class StreamAssistantMessageStartData(BaseModel):
    """Stream assistant message start data"""

    id: str
    conversation_id: str
    message_type: str
    model: str
    created_at: str


class StreamMediaItem(BaseModel):
    """Media payload emitted during streaming."""

    id: str | None = None
    type: str = Field(default="image")
    mime_type: str
    data_url: str | None = None
    url: str | None = None
    alt: str | None = None
    index: int | None = None
    source: str | None = None


class StreamContentChunkData(BaseModel):
    """Stream content chunk data"""

    content: str
    is_final: bool
    media: list[StreamMediaItem] | None = None


class StreamAssistantMessageCompleteData(BaseModel):
    """Stream assistant message complete data

    Includes extra_data for follow-up questions and other metadata.
    """

    id: str
    content: str
    conversation_id: str
    message_type: str
    model: str
    created_at: str
    updated_at: str
    user_message_id: str
    media: list[StreamMediaItem] | None = None
    extra_data: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None


class StreamErrorData(BaseModel):
    """Stream error data"""

    error: str
    conversation_id: str


class StreamEvent(BaseModel):
    """Stream event wrapper"""

    type: StreamEventType
    data: dict[str, Any]


# List responses
class AssistantListResponse(BaseModel):
    """Assistant list response with pagination"""

    items: list[AssistantResponse]
    total: int
    page: int
    size: int
    pages: int


class ConversationListResponse(BaseModel):
    """Conversation list response with pagination"""

    items: list[ConversationResponse]
    total: int
    page: int
    size: int
    pages: int


class MessageListResponse(BaseModel):
    """Message list response with pagination"""

    items: list[MessageResponse]
    total: int
    page: int
    size: int
    pages: int


# Dashboard schemas
class DashboardOverview(BaseModel):
    """Dashboard overview metrics"""

    total_users: int
    total_conversations: int
    total_documents: int


class ChartDataPoint(BaseModel):
    """Generic chart data point"""

    name: str
    value: float
    extra: dict[str, Any] | None = None


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response"""

    overview: DashboardOverview
    user_growth: list[ChartDataPoint]
    top_assistants: list[dict[str, Any]]
    recent_users: list[dict[str, Any]]


class AnalyticsStatsResponse(BaseModel):
    """Analytics statistics response"""

    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_execution_time_ms: int
    avg_execution_time_ms: float

    # Charts data
    daily_tokens: list[dict[str, Any]]  # date, input, output
    daily_requests: list[ChartDataPoint]
    daily_latency: list[ChartDataPoint]
