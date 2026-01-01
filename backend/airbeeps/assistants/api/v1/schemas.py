import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from airbeeps.ai_models.api.v1.schemas import ModelBase
from airbeeps.assistants.models import AssistantModeEnum, AssistantStatusEnum
from airbeeps.config import settings


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
    skip_smalltalk: bool = Field(
        default=False,
        description="If true, skip RAG for greetings/acks/short small-talk messages.",
    )
    skip_patterns: list[str] = Field(
        default_factory=list,
        description="Optional list of phrases to treat as small-talk (case-insensitive).",
    )
    multi_query: bool = Field(
        default=False,
        description="Generate alternative queries for better recall (heuristic, no LLM).",
    )
    multi_query_count: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Max alternative queries to generate when multi_query is true.",
    )
    rerank_top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional embedding-based rerank depth.",
    )
    rerank_model_id: uuid.UUID | None = Field(
        default=None,
        description="Optional model ID to use for reranking (fallback to embedding model if not set).",
    )
    hybrid_enabled: bool = Field(
        default=False,
        description="Enable lightweight BM25 lexical fusion with dense results.",
    )
    hybrid_corpus_limit: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Max chunks to consider for BM25 (limits memory/time).",
    )


# Assistant schemas
class AssistantBase(BaseModel):
    """Base assistant schema"""

    name: str = Field(..., max_length=200, description="Assistant name")
    description: str | None = Field(None, description="Assistant description")
    system_prompt: str | None = Field(
        None, description="System prompt for the assistant"
    )
    mode: AssistantModeEnum = Field(
        default=AssistantModeEnum.GENERAL, description="Assistant mode (GENERAL|RAG)"
    )
    avatar_file_path: str | None = Field(None, max_length=500, description="Avatar URL")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Model configuration"
    )
    followup_questions_enabled: bool = Field(
        default=True,
        description="Whether follow-up question suggestions are enabled for this assistant (effective only when globally enabled)",
    )
    followup_questions_count: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Preferred follow-up question count (capped by global setting)",
    )
    use_global_generation_defaults: bool = Field(
        default=True,
        description="If true, inherit global generation defaults; if false, use assistant overrides",
    )
    use_global_rag_defaults: bool = Field(
        default=True,
        description="If true, inherit global RAG defaults; if false, use assistant overrides",
    )
    temperature: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Temperature for text generation (0.0-2.0)",
    )
    max_tokens: int | None = Field(
        default=2048, ge=1, description="Maximum number of tokens to generate"
    )
    max_history_messages: int | None = Field(
        default=None,
        ge=0,
        description="Maximum number of history messages to include in context (None for no limit)",
    )
    is_public: bool = Field(default=False, description="Whether assistant is public")
    rag_config: RAGConfig | None = Field(
        default=None,
        description="RAG configuration overrides (only used when not inheriting defaults)",
    )

    # Agent configuration
    enable_agent: bool = Field(
        default=False, description="Whether to enable agent (tool calling) capabilities"
    )
    agent_max_iterations: int = Field(
        default=5, ge=1, le=20, description="Maximum iterations for agent reasoning"
    )
    agent_enabled_tools: list[str] = Field(
        default_factory=list, description="List of enabled tool names for agent"
    )
    agent_tool_config: dict[str, Any] = Field(
        default_factory=dict, description="Tool configuration parameters for agent"
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
    mcp_server_ids: list[uuid.UUID] | None = Field(
        default_factory=list, description="MCP server IDs to attach for agent tools"
    )


class AssistantUpdate(BaseModel):
    """Schema for updating an assistant"""

    name: str | None = Field(None, max_length=200, description="Assistant name")
    description: str | None = Field(None, description="Assistant description")
    system_prompt: str | None = Field(
        None, description="System prompt for the assistant"
    )
    mode: AssistantModeEnum | None = Field(
        None, description="Assistant mode (GENERAL|RAG)"
    )
    avatar_file_path: str | None = Field(None, max_length=500, description="Avatar URL")
    model_id: uuid.UUID | None = Field(None, description="Model ID to use")
    config: dict[str, Any] | None = Field(None, description="Model configuration")
    followup_questions_enabled: bool | None = Field(
        None,
        description="Whether follow-up question suggestions are enabled for this assistant (effective only when globally enabled)",
    )
    followup_questions_count: int | None = Field(
        None,
        ge=1,
        le=5,
        description="Preferred follow-up question count (capped by global setting)",
    )
    use_global_generation_defaults: bool | None = Field(
        None,
        description="If true, inherit global generation defaults; if false, use assistant overrides",
    )
    use_global_rag_defaults: bool | None = Field(
        None,
        description="If true, inherit global RAG defaults; if false, use assistant overrides",
    )
    temperature: float | None = Field(
        None, ge=0.0, le=2.0, description="Temperature for text generation (0.0-2.0)"
    )
    max_tokens: int | None = Field(
        None, ge=1, description="Maximum number of tokens to generate"
    )
    max_history_messages: int | None = Field(
        None,
        ge=0,
        description="Maximum number of history messages to include in context (None for no limit)",
    )
    status: AssistantStatusEnum | None = Field(None, description="Assistant status")
    is_public: bool | None = Field(None, description="Whether assistant is public")
    rag_config: RAGConfig | None = Field(
        None, description="RAG configuration overrides"
    )
    knowledge_base_ids: list[uuid.UUID] | None = Field(
        None, description="Knowledge base IDs to associate"
    )
    mcp_server_ids: list[uuid.UUID] | None = Field(
        None, description="MCP server IDs to attach for agent tools"
    )

    # Agent configuration
    enable_agent: bool | None = Field(
        None, description="Whether to enable agent (tool calling) capabilities"
    )
    agent_max_iterations: int | None = Field(
        None, ge=1, le=20, description="Maximum iterations for agent reasoning"
    )
    agent_enabled_tools: list[str] | None = Field(
        None, description="List of enabled tool names for agent"
    )
    agent_tool_config: dict[str, Any] | None = Field(
        None, description="Tool configuration parameters for agent"
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
    mcp_server_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Attached MCP server IDs for agent tools"
    )

    # Multi-language translations
    translations: dict[str, dict[str, str]] | None = Field(
        None, description="Multi-language translations {locale: {field: value}}"
    )

    # User specific fields
    is_pinned: bool = Field(
        default=False, description="Whether the current user has pinned this assistant"
    )

    # Related objects
    model: ModelBase | None = None

    # Owner info (populated from relationship)
    owner_name: str | None = Field(
        default=None, description="Owner display name or email"
    )

    @computed_field
    def avatar_url(self) -> str | None:
        """Full avatar URL"""
        if not self.avatar_file_path:
            return None
        base_url = settings.S3_EXTERNAL_ENDPOINT_URL or settings.S3_ENDPOINT_URL
        base_url = str(base_url).rstrip("/")
        return f"{base_url}/{self.avatar_file_path}"

    model_config = ConfigDict(from_attributes=True)


# Translation management schemas
class TranslationData(BaseModel):
    """Translation data for a specific locale"""

    name: str | None = Field(None, description="Translated name")
    description: str | None = Field(None, description="Translated description")
    system_prompt: str | None = Field(None, description="Translated system prompt")


class AssistantTranslationsResponse(BaseModel):
    """Schema for assistant translations (translation management page)"""

    id: uuid.UUID
    default_name: str = Field(..., description="Default name")
    default_description: str | None = Field(None, description="Default description")
    default_system_prompt: str | None = Field(None, description="Default system prompt")
    translations: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="All translations {locale: {field: value}}"
    )
    available_locales: list[str] = Field(
        default_factory=lambda: ["ja", "ko", "es", "fr", "de"],
        description="Available locales for translation",
    )
    translation_progress: dict[str, int] = Field(
        default_factory=dict,
        description="Translation completion percentage for each locale",
    )


class UpdateTranslationRequest(BaseModel):
    """Request to update translation for a specific locale"""

    name: str | None = Field(None, description="Translated name")
    description: str | None = Field(None, description="Translated description")
    system_prompt: str | None = Field(None, description="Translated system prompt")


# List responses
class AssistantListResponse(BaseModel):
    """Assistant list response with pagination"""

    items: list[AssistantResponse]
    total: int
    page: int
    size: int
    pages: int
