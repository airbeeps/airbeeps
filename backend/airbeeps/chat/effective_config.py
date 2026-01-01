from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from airbeeps.system_config.assistant_defaults import (
    ASSISTANT_GENERATION_DEFAULTS_KEY,
    ASSISTANT_RAG_DEFAULTS_KEY,
    AssistantGenerationDefaults,
    AssistantRAGDefaults,
)
from airbeeps.system_config.service import config_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from airbeeps.assistants.models import Assistant

logger = logging.getLogger(__name__)

UI_GENERATE_FOLLOWUP_QUESTIONS_KEY = "ui_generate_followup_questions"
UI_FOLLOWUP_QUESTION_COUNT_KEY = "ui_followup_question_count"
CHAT_FOLLOWUP_QUESTION_LIMITS_KEY = "chat_followup_question_limits"


def _merge_dicts(*dicts: dict | None) -> dict:
    merged: dict = {}
    for d in dicts:
        if not d:
            continue
        for k, v in d.items():
            if v is None:
                continue
            merged[k] = v
    return merged


async def _get_generation_defaults(
    session: AsyncSession,
) -> AssistantGenerationDefaults:
    raw = await config_service.get_config_value(
        session, ASSISTANT_GENERATION_DEFAULTS_KEY, default=None
    )
    try:
        return AssistantGenerationDefaults.model_validate(raw or {})
    except Exception as exc:
        logger.warning(
            "Invalid %s config in DB; falling back to defaults: %s",
            ASSISTANT_GENERATION_DEFAULTS_KEY,
            exc,
        )
        return AssistantGenerationDefaults()


async def _get_rag_defaults(session: AsyncSession) -> AssistantRAGDefaults:
    raw = await config_service.get_config_value(
        session, ASSISTANT_RAG_DEFAULTS_KEY, default=None
    )
    try:
        return AssistantRAGDefaults.model_validate(raw or {})
    except Exception as exc:
        logger.warning(
            "Invalid %s config in DB; falling back to defaults: %s",
            ASSISTANT_RAG_DEFAULTS_KEY,
            exc,
        )
        return AssistantRAGDefaults()


@dataclass(frozen=True)
class EffectiveGenerationConfig:
    temperature: float
    max_tokens: int | None
    additional_params: dict[str, Any]


@dataclass(frozen=True)
class EffectiveRAGConfig:
    retrieval_count: int
    fetch_k: int | None
    similarity_threshold: float | None
    context_max_tokens: int | None
    search_type: str
    mmr_lambda: float
    skip_smalltalk: bool
    skip_patterns: list[str]
    multi_query: bool
    multi_query_count: int
    rerank_top_k: int | None
    rerank_model_id: str | None
    hybrid_enabled: bool
    hybrid_corpus_limit: int


@dataclass(frozen=True)
class EffectiveFollowupConfig:
    enabled: bool
    count: int


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    # Avoid treating booleans as ints for numeric config.
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except Exception:
        return default


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


async def resolve_followup_config(
    session: AsyncSession, assistant: Assistant
) -> EffectiveFollowupConfig:
    """
    Resolve follow-up question settings with precedence:
      Global enable -> Assistant enable
      Global max count -> Assistant count (never exceeds global)

    Notes:
    - If global is disabled, follow-ups are always disabled.
    - Assistant overrides are read from assistant.config:
        - followup_questions_enabled (bool, default True)
        - followup_questions_count (int, optional)
    - Hard caps are sourced from SystemConfig.chat_followup_question_limits (seeded from YAML).
    """

    limits_raw = await config_service.get_config_value(
        session,
        CHAT_FOLLOWUP_QUESTION_LIMITS_KEY,
        default={"min_count": 1, "max_count": 5},
    )
    limits = limits_raw if isinstance(limits_raw, dict) else {}
    min_count = _coerce_int(limits.get("min_count"), 1)
    max_count = _coerce_int(limits.get("max_count"), 5)
    min_count = max(min_count, 1)
    max_count = max(max_count, min_count)

    global_enabled_raw = await config_service.get_config_value(
        session, UI_GENERATE_FOLLOWUP_QUESTIONS_KEY, default=False
    )
    global_enabled = _coerce_bool(global_enabled_raw, False)
    if not global_enabled:
        return EffectiveFollowupConfig(enabled=False, count=0)

    global_count_raw = await config_service.get_config_value(
        session, UI_FOLLOWUP_QUESTION_COUNT_KEY, default=3
    )
    global_count = _clamp_int(_coerce_int(global_count_raw, 3), min_count, max_count)

    assistant_enabled_raw = getattr(assistant, "followup_questions_enabled", True)
    assistant_enabled = _coerce_bool(assistant_enabled_raw, True)
    if not assistant_enabled:
        return EffectiveFollowupConfig(enabled=False, count=0)

    assistant_count_raw = getattr(assistant, "followup_questions_count", None)
    if assistant_count_raw is None:
        return EffectiveFollowupConfig(enabled=True, count=global_count)

    assistant_count = _clamp_int(
        _coerce_int(assistant_count_raw, global_count), min_count, max_count
    )
    effective_count = min(global_count, assistant_count)
    return EffectiveFollowupConfig(enabled=True, count=effective_count)


