import pytest


@pytest.mark.asyncio
async def test_hf_hub_search_formats_results(client, monkeypatch):
    from airbeeps.ai_models.api.v1 import admin_router

    admin_router._HF_EMBEDDING_SEARCH_CACHE.clear()

    class FakeModel:
        def __init__(
            self,
            model_id: str,
            pipeline_tag: str | None = None,
            library_name: str | None = None,
            downloads: int | None = None,
            likes: int | None = None,
        ):
            self.modelId = model_id
            self.pipeline_tag = pipeline_tag
            self.library_name = library_name
            self.downloads = downloads
            self.likes = likes

    class FakeApi:
        def list_models(self, **_kwargs):
            return [
                FakeModel(
                    "BAAI/bge-small-en-v1.5",
                    pipeline_tag="feature-extraction",
                    library_name="sentence-transformers",
                    downloads=123,
                    likes=10,
                ),
                FakeModel(
                    "openai/gpt-4",
                    pipeline_tag="text-generation",
                    library_name=None,
                    downloads=999,
                    likes=99,
                ),
            ]

    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "HfApi", lambda: FakeApi())
    monkeypatch.setattr(
        admin_router,
        "list_hf_hub_cached_model_repo_ids",
        lambda: ["BAAI/bge-small-en-v1.5"],
    )

    response = await client.get(
        "/v1/admin/model-assets/huggingface/embeddings/search?q=bge"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "bge"
    assert data["external_enabled"] is True
    assert len(data["results"]) == 1

    result = data["results"][0]
    assert result["repo_id"] == "BAAI/bge-small-en-v1.5"
    assert result["is_installed"] is True
