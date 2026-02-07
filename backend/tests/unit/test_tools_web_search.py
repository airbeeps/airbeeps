"""
Unit tests for WebSearchTool.

Tests for web search with mocked HTTP to avoid real API calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchProviders:
    """Tests for search provider classes."""

    @pytest.mark.asyncio
    async def test_brave_search_provider(self):
        """Should format Brave API results correctly."""
        from airbeeps.agents.tools.web_search import BraveSearchProvider

        provider = BraveSearchProvider(api_key="test-key")

        mock_response = {
            "web": {
                "results": [
                    {
                        "title": "Python Tutorial",
                        "url": "https://python.org",
                        "description": "Learn Python programming",
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value=MagicMock(
                    json=lambda: mock_response,
                    raise_for_status=lambda: None,
                )
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock()

            results = await provider.search("python", num_results=5)

        assert len(results) == 1
        assert results[0]["title"] == "Python Tutorial"
        assert results[0]["url"] == "https://python.org"

    @pytest.mark.asyncio
    async def test_tavily_search_provider(self):
        """Should format Tavily API results correctly."""
        from airbeeps.agents.tools.web_search import TavilySearchProvider

        provider = TavilySearchProvider(api_key="test-key")

        mock_response = {
            "results": [
                {
                    "title": "JavaScript Guide",
                    "url": "https://javascript.info",
                    "content": "Comprehensive JavaScript guide",
                }
            ]
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                return_value=MagicMock(
                    json=lambda: mock_response,
                    raise_for_status=lambda: None,
                )
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock()

            results = await provider.search("javascript", num_results=5)

        assert len(results) == 1
        assert results[0]["title"] == "JavaScript Guide"

    @pytest.mark.asyncio
    async def test_duckduckgo_provider(self):
        """Should format DuckDuckGo API results correctly."""
        from airbeeps.agents.tools.web_search import DuckDuckGoProvider

        provider = DuckDuckGoProvider()

        mock_response = {
            "Heading": "Python",
            "Abstract": "Python is a programming language",
            "AbstractURL": "https://en.wikipedia.org/wiki/Python",
            "RelatedTopics": [
                {
                    "FirstURL": "https://example.com/topic",
                    "Text": "Related topic text",
                }
            ],
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value=MagicMock(
                    json=lambda: mock_response,
                    raise_for_status=lambda: None,
                )
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock()

            results = await provider.search("python", num_results=5)

        assert len(results) >= 1
        assert results[0]["title"] == "Python"


class TestWebSearchTool:
    """Tests for WebSearchTool class."""

    @pytest.fixture
    def tool_with_brave(self):
        """Create tool with Brave API key."""
        from airbeeps.agents.tools.web_search import WebSearchTool
        from airbeeps.agents.tools.base import AgentToolConfig

        config = AgentToolConfig(
            name="web_search",
            parameters={"brave_api_key": "test-brave-key"},
        )
        return WebSearchTool(config=config)

    @pytest.fixture
    def tool_with_tavily(self):
        """Create tool with Tavily API key."""
        from airbeeps.agents.tools.web_search import WebSearchTool
        from airbeeps.agents.tools.base import AgentToolConfig

        config = AgentToolConfig(
            name="web_search",
            parameters={"tavily_api_key": "test-tavily-key"},
        )
        return WebSearchTool(config=config)

    @pytest.fixture
    def tool_no_keys(self):
        """Create tool without API keys."""
        from airbeeps.agents.tools.web_search import WebSearchTool

        return WebSearchTool()

    def test_tool_properties(self, tool_with_brave):
        """Should have correct tool properties."""
        from airbeeps.agents.tools.base import ToolSecurityLevel

        assert tool_with_brave.name == "web_search"
        assert tool_with_brave.security_level == ToolSecurityLevel.SAFE

    def test_get_input_schema(self, tool_with_brave):
        """Should return valid input schema."""
        schema = tool_with_brave.get_input_schema()

        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_provider_priority_brave(self, tool_with_brave):
        """Should prefer Brave when available."""
        from airbeeps.agents.tools.web_search import BraveSearchProvider

        provider = tool_with_brave._get_provider()

        assert isinstance(provider, BraveSearchProvider)

    def test_provider_priority_tavily(self, tool_with_tavily):
        """Should use Tavily when no Brave key."""
        from airbeeps.agents.tools.web_search import TavilySearchProvider

        provider = tool_with_tavily._get_provider()

        assert isinstance(provider, TavilySearchProvider)

    def test_provider_fallback_duckduckgo(self, tool_no_keys):
        """Should fallback to DuckDuckGo when no keys."""
        from airbeeps.agents.tools.web_search import DuckDuckGoProvider

        # Clear environment variables
        with patch.dict("os.environ", {}, clear=True):
            provider = tool_no_keys._get_provider()

            assert isinstance(provider, DuckDuckGoProvider)

    @pytest.mark.asyncio
    async def test_execute_success(self, tool_with_brave):
        """Should return formatted results."""
        mock_results = [
            {
                "title": "Result 1",
                "url": "https://example1.com",
                "snippet": "First result",
            },
            {
                "title": "Result 2",
                "url": "https://example2.com",
                "snippet": "Second result",
            },
        ]

        mock_provider = AsyncMock()
        mock_provider.search = AsyncMock(return_value=mock_results)
        tool_with_brave._provider = mock_provider

        result = await tool_with_brave.execute(query="test query", num_results=5)

        assert "Result 1" in result
        assert "Result 2" in result
        assert "https://example1.com" in result

    @pytest.mark.asyncio
    async def test_execute_no_results(self, tool_with_brave):
        """Should indicate when no results found."""
        mock_provider = AsyncMock()
        mock_provider.search = AsyncMock(return_value=[])
        tool_with_brave._provider = mock_provider

        result = await tool_with_brave.execute(query="obscure query")

        assert "No search results" in result

    @pytest.mark.asyncio
    async def test_execute_http_error(self, tool_with_brave):
        """Should handle HTTP errors gracefully."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_provider = AsyncMock()
        mock_provider.search = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Rate limited", request=None, response=mock_response
            )
        )
        tool_with_brave._provider = mock_provider

        result = await tool_with_brave.execute(query="test")

        assert "Error" in result
        assert "429" in result

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tool_with_brave):
        """Should handle timeout gracefully."""
        import httpx

        mock_provider = AsyncMock()
        mock_provider.search = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        tool_with_brave._provider = mock_provider

        result = await tool_with_brave.execute(query="test")

        assert "Error" in result
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_general_error(self, tool_with_brave):
        """Should handle general errors gracefully."""
        mock_provider = AsyncMock()
        mock_provider.search = AsyncMock(side_effect=Exception("Unknown error"))
        tool_with_brave._provider = mock_provider

        result = await tool_with_brave.execute(query="test")

        assert "Error" in result
