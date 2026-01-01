"""
Agent tool action and observation descriptions
"""

from typing import Any


def get_action_description(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Generate friendly description for tool action

    Args:
        tool_name: Name of the tool being used
        tool_input: Input parameters for the tool

        Returns:
        Human-friendly description in English
    """
    if tool_name == "knowledge_base_query":
        query = tool_input.get("query", "")
        top_k = tool_input.get("top_k", 5)
        return f"Querying knowledge base (Query: {query[:30]}{'...' if len(query) > 30 else ''}, Fetching {top_k} results)"

    # Generic description for unknown tools
    return f"Using tool: {tool_name}"


def get_observation_description(tool_name: str, observation: str) -> str:
    """
    Generate friendly description for tool observation

    Args:
        tool_name: Name of the tool that was executed
        observation: Raw observation result

    Returns:
        Human-friendly description in English
    """
    if tool_name == "knowledge_base_query":
        # Try to extract document count from observation
        if observation and len(observation) > 0:
            return "Found relevant information, organizing answer..."
        return "No relevant information found"

    # Generic description for unknown tools
    return f"Tool {tool_name} execution completed"


# Tool name mappings for display
TOOL_DISPLAY_NAMES = {
    "knowledge_base_query": "Knowledge Base Query",
}


def get_tool_display_name(tool_name: str) -> str:
    """Get friendly display name for tool"""
    return TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
