"""
Unit tests for Specialist Router and Types.

Tests for AgentRouter, intent classification, and specialist configuration.
All tests use mocked LLM to ensure no real API calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestSpecialistType:
    """Tests for SpecialistType enum."""

    def test_specialist_types(self):
        """Should have expected specialist types."""
        from airbeeps.agents.specialist.types import SpecialistType

        assert SpecialistType.RESEARCH.value == "RESEARCH"
        assert SpecialistType.CODE.value == "CODE"
        assert SpecialistType.DATA.value == "DATA"
        assert SpecialistType.GENERAL.value == "GENERAL"


class TestSpecialistConfig:
    """Tests for SpecialistConfig."""

    def test_research_config(self):
        """Should have appropriate research config."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            get_specialist_config,
        )

        config = get_specialist_config(SpecialistType.RESEARCH)

        assert config.type == SpecialistType.RESEARCH
        assert "web_search" in config.tools
        assert "search" in config.priority_keywords

    def test_code_config(self):
        """Should have appropriate code config."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            get_specialist_config,
        )

        config = get_specialist_config(SpecialistType.CODE)

        assert "execute_python" in config.tools
        assert "code" in config.priority_keywords
        assert config.max_iterations == 3

    def test_data_config(self):
        """Should have appropriate data config."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            get_specialist_config,
        )

        config = get_specialist_config(SpecialistType.DATA)

        assert "analyze_data" in config.tools
        assert "csv" in config.priority_keywords

    def test_general_config(self):
        """Should have appropriate general config."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            get_specialist_config,
        )

        config = get_specialist_config(SpecialistType.GENERAL)

        assert config.tools == []  # General uses assistant's default tools
        assert config.max_iterations == 10

    def test_config_name_property(self):
        """Should return formatted name."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            get_specialist_config,
        )

        config = get_specialist_config(SpecialistType.RESEARCH)
        assert "Research" in config.name


class TestClassifyIntentKeywords:
    """Tests for keyword-based intent classification."""

    def test_classify_research_intent(self):
        """Should classify research requests."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            classify_intent_keywords,
        )

        result = classify_intent_keywords("search for information about Python")
        assert result == SpecialistType.RESEARCH

        result = classify_intent_keywords("look up the documentation for Flask")
        assert result == SpecialistType.RESEARCH

    def test_classify_code_intent(self):
        """Should classify code requests."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            classify_intent_keywords,
        )

        result = classify_intent_keywords("write python code to sort a list")
        assert result == SpecialistType.CODE

        result = classify_intent_keywords("execute this script")
        assert result == SpecialistType.CODE

    def test_classify_data_intent(self):
        """Should classify data requests."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            classify_intent_keywords,
        )

        result = classify_intent_keywords("analyze the sales data from the csv")
        assert result == SpecialistType.DATA

        result = classify_intent_keywords("show the average values in the spreadsheet")
        assert result == SpecialistType.DATA

    def test_classify_ambiguous_returns_none(self):
        """Should return None for ambiguous input."""
        from airbeeps.agents.specialist.types import classify_intent_keywords

        result = classify_intent_keywords("hello, how are you?")
        assert result is None

    def test_classify_mixed_keywords(self):
        """Should pick highest scoring specialist."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            classify_intent_keywords,
        )

        # More code keywords than research
        result = classify_intent_keywords("write python code and debug the error")
        assert result == SpecialistType.CODE


class TestGetSpecialistTools:
    """Tests for get_specialist_tools helper."""

    def test_get_tools(self):
        """Should return tools for specialist type."""
        from airbeeps.agents.specialist.types import (
            SpecialistType,
            get_specialist_tools,
        )

        tools = get_specialist_tools(SpecialistType.RESEARCH)
        assert isinstance(tools, list)
        assert len(tools) > 0


