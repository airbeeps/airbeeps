"""
Test mode guard tests.

These tests verify that in test mode (AIRBEEPS_TEST_MODE=1):
1. The FakeLiteLLMClient is used instead of the real LiteLLM client
2. Real litellm.acompletion is never called
3. Chat requests succeed with deterministic fake responses
"""

from unittest.mock import patch

import pytest


class TestLLMTestMode:
    """Tests to verify LLM test mode behavior."""

    def test_test_mode_is_enabled(self, setup_test_environment):
        """Verify that test mode is enabled in the test environment."""
        from airbeeps.config import settings

        assert settings.TEST_MODE is True, (
            "TEST_MODE should be True in test environment"
        )

    def test_create_chat_model_returns_fake_client(self, setup_test_environment):
        """Verify that create_chat_model returns FakeLiteLLMClient in test mode."""
        from airbeeps.ai_models.client_factory import (
            FakeLiteLLMClient,
            create_chat_model,
        )

        # Create a mock provider
        class MockProvider:
            interface_type = "OPENAI"
            api_key = "test-key"
            api_base_url = "https://api.test.com"
            litellm_provider = None

        provider = MockProvider()

        client = create_chat_model(
            provider=provider,
            model_name="test-model",
            temperature=0.7,
        )

        assert isinstance(client, FakeLiteLLMClient), (
            f"Expected FakeLiteLLMClient but got {type(client)}"
        )

    @pytest.mark.asyncio
    async def test_fake_client_returns_deterministic_response(
        self, setup_test_environment
    ):
        """Verify that FakeLiteLLMClient returns deterministic responses."""
        from airbeeps.ai_models.client_factory import FakeLiteLLMClient

        client = FakeLiteLLMClient(model="test-model")

        messages = [{"role": "user", "content": "Hello, world!"}]

        response = await client.ainvoke(messages)

        # Verify response structure
        assert hasattr(response, "choices"), "Response should have choices"
        assert len(response.choices) > 0, "Response should have at least one choice"
        assert hasattr(response.choices[0], "message"), "Choice should have message"
        assert hasattr(response.choices[0].message, "content"), (
            "Message should have content"
        )

        # Verify deterministic content
        content = response.choices[0].message.content
        assert "TEST_MODE_RESPONSE:" in content, (
            f"Response should contain test mode prefix. Got: {content}"
        )
        assert "Hello, world!" in content, (
            f"Response should echo user message. Got: {content}"
        )

        # Verify usage
        assert hasattr(response, "usage"), "Response should have usage"
        assert response.usage.total_tokens > 0, "Total tokens should be positive"

    @pytest.mark.asyncio
    async def test_fake_client_streaming(self, setup_test_environment):
        """Verify that FakeLiteLLMClient streaming works correctly."""
        from airbeeps.ai_models.client_factory import FakeLiteLLMClient

        client = FakeLiteLLMClient(model="test-model")

        messages = [{"role": "user", "content": "Test streaming"}]

        chunks = []
        async for chunk in client.astream(messages):
            chunks.append(chunk)

        assert len(chunks) > 0, "Should receive streaming chunks"

        # Verify last chunk has finish_reason
        last_chunk = chunks[-1]
        assert hasattr(last_chunk, "choices"), "Chunk should have choices"
        assert last_chunk.choices[0].finish_reason == "stop", (
            "Last chunk should have finish_reason='stop'"
        )

        # Verify usage in last chunk
        assert last_chunk.usage is not None, "Last chunk should have usage"
        assert last_chunk.usage.total_tokens > 0, "Total tokens should be positive"

    @pytest.mark.asyncio
    async def test_real_litellm_is_not_called(self, setup_test_environment):
        """
        Verify that real litellm.acompletion is NEVER called in test mode.

        This is the critical guard test that ensures tests don't accidentally
        make real API calls even if API keys are present.
        """
        # Patch litellm.acompletion to raise an error if called
        with patch("litellm.acompletion") as mock_acompletion:
            mock_acompletion.side_effect = RuntimeError(
                "REAL LITELLM WAS CALLED! This should never happen in test mode."
            )

            # Import after patching
            from airbeeps.ai_models.client_factory import create_chat_model

            class MockProvider:
                interface_type = "OPENAI"
                api_key = "test-key"
                api_base_url = "https://api.test.com"
                litellm_provider = None

            provider = MockProvider()

            # Create client (should be FakeLiteLLMClient)
            client = create_chat_model(
                provider=provider,
                model_name="test-model",
            )

            messages = [{"role": "user", "content": "Test message"}]

            # This should succeed because FakeLiteLLMClient doesn't call litellm
            response = await client.ainvoke(messages)

            # Verify the response is valid
            assert response is not None
            assert "TEST_MODE_RESPONSE:" in response.choices[0].message.content

            # Verify litellm was NOT called
            mock_acompletion.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_endpoint_uses_fake_client(self, fresh_client):
        """
        Verify that the actual chat endpoint uses FakeLiteLLMClient in test mode.

        This test patches litellm.acompletion to raise and then exercises
        the full chat flow through the API to prove the fake client is used.
        """
        from tests.helpers import (
            create_assistant,
            create_conversation,
            create_model,
            create_provider,
            login_and_get_cookies,
            post_chat_and_collect_sse_events,
            register_user,
        )
        from tests.helpers.api import get_final_content_from_events

        client = fresh_client

        # Patch litellm.acompletion to raise if called
        with patch("litellm.acompletion") as mock_acompletion:
            mock_acompletion.side_effect = RuntimeError(
                "REAL LITELLM WAS CALLED VIA CHAT ENDPOINT!"
            )

            # Set up: register, login, create provider/model/assistant
            await register_user(client, email="guard@test.com", password="Password123!")
            cookies = await login_and_get_cookies(
                client, email="guard@test.com", password="Password123!"
            )

            provider_resp = await create_provider(client, cookies)
            assert provider_resp.status_code == 201
            provider_id = provider_resp.json()["id"]

            model_resp = await create_model(client, cookies, provider_id=provider_id)
            assert model_resp.status_code == 201
            model_id = model_resp.json()["id"]

            assistant_resp = await create_assistant(client, cookies, model_id=model_id)
            assert assistant_resp.status_code == 201
            assistant_id = assistant_resp.json()["id"]

            conv_resp = await create_conversation(
                client, cookies, assistant_id=assistant_id
            )
            assert conv_resp.status_code == 200
            conversation_id = conv_resp.json()["id"]

            # This should work because FakeLiteLLMClient is used, not real litellm
            events = await post_chat_and_collect_sse_events(
                client,
                cookies,
                conversation_id=conversation_id,
                content="Hello guard test!",
            )

            # Verify we got a fake response
            final_content = get_final_content_from_events(events)
            assert "TEST_MODE_RESPONSE:" in final_content

            # Verify litellm was never called
            mock_acompletion.assert_not_called()

    def test_fake_embeddings_in_test_mode(self, setup_test_environment):
        """Verify that FakeEmbeddings is used in test mode."""
        from airbeeps.rag.embeddings import FakeEmbeddings, _is_test_mode

        assert _is_test_mode() is True, "Should be in test mode"

        # Create fake embeddings
        embeddings = FakeEmbeddings(model_name="test-embedding")

        # Test embed_query
        vector = embeddings.embed_query("test query")
        assert len(vector) == FakeEmbeddings.EMBEDDING_DIM, (
            f"Vector should have {FakeEmbeddings.EMBEDDING_DIM} dimensions"
        )
        assert all(isinstance(v, float) for v in vector), (
            "All vector elements should be floats"
        )

        # Test determinism - same input should give same output
        vector2 = embeddings.embed_query("test query")
        assert vector == vector2, "Same input should produce same vector"

        # Test embed_documents
        docs = ["doc 1", "doc 2", "doc 3"]
        vectors = embeddings.embed_documents(docs)
        assert len(vectors) == 3, "Should return one vector per document"
        assert all(len(v) == FakeEmbeddings.EMBEDDING_DIM for v in vectors), (
            "All vectors should have correct dimension"
        )
