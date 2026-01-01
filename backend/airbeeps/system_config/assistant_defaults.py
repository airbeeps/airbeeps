from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

# -----------------------------------------------------------------------------
# SystemConfig keys for assistant defaults
# -----------------------------------------------------------------------------

ASSISTANT_GENERATION_DEFAULTS_KEY = "assistant_generation_defaults"
ASSISTANT_RAG_DEFAULTS_KEY = "assistant_rag_defaults"


class AssistantGenerationDefaults(BaseModel):
    """Admin-defined defaults for generation (applies to GENERAL and RAG modes)."""

    temperature: float = Field(
        default=0.7, ge=0.0, le=2.0, description="Default temperature"
    )
    max_tokens: int | None = Field(
        default=2048, ge=1, description="Default max output tokens"
    )
    additional_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional LiteLLM parameters (top_p, stop, seed, etc.)",
    )


class AssistantRAGDefaults(BaseModel):
    """Admin-defined defaults for RAG retrieval and prompt context."""

    retrieval_count: int = Field(
        default=5, ge=1, le=50, description="Number of chunks to retrieve"
    )
    fetch_k: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Initial fetch size before filtering/dedup (defaults to 3x retrieval_count).",
    )
    similarity_threshold: float | None = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Similarity threshold (0-1). If None, no thresholding is applied.",
    )
    context_max_tokens: int | None = Field(
        default=1200,
        ge=200,
        le=6000,
        description="Max tokens to allocate to RAG context in the prompt",
    )
    search_type: str = Field(
        default="similarity", description="Retriever search type: similarity|mmr"
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
        description="Optional embedding-based rerank of top candidates.",
    )
    rerank_model_id: str | None = Field(
        default=None,
        description="Optional model ID to use for reranking (UUID as string).",
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

    @field_validator("search_type")
    @classmethod
    def _validate_search_type(cls, v: str) -> str:
        allowed = {"similarity", "mmr"}
        if v not in allowed:
            raise ValueError(f"search_type must be one of: {sorted(allowed)}")
        return v

    @field_validator("rerank_model_id")
    @classmethod
    def _validate_rerank_model_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip()
        if not v:
            return None
        try:
            uuid.UUID(v)
        except Exception as exc:
            raise ValueError("rerank_model_id must be a UUID string") from exc
        return v


def validate_assistant_defaults(key: str, value: Any) -> Any:
    """
    Validate and normalize assistant defaults stored in SystemConfig.

    Returns a JSON-serializable value suitable for persistence.
    """
    if key == ASSISTANT_GENERATION_DEFAULTS_KEY:
        model = AssistantGenerationDefaults.model_validate(value or {})
        return model.model_dump()
    if key == ASSISTANT_RAG_DEFAULTS_KEY:
        model = AssistantRAGDefaults.model_validate(value or {})
        return model.model_dump()
    return value