async def resolve_generation_config(
    session: AsyncSession, assistant: Assistant
) -> EffectiveGenerationConfig:
    """
    Resolve generation parameters with precedence:
      Model.generation_config -> Global generation defaults -> Assistant overrides
    """
    defaults = await _get_generation_defaults(session)

    model_generation_config = getattr(assistant.model, "generation_config", None) or {}
    global_additional_params = defaults.additional_params or {}

    use_global = bool(getattr(assistant, "use_global_generation_defaults", True))
    assistant_additional_params = {}
    if not use_global:
        assistant_additional_params = (assistant.config or {}).get(
            "additional_params"
        ) or {}

    additional_params = _merge_dicts(
        model_generation_config,
        global_additional_params,
        assistant_additional_params,
    )

    temperature = defaults.temperature
    max_tokens = defaults.max_tokens

    if not use_global:
        # Use assistant-level values
        temperature = float(getattr(assistant, "temperature", temperature))
        max_tokens = (
            int(getattr(assistant, "max_tokens", max_tokens or 0))
            if getattr(assistant, "max_tokens", None) is not None
            else max_tokens
        )

    return EffectiveGenerationConfig(
        temperature=temperature,
        max_tokens=max_tokens,
        additional_params=additional_params,
    )


async def resolve_rag_config(
    session: AsyncSession, assistant: Assistant
) -> EffectiveRAGConfig:
    """
    Resolve RAG parameters with precedence:
      Global RAG defaults -> Assistant overrides (assistant.rag_config)
    """
    defaults = await _get_rag_defaults(session)

    use_global = bool(getattr(assistant, "use_global_rag_defaults", True))
    overrides = {}
    if not use_global:
        overrides = getattr(assistant, "rag_config", None) or {}

    # Merge per-field overrides
    merged = {**defaults.model_dump(), **(overrides or {})}

    return EffectiveRAGConfig(
        retrieval_count=int(merged.get("retrieval_count", defaults.retrieval_count)),
        fetch_k=merged.get("fetch_k"),
        similarity_threshold=merged.get("similarity_threshold"),
        context_max_tokens=merged.get("context_max_tokens"),
        search_type=str(merged.get("search_type", defaults.search_type)),
        mmr_lambda=float(merged.get("mmr_lambda", defaults.mmr_lambda)),
        skip_smalltalk=bool(merged.get("skip_smalltalk", defaults.skip_smalltalk)),
        skip_patterns=list(merged.get("skip_patterns") or []),
        multi_query=bool(merged.get("multi_query", defaults.multi_query)),
        multi_query_count=int(
            merged.get("multi_query_count", defaults.multi_query_count)
        ),
        rerank_top_k=merged.get("rerank_top_k"),
        rerank_model_id=merged.get("rerank_model_id"),
        hybrid_enabled=bool(merged.get("hybrid_enabled", defaults.hybrid_enabled)),
        hybrid_corpus_limit=int(
            merged.get("hybrid_corpus_limit", defaults.hybrid_corpus_limit)
        ),
    )