class TestAgentRouter:
    """Tests for AgentRouter class."""

    @pytest.fixture
    def router_no_llm(self):
        """Create router without LLM."""
        from airbeeps.agents.specialist.router import AgentRouter

        return AgentRouter(llm=None, use_llm_classification=False)

    @pytest.fixture
    def router_with_llm(self):
        """Create router with mocked LLM."""
        from airbeeps.agents.specialist.router import AgentRouter

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="RESEARCH"))
        return AgentRouter(llm=mock_llm, use_llm_classification=True)

    @pytest.mark.asyncio
    async def test_route_by_keywords(self, router_no_llm):
        """Should route using keywords."""
        from airbeeps.agents.specialist.types import SpecialistType

        result = await router_no_llm.route("search for Python tutorials")

        assert result.specialist_type == SpecialistType.RESEARCH
        assert result.method == "keyword"

    @pytest.mark.asyncio
    async def test_route_by_keywords_code(self, router_no_llm):
        """Should route code requests to CODE specialist."""
        from airbeeps.agents.specialist.types import SpecialistType

        result = await router_no_llm.route("write python code for sorting")

        assert result.specialist_type == SpecialistType.CODE

    @pytest.mark.asyncio
    async def test_route_fallback_to_general(self, router_no_llm):
        """Should fallback to GENERAL for ambiguous requests."""
        from airbeeps.agents.specialist.types import SpecialistType

        result = await router_no_llm.route("hello there!")

        assert result.specialist_type == SpecialistType.GENERAL
        assert result.method == "fallback"

    @pytest.mark.asyncio
    async def test_route_with_llm(self, router_with_llm):
        """Should use LLM for classification when available."""
        from airbeeps.agents.specialist.types import SpecialistType

        result = await router_with_llm.route("tell me about quantum computing")

        # LLM mock returns RESEARCH
        assert result.specialist_type == SpecialistType.RESEARCH
        assert result.method == "llm"

    @pytest.mark.asyncio
    async def test_route_respects_available_specialists(self, router_no_llm):
        """Should only route to available specialists."""
        from airbeeps.agents.specialist.types import SpecialistType

        result = await router_no_llm.route(
            "analyze data in the csv",
            available_specialists=[SpecialistType.GENERAL, SpecialistType.CODE],
        )

        # DATA is not available, should fallback
        assert result.specialist_type in [SpecialistType.GENERAL, SpecialistType.CODE]

    @pytest.mark.asyncio
    async def test_route_llm_failure_fallback(self):
        """Should fallback to keywords when LLM fails."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

        router = AgentRouter(llm=mock_llm, use_llm_classification=True)

        result = await router.route("search for information")

        assert result.specialist_type == SpecialistType.RESEARCH
        assert result.method == "keyword"

    def test_parse_classification_research(self):
        """Should parse RESEARCH classification."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        result = router._parse_classification("RESEARCH")
        assert result == SpecialistType.RESEARCH

    def test_parse_classification_with_extra_text(self):
        """Should parse classification from response with extra text."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        result = router._parse_classification("Based on the request, I would say CODE")
        assert result == SpecialistType.CODE

    def test_parse_classification_unknown(self):
        """Should return None for unknown classification."""
        from airbeeps.agents.specialist.router import AgentRouter

        router = AgentRouter()

        result = router._parse_classification("UNKNOWN_TYPE")
        assert result is None


class TestHandoffParsing:
    """Tests for handoff request parsing."""

    def test_parse_handoff_research(self):
        """Should detect NEED_RESEARCH handoff."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        result = router.parse_handoff_request(
            "I need to look this up. NEED_RESEARCH for current data."
        )

        assert result == SpecialistType.RESEARCH

    def test_parse_handoff_code(self):
        """Should detect NEED_CODE handoff."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        result = router.parse_handoff_request(
            "This requires programming. NEED_CODE to implement."
        )

        assert result == SpecialistType.CODE

    def test_parse_handoff_data(self):
        """Should detect NEED_DATA handoff."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        result = router.parse_handoff_request(
            "I should analyze this. NEED_DATA for the spreadsheet."
        )

        assert result == SpecialistType.DATA

    def test_parse_handoff_none(self):
        """Should return None when no handoff requested."""
        from airbeeps.agents.specialist.router import AgentRouter

        router = AgentRouter()

        result = router.parse_handoff_request("Here is my response without handoff.")

        assert result is None


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_routing_decision_fields(self):
        """Should have expected fields."""
        from airbeeps.agents.specialist.router import RoutingDecision
        from airbeeps.agents.specialist.types import SpecialistType

        decision = RoutingDecision(
            specialist_type=SpecialistType.CODE,
            confidence=0.9,
            reasoning="Strong keyword match",
            method="keyword",
        )

        assert decision.specialist_type == SpecialistType.CODE
        assert decision.confidence == 0.9
        assert decision.method == "keyword"


class TestGetAvailableSpecialists:
    """Tests for get_available_specialists_for_assistant."""

    def test_with_specialist_type(self):
        """Should return assistant's specialist type."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        assistant = MagicMock()
        assistant.specialist_type = "RESEARCH"
        assistant.can_collaborate = False

        result = router.get_available_specialists_for_assistant(assistant)

        assert SpecialistType.RESEARCH in result

    def test_with_collaboration(self):
        """Should return all types when can_collaborate."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        assistant = MagicMock()
        assistant.specialist_type = None
        assistant.can_collaborate = True

        result = router.get_available_specialists_for_assistant(assistant)

        assert len(result) == len(list(SpecialistType))

    def test_fallback_to_general(self):
        """Should fallback to GENERAL only."""
        from airbeeps.agents.specialist.router import AgentRouter
        from airbeeps.agents.specialist.types import SpecialistType

        router = AgentRouter()

        assistant = MagicMock()
        assistant.specialist_type = None
        assistant.can_collaborate = False

        result = router.get_available_specialists_for_assistant(assistant)

        assert result == [SpecialistType.GENERAL]
