from airbeeps.ai_models import litellm_providers


def test_provider_info_fallback_for_unknown_provider():
    info = litellm_providers.get_provider_info("unknown_provider", allow_external=False)
    assert info["id"] == "unknown_provider"
    assert info["category"] == "PROVIDER_SPECIFIC"
    assert info["docs_url"].endswith("/unknown_provider")


def test_provider_overrides_are_applied():
    info = litellm_providers.get_provider_info("openai", allow_external=False)
    assert info["display_name"] == "OpenAI"
    assert info["default_base_url"] == "https://api.openai.com/v1"


def test_provider_list_uses_overrides_when_external_disabled():
    providers = litellm_providers.get_litellm_providers(allow_external=False)
    assert "openai" in providers
