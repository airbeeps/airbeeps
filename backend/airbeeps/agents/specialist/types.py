"""
Specialist Agent Types and Configuration.

Defines the types of specialist agents and their default configurations.
"""

import enum
from dataclasses import dataclass, field


class SpecialistType(enum.Enum):
    """Types of specialist agents"""

    RESEARCH = "RESEARCH"  # Web search + RAG expert
    CODE = "CODE"  # Code execution + file operations
    DATA = "DATA"  # SQL queries + data analysis
    GENERAL = "GENERAL"  # General conversation, routing hub


@dataclass
class SpecialistConfig:
    """Configuration for a specialist agent"""

    type: SpecialistType
    tools: list[str] = field(default_factory=list)
    system_prompt_suffix: str = ""
    max_iterations: int = 5
    cost_limit_usd: float = 0.25
    can_handoff_to: list[SpecialistType] = field(default_factory=list)
    priority_keywords: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Get display name for the specialist type"""
        return f"{self.type.value.title()} Specialist"


# Default configurations for each specialist type
SPECIALIST_CONFIGS: dict[SpecialistType, SpecialistConfig] = {
    SpecialistType.RESEARCH: SpecialistConfig(
        type=SpecialistType.RESEARCH,
        tools=["web_search", "knowledge_base_query", "knowledge_base_search"],
        system_prompt_suffix="""You are a research specialist. Your expertise is in:
- Searching the web for current information
- Querying knowledge bases for relevant documents
- Synthesizing information from multiple sources
- Providing well-cited, factual answers

When you cannot find sufficient information, explain what you searched for and suggest
how to refine the search. Always cite your sources.""",
        max_iterations=5,
        cost_limit_usd=0.25,
        can_handoff_to=[
            SpecialistType.CODE,
            SpecialistType.DATA,
            SpecialistType.GENERAL,
        ],
        priority_keywords=[
            "search",
            "find",
            "look up",
            "research",
            "information about",
            "what is",
            "who is",
            "when did",
            "where is",
            "how does",
            "explain",
            "learn about",
            "documentation",
            "article",
            "news",
        ],
    ),
    SpecialistType.CODE: SpecialistConfig(
        type=SpecialistType.CODE,
        tools=["execute_python", "file_read", "file_write", "file_list"],
        system_prompt_suffix="""You are a code specialist. Your expertise is in:
- Writing and executing Python code safely
- Reading and writing files
- Debugging and troubleshooting code issues
- Providing code explanations and suggestions

Always explain your code clearly and handle errors gracefully.
Use the sandbox environment for code execution - it has limited imports and resources.
Available imports: math, json, datetime, pandas, numpy, re, collections.

If a task requires capabilities outside your tools (like database queries),
request handoff to the appropriate specialist by including "NEED_DATA" or "NEED_RESEARCH" in your response.""",
        max_iterations=3,
        cost_limit_usd=0.15,
        can_handoff_to=[
            SpecialistType.DATA,
            SpecialistType.RESEARCH,
            SpecialistType.GENERAL,
        ],
        priority_keywords=[
            "code",
            "python",
            "programming",
            "script",
            "function",
            "execute",
            "run",
            "debug",
            "error",
            "file",
            "write code",
            "algorithm",
            "implement",
            "create a program",
        ],
    ),
    SpecialistType.DATA: SpecialistConfig(
        type=SpecialistType.DATA,
        tools=["analyze_data", "list_tabular_documents", "knowledge_base_query"],
        system_prompt_suffix="""You are a data analysis specialist. Your expertise is in:
- Analyzing CSV and Excel data
- Performing statistical analysis
- Aggregating and filtering data
- Answering questions about datasets

First list available documents, then analyze the relevant data.
Use clear explanations of your analysis process and findings.
Present data in readable formats (tables, summaries).

If a task requires code execution beyond data analysis, request handoff to the
CODE specialist by including "NEED_CODE" in your response.""",
        max_iterations=4,
        cost_limit_usd=0.20,
        can_handoff_to=[
            SpecialistType.CODE,
            SpecialistType.RESEARCH,
            SpecialistType.GENERAL,
        ],
        priority_keywords=[
            "data",
            "analyze",
            "statistics",
            "csv",
            "excel",
            "spreadsheet",
            "aggregate",
            "filter",
            "sum",
            "average",
            "count",
            "group by",
            "chart",
            "graph",
            "table",
            "dataset",
        ],
    ),
    SpecialistType.GENERAL: SpecialistConfig(
        type=SpecialistType.GENERAL,
        tools=[],  # General uses assistant's default tools
        system_prompt_suffix="""You are a general-purpose assistant. You can:
- Answer questions directly when no specialized tools are needed
- Route complex requests to specialist agents
- Provide conversational assistance

If a task requires specialized capabilities, request handoff:
- For web/document research: include "NEED_RESEARCH" in your response
- For code execution: include "NEED_CODE" in your response
- For data analysis: include "NEED_DATA" in your response""",
        max_iterations=10,
        cost_limit_usd=0.50,
        can_handoff_to=[
            SpecialistType.RESEARCH,
            SpecialistType.CODE,
            SpecialistType.DATA,
        ],
        priority_keywords=[],  # Fallback, no priority keywords
    ),
}


def get_specialist_config(specialist_type: SpecialistType) -> SpecialistConfig:
    """Get the default configuration for a specialist type"""
    return SPECIALIST_CONFIGS.get(
        specialist_type, SPECIALIST_CONFIGS[SpecialistType.GENERAL]
    )


def get_specialist_tools(specialist_type: SpecialistType) -> list[str]:
    """Get the tools available to a specialist type"""
    config = get_specialist_config(specialist_type)
    return config.tools


def get_specialist_prompt_suffix(specialist_type: SpecialistType) -> str:
    """Get the system prompt suffix for a specialist type"""
    config = get_specialist_config(specialist_type)
    return config.system_prompt_suffix


def classify_intent_keywords(user_input: str) -> SpecialistType | None:
    """
    Classify intent based on keywords in user input.

    This is a fast, heuristic-based classification that can be used
    before LLM-based classification for common cases.

    Returns:
        SpecialistType if a clear match is found, None otherwise
    """
    lower_input = user_input.lower()

    # Score each specialist based on keyword matches
    scores: dict[SpecialistType, int] = {
        SpecialistType.RESEARCH: 0,
        SpecialistType.CODE: 0,
        SpecialistType.DATA: 0,
    }

    for spec_type, config in SPECIALIST_CONFIGS.items():
        if spec_type == SpecialistType.GENERAL:
            continue

        for keyword in config.priority_keywords:
            if keyword in lower_input:
                scores[spec_type] += 1

    # Find the highest score
    max_score = max(scores.values())
    if max_score == 0:
        return None

    # Return the specialist with the highest score
    for spec_type, score in scores.items():
        if score == max_score:
            return spec_type

    return None
