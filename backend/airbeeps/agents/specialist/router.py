"""
Agent Router for Multi-Agent System.

Routes user requests to the appropriate specialist agent based on
intent classification using keywords and LLM analysis.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .types import SpecialistType, classify_intent_keywords, get_specialist_config

logger = logging.getLogger(__name__)


# LLM prompt for intent classification
CLASSIFICATION_PROMPT = """Analyze the user's request and classify it into ONE of these categories:

RESEARCH - The request needs:
- Web searching for current information
- Looking up documentation or articles
- Finding facts or explanations
- Knowledge base queries

CODE - The request needs:
- Writing or executing code
- Programming tasks
- File operations
- Debugging or troubleshooting

DATA - The request needs:
- Analyzing spreadsheet/CSV data
- Statistical analysis
- Data aggregation or filtering
- Working with datasets

GENERAL - The request is:
- A simple question that doesn't need tools
- Conversational (greetings, thanks, etc.)
- Ambiguous or multi-part (needs clarification)

User request: {user_input}

Respond with ONLY one word: RESEARCH, CODE, DATA, or GENERAL"""


@dataclass
class RoutingDecision:
    """Result of routing decision"""

    specialist_type: SpecialistType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    method: str  # "keyword", "llm", "fallback"


class AgentRouter:
    """
    Routes tasks to appropriate specialist agents.

    Uses a two-stage approach:
    1. Fast keyword-based classification for common cases
    2. LLM-based classification for ambiguous cases
    """

    def __init__(
        self,
        llm: Any | None = None,
        use_llm_classification: bool = True,
        keyword_confidence_threshold: float = 0.7,
    ):
        """
        Initialize the router.

        Args:
            llm: LangChain-compatible LLM for classification
            use_llm_classification: Whether to use LLM for ambiguous cases
            keyword_confidence_threshold: Minimum confidence for keyword-only routing
        """
        self.llm = llm
        self.use_llm_classification = use_llm_classification
        self.keyword_confidence_threshold = keyword_confidence_threshold

    async def route(
        self,
        user_input: str,
        available_specialists: list[SpecialistType] | None = None,
        context: dict | None = None,
    ) -> RoutingDecision:
        """
        Route a user request to the appropriate specialist.

        Args:
            user_input: The user's request
            available_specialists: List of available specialist types (defaults to all)
            context: Optional context (conversation history, etc.)

        Returns:
            RoutingDecision with the selected specialist and reasoning
        """
        if available_specialists is None:
            available_specialists = list(SpecialistType)

        # Stage 1: Try keyword-based classification
        keyword_result = self._classify_by_keywords(user_input, available_specialists)

        if (
            keyword_result
            and keyword_result.confidence >= self.keyword_confidence_threshold
        ):
            logger.debug(
                f"Routed to {keyword_result.specialist_type.value} via keywords"
            )
            return keyword_result

        # Stage 2: Use LLM classification if enabled
        if self.use_llm_classification and self.llm:
            try:
                llm_result = await self._classify_by_llm(
                    user_input, available_specialists
                )
                if llm_result:
                    logger.debug(
                        f"Routed to {llm_result.specialist_type.value} via LLM"
                    )
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}")

        # Fallback: Use keyword result if available, otherwise GENERAL
        if keyword_result:
            keyword_result.reasoning += " (LLM unavailable, using keyword match)"
            return keyword_result

        return RoutingDecision(
            specialist_type=SpecialistType.GENERAL,
            confidence=0.3,
            reasoning="No clear specialist match, routing to general",
            method="fallback",
        )

    def _classify_by_keywords(
        self,
        user_input: str,
        available_specialists: list[SpecialistType],
    ) -> RoutingDecision | None:
        """Classify using keyword matching"""
        result = classify_intent_keywords(user_input)

        if result and result in available_specialists:
            config = get_specialist_config(result)
            matched_keywords = [
                kw for kw in config.priority_keywords if kw in user_input.lower()
            ]

            # Calculate confidence based on number of matches
            confidence = min(0.5 + len(matched_keywords) * 0.1, 0.9)

            return RoutingDecision(
                specialist_type=result,
                confidence=confidence,
                reasoning=f"Matched keywords: {', '.join(matched_keywords[:3])}",
                method="keyword",
            )

        return None

    async def _classify_by_llm(
        self,
        user_input: str,
        available_specialists: list[SpecialistType],
    ) -> RoutingDecision | None:
        """Classify using LLM"""
        if not self.llm:
            return None

        prompt = CLASSIFICATION_PROMPT.format(user_input=user_input[:500])

        try:
            response = await self.llm.ainvoke(prompt)
            content = (
                response.content if hasattr(response, "content") else str(response)
            )
            content = content.strip().upper()

            # Parse the response
            specialist_type = self._parse_classification(content)

            if specialist_type and specialist_type in available_specialists:
                return RoutingDecision(
                    specialist_type=specialist_type,
                    confidence=0.85,
                    reasoning=f"LLM classified as {specialist_type.value}",
                    method="llm",
                )

        except Exception as e:
            logger.error(f"LLM classification error: {e}")

        return None

    def _parse_classification(self, response: str) -> SpecialistType | None:
        """Parse LLM classification response"""
        response = response.strip().upper()

        # Direct match
        for spec_type in SpecialistType:
            if spec_type.value in response:
                return spec_type

        return None

    def parse_handoff_request(self, agent_response: str) -> SpecialistType | None:
        """
        Parse an agent's response to detect handoff requests.

        Agents can request handoffs by including specific markers:
        - NEED_RESEARCH -> SpecialistType.RESEARCH
        - NEED_CODE -> SpecialistType.CODE
        - NEED_DATA -> SpecialistType.DATA

        Returns:
            The requested specialist type, or None if no handoff requested
        """
        upper_response = agent_response.upper()

        if "NEED_RESEARCH" in upper_response:
            return SpecialistType.RESEARCH
        elif "NEED_CODE" in upper_response:
            return SpecialistType.CODE
        elif "NEED_DATA" in upper_response:
            return SpecialistType.DATA

        return None

    def get_available_specialists_for_assistant(
        self,
        assistant: Any,
    ) -> list[SpecialistType]:
        """
        Get the list of specialist types available for an assistant.

        Looks at the assistant's configuration to determine which
        specialist types are enabled.
        """
        available = []

        # Check assistant's specialist type
        if hasattr(assistant, "specialist_type") and assistant.specialist_type:
            try:
                spec_type = SpecialistType(assistant.specialist_type)
                available.append(spec_type)
            except ValueError:
                pass

        # If no specific type, include all that can collaborate
        if (
            not available
            and hasattr(assistant, "can_collaborate")
            and assistant.can_collaborate
        ):
            available = list(SpecialistType)

        # Fallback to GENERAL only
        if not available:
            available = [SpecialistType.GENERAL]

        return available
