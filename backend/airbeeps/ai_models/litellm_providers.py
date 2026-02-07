"""
LiteLLM provider utilities.

This module surfaces LiteLLM's provider list and enriches it with lightweight
metadata for UI defaults. External registry calls can be disabled, with a small
override set preserved for common providers.
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Minimal metadata overrides for common providers.
# Keep this list small; LiteLLM is the source of truth for availability.
PROVIDER_OVERRIDES: dict[str, dict[str, Any]] = {
    # OpenAI-Compatible Providers
    "groq": {
        "display_name": "Groq",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://api.groq.com/openai/v1",
        "docs_url": "https://console.groq.com/docs",
        "description": "Ultra-fast inference with Llama models",
    },
    "together_ai": {
        "display_name": "Together AI",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://api.together.xyz/v1",
        "docs_url": "https://docs.together.ai/",
        "description": "Open-source models at scale",
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://openrouter.ai/api/v1",
        "docs_url": "https://openrouter.ai/docs",
        "description": "Unified API for 100+ LLMs",
    },
    "perplexity": {
        "display_name": "Perplexity AI",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://api.perplexity.ai",
        "docs_url": "https://docs.perplexity.ai/",
        "description": "Search-augmented LLMs",
    },
    # Native Provider APIs
    "openai": {
        "display_name": "OpenAI",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://api.openai.com/v1",
        "docs_url": "https://platform.openai.com/docs",
        "description": "GPT-4, GPT-3.5, and more",
    },
    "anthropic": {
        "display_name": "Anthropic",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://api.anthropic.com",
        "docs_url": "https://docs.anthropic.com/",
        "description": "Claude models",
    },
    "gemini": {
        "display_name": "Google Gemini",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://generativelanguage.googleapis.com",
        "docs_url": "https://ai.google.dev/docs",
        "description": "Google's multimodal AI",
    },
    "azure": {
        "display_name": "Azure OpenAI",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://{deployment}.openai.azure.com",
        "docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/",
        "description": "OpenAI models on Azure",
    },
    "bedrock": {
        "display_name": "AWS Bedrock",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "",
        "docs_url": "https://docs.aws.amazon.com/bedrock/",
        "description": "Foundation models on AWS",
    },
    # Local/Self-Hosted
    "ollama": {
        "display_name": "Ollama",
        "category": "CUSTOM",
        "default_base_url": "http://localhost:11434",
        "docs_url": "https://ollama.ai/",
        "description": "Run LLMs locally",
    },
    "vllm": {
        "display_name": "vLLM",
        "category": "CUSTOM",
        "default_base_url": "http://localhost:8000/v1",
        "docs_url": "https://docs.vllm.ai/",
        "description": "High-throughput LLM serving",
    },
    "lmstudio": {
        "display_name": "LM Studio",
        "category": "CUSTOM",
        "default_base_url": "http://localhost:1234/v1",
        "docs_url": "https://lmstudio.ai/docs",
        "description": "Desktop LLM interface",
    },
    "huggingface": {
        "display_name": "HuggingFace Local Embeddings",
        "category": "LOCAL",
        "default_base_url": "local",
        "docs_url": "https://huggingface.co/docs",
        "description": "Local embeddings with sentence-transformers",
    },
}

_CACHE_TTL_SECONDS = 300
_PROVIDER_LIST_CACHE: dict[bool, dict[str, Any]] = {}
_OPENAI_COMPATIBLE_CACHE: dict[str, Any] = {}


def _fetch_litellm_provider_list() -> list[str]:
    import litellm

    if hasattr(litellm, "provider_list"):
        return list(litellm.provider_list)

    if hasattr(litellm, "models_by_provider"):
        return list(litellm.models_by_provider.keys())

    return []


def _fetch_openai_compatible_providers() -> set[str]:
    """Best-effort lookup of OpenAI-compatible providers from LiteLLM."""
    try:
        import litellm

        for attr in (
            "openai_compatible_providers",
            "openai_compatible_provider_list",
            "openai_compatible_providers_list",
        ):
            value = getattr(litellm, attr, None)
            if isinstance(value, (list, set, tuple)):
                return set(value)
    except Exception as exc:
        logger.debug("LiteLLM openai-compatible list unavailable: %s", exc)

    return set()


def _get_cached_openai_compatible_providers(allow_external: bool) -> set[str]:
    if not allow_external:
        return set()

    cached = _OPENAI_COMPATIBLE_CACHE.get("data")
    if cached:
        age = time.monotonic() - cached["ts"]
        if age < _CACHE_TTL_SECONDS:
            return cached["providers"]

    providers = _fetch_openai_compatible_providers()
    _OPENAI_COMPATIBLE_CACHE["data"] = {
        "ts": time.monotonic(),
        "providers": providers,
    }
    return providers


def _get_cached_provider_list(allow_external: bool) -> list[str]:
    cached = _PROVIDER_LIST_CACHE.get(allow_external)
    if cached:
        age = time.monotonic() - cached["ts"]
        if age < _CACHE_TTL_SECONDS:
            return list(cached["providers"])

    providers = set(PROVIDER_OVERRIDES.keys())
    if allow_external:
        try:
            providers.update(_fetch_litellm_provider_list())
        except Exception as exc:
            logger.warning("Error getting LiteLLM providers: %s", exc)

    provider_list = sorted(providers)
    _PROVIDER_LIST_CACHE[allow_external] = {
        "ts": time.monotonic(),
        "providers": provider_list,
    }
    return provider_list


def get_litellm_providers(allow_external: bool = True) -> list[str]:
    """
    Get list of all providers supported by LiteLLM.

    Returns:
        List of provider identifiers supported by LiteLLM
    """
    return _get_cached_provider_list(allow_external)


def get_provider_info(provider_id: str, allow_external: bool = True) -> dict[str, Any]:
    """
    Get metadata for a specific provider.

    Args:
        provider_id: LiteLLM provider identifier

    Returns:
        Dictionary with provider metadata
    """
    provider_id = (provider_id or "").strip()
    if not provider_id:
        return {
            "id": "",
            "display_name": "",
            "category": "PROVIDER_SPECIFIC",
            "default_base_url": "",
            "docs_url": "",
            "description": "",
        }

    override = PROVIDER_OVERRIDES.get(provider_id)
    if override:
        return {"id": provider_id, **override}

    category = "PROVIDER_SPECIFIC"
    openai_compatible = _get_cached_openai_compatible_providers(allow_external)
    if provider_id in openai_compatible:
        category = "OPENAI_COMPATIBLE"

    return {
        "id": provider_id,
        "display_name": provider_id.replace("_", " ").title(),
        "category": category,
        "default_base_url": "",
        "docs_url": f"https://docs.litellm.ai/docs/providers/{provider_id}",
        "description": f"LiteLLM-supported provider: {provider_id}",
    }


def get_all_providers_info(allow_external: bool = True) -> list[dict[str, Any]]:
    """
    Get metadata for all LiteLLM providers.

    Returns:
        List of provider metadata dictionaries
    """
    providers = get_litellm_providers(allow_external=allow_external)
    return [get_provider_info(p, allow_external=allow_external) for p in providers]


def get_providers_by_category(
    allow_external: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """
    Get providers grouped by category.

    Returns:
        Dictionary mapping category to list of provider info
    """
    all_providers = get_all_providers_info(allow_external=allow_external)

    categorized = {
        "OPENAI_COMPATIBLE": [],
        "PROVIDER_SPECIFIC": [],
        "CUSTOM": [],
        "LOCAL": [],
    }

    for provider in all_providers:
        category = provider.get("category", "PROVIDER_SPECIFIC")
        categorized[category].append(provider)

    # Sort each category by display name
    for category in categorized:
        categorized[category].sort(key=lambda p: p["display_name"])

    return categorized


def get_openai_compatible_providers(
    allow_external: bool = True,
) -> list[dict[str, Any]]:
    """Get list of OpenAI-compatible providers."""
    return get_providers_by_category(allow_external=allow_external)["OPENAI_COMPATIBLE"]


def get_native_providers(allow_external: bool = True) -> list[dict[str, Any]]:
    """Get list of native/provider-specific providers."""
    return get_providers_by_category(allow_external=allow_external)["PROVIDER_SPECIFIC"]


def get_custom_providers(allow_external: bool = True) -> list[dict[str, Any]]:
    """Get list of custom/self-hosted providers."""
    return get_providers_by_category(allow_external=allow_external)["CUSTOM"]
