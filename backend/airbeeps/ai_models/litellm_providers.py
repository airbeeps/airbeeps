"""
LiteLLM provider utilities.

This module provides utilities to work with LiteLLM's built-in provider list
and model information, avoiding the need to maintain a static catalog.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Provider metadata for common providers
# This is minimal metadata to help users - the actual provider support comes from LiteLLM
PROVIDER_METADATA = {
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
    "deepinfra": {
        "display_name": "DeepInfra",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://api.deepinfra.com/v1/openai",
        "docs_url": "https://deepinfra.com/docs",
        "description": "Serverless inference for open models",
    },
    "fireworks_ai": {
        "display_name": "Fireworks AI",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://api.fireworks.ai/inference/v1",
        "docs_url": "https://docs.fireworks.ai/",
        "description": "Fast inference for open models",
    },
    "anyscale": {
        "display_name": "Anyscale",
        "category": "OPENAI_COMPATIBLE",
        "default_base_url": "https://api.endpoints.anyscale.com/v1",
        "docs_url": "https://docs.anyscale.com/",
        "description": "Ray-powered model serving",
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
    "vertex_ai": {
        "display_name": "Google Vertex AI",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "",  # Uses Google Cloud project
        "docs_url": "https://cloud.google.com/vertex-ai/docs",
        "description": "Enterprise Google AI on GCP",
    },
    "bedrock": {
        "display_name": "AWS Bedrock",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "",  # Uses AWS credentials
        "docs_url": "https://docs.aws.amazon.com/bedrock/",
        "description": "Foundation models on AWS",
    },
    "azure": {
        "display_name": "Azure OpenAI",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://{deployment}.openai.azure.com",
        "docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/",
        "description": "OpenAI models on Azure",
    },
    "cohere": {
        "display_name": "Cohere",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://api.cohere.ai",
        "docs_url": "https://docs.cohere.com/",
        "description": "Command and embedding models",
    },
    "mistral": {
        "display_name": "Mistral AI",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://api.mistral.ai",
        "docs_url": "https://docs.mistral.ai/",
        "description": "Open and commercial models",
    },
    "xai": {
        "display_name": "xAI",
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "https://api.x.ai/v1",
        "docs_url": "https://docs.x.ai/",
        "description": "Grok models",
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
        "display_name": "HuggingFace (Local)",
        "category": "LOCAL",
        "default_base_url": "local",
        "docs_url": "https://huggingface.co/docs",
        "description": "Local embeddings with sentence-transformers",
    },
}


def get_litellm_providers() -> list[str]:
    """
    Get list of all providers supported by LiteLLM.

    Returns:
        List of provider identifiers supported by LiteLLM
    """
    try:
        import litellm

        # LiteLLM exposes provider_list constant
        if hasattr(litellm, "provider_list"):
            return list(litellm.provider_list)

        # Fallback: get from models_by_provider keys
        if hasattr(litellm, "models_by_provider"):
            return list(litellm.models_by_provider.keys())

        logger.warning("Could not find provider_list in LiteLLM, using metadata keys")
        return list(PROVIDER_METADATA.keys())

    except Exception as e:
        logger.error(f"Error getting LiteLLM providers: {e}")
        return list(PROVIDER_METADATA.keys())


def get_provider_info(provider_id: str) -> dict[str, Any]:
    """
    Get metadata for a specific provider.

    Args:
        provider_id: LiteLLM provider identifier

    Returns:
        Dictionary with provider metadata
    """
    # Check if we have metadata for this provider
    if provider_id in PROVIDER_METADATA:
        return {
            "id": provider_id,
            **PROVIDER_METADATA[provider_id],
        }

    # Return minimal info for unknown providers
    return {
        "id": provider_id,
        "display_name": provider_id.replace("_", " ").title(),
        "category": "PROVIDER_SPECIFIC",
        "default_base_url": "",
        "docs_url": f"https://docs.litellm.ai/docs/providers/{provider_id}",
        "description": f"LiteLLM-supported provider: {provider_id}",
    }


def get_all_providers_info() -> list[dict[str, Any]]:
    """
    Get metadata for all LiteLLM providers.

    Returns:
        List of provider metadata dictionaries
    """
    providers = get_litellm_providers()
    return [get_provider_info(p) for p in providers]


def get_providers_by_category() -> dict[str, list[dict[str, Any]]]:
    """
    Get providers grouped by category.

    Returns:
        Dictionary mapping category to list of provider info
    """
    all_providers = get_all_providers_info()

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


def get_openai_compatible_providers() -> list[dict[str, Any]]:
    """Get list of OpenAI-compatible providers."""
    return get_providers_by_category()["OPENAI_COMPATIBLE"]


def get_native_providers() -> list[dict[str, Any]]:
    """Get list of native/provider-specific providers."""
    return get_providers_by_category()["PROVIDER_SPECIFIC"]


def get_custom_providers() -> list[dict[str, Any]]:
    """Get list of custom/self-hosted providers."""
    return get_providers_by_category()["CUSTOM"]
