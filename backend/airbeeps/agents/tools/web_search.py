"""
Web Search tool for agents.

Provides web search capabilities using various search APIs:
- Brave Search API
- Tavily API
- DuckDuckGo (fallback)
"""

import logging
from typing import Any

import httpx

from .base import AgentTool, AgentToolConfig, ToolSecurityLevel
from .registry import tool_registry

logger = logging.getLogger(__name__)


class SearchProvider:
    """Base class for search providers"""

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError


class BraveSearchProvider(SearchProvider):
    """Brave Search API provider"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.base_url,
                params={"q": query, "count": num_results},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.api_key,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("web", {}).get("results", [])[:num_results]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("description", ""),
                    }
                )

            return results


class TavilySearchProvider(SearchProvider):
    """Tavily Search API provider"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tavily.com/search"

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": num_results,
                    "include_answer": False,
                    "search_depth": "basic",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", [])[:num_results]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                    }
                )

            return results


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo instant answer API (limited, fallback only)"""

    def __init__(self):
        self.base_url = "https://api.duckduckgo.com/"

    async def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.base_url,
                params={"q": query, "format": "json", "no_html": 1},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            results = []

            # Abstract (main result)
            if data.get("Abstract"):
                results.append(
                    {
                        "title": data.get("Heading", query),
                        "url": data.get("AbstractURL", ""),
                        "snippet": data.get("Abstract", ""),
                    }
                )

            # Related topics
            for topic in data.get("RelatedTopics", [])[: num_results - len(results)]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append(
                        {
                            "title": topic.get("FirstURL", "")
                            .split("/")[-1]
                            .replace("_", " "),
                            "url": topic.get("FirstURL", ""),
                            "snippet": topic.get("Text", ""),
                        }
                    )

            return results


@tool_registry.register
class WebSearchTool(AgentTool):
    """
    Web search tool for agents.

    Searches the web for current information using various search APIs.
    """

    def __init__(self, config: AgentToolConfig | None = None):
        super().__init__(config)

        # Get API keys from config or environment
        self.brave_api_key = self.config.parameters.get("brave_api_key")
        self.tavily_api_key = self.config.parameters.get("tavily_api_key")

        # Initialize provider
        self._provider: SearchProvider | None = None

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information. "
            "Returns snippets with URLs. Use this to find up-to-date information "
            "that may not be in your training data."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    def _get_provider(self) -> SearchProvider:
        """Get the search provider based on available API keys"""
        if self._provider:
            return self._provider

        # Try Brave first
        if self.brave_api_key:
            self._provider = BraveSearchProvider(self.brave_api_key)
            logger.info("Using Brave Search API")
            return self._provider

        # Try Tavily
        if self.tavily_api_key:
            self._provider = TavilySearchProvider(self.tavily_api_key)
            logger.info("Using Tavily Search API")
            return self._provider

        # Check environment variables
        import os

        brave_key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if brave_key:
            self._provider = BraveSearchProvider(brave_key)
            logger.info("Using Brave Search API from environment")
            return self._provider

        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            self._provider = TavilySearchProvider(tavily_key)
            logger.info("Using Tavily Search API from environment")
            return self._provider

        # Fallback to DuckDuckGo
        self._provider = DuckDuckGoProvider()
        logger.warning("No search API key configured, falling back to DuckDuckGo")
        return self._provider

    async def execute(self, query: str, num_results: int = 5) -> str:
        """Execute web search"""
        try:
            provider = self._get_provider()
            results = await provider.search(query, num_results)

            if not results:
                return "No search results found."

            # Format results
            formatted = []
            for i, result in enumerate(results, 1):
                formatted.append(
                    f"[{i}] {result['title']}\n"
                    f"    URL: {result['url']}\n"
                    f"    {result['snippet']}"
                )

            return "Web search results:\n\n" + "\n\n".join(formatted)

        except httpx.HTTPStatusError as e:
            logger.error(f"Web search HTTP error: {e}")
            return f"Error: Search API returned status {e.response.status_code}"
        except httpx.TimeoutException:
            logger.error("Web search timeout")
            return "Error: Search request timed out"
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return f"Error performing web search: {e!s}"
