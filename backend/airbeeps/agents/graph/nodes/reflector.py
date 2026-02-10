"""
Reflector Node for LangGraph.

Responsible for:
- Evaluating tool execution results
- Deciding if more information is needed
- Quality scoring
- Self-critique and retry logic
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

REFLECTION_PROMPT = """You are evaluating the progress of a task.

Original request: {user_input}

Plan: {plan}

Tool results so far:
{tool_results}

Evaluate:
1. Was the tool output useful? (1-10)
2. Do we have enough information to answer? (yes/no)
3. Should we try a different approach? (yes/no)
4. What's missing, if anything?

Respond with JSON:
{{
    "quality_score": 7,
    "has_enough_info": true/false,
    "needs_different_approach": true/false,
    "missing_info": "Description of what's missing, if any",
    "next_tool_calls": [
        {{"tool": "tool_name", "input": {{"param": "value"}}}}
    ],
    "reasoning": "Your evaluation"
}}

If we have enough information, set has_enough_info to true and leave next_tool_calls empty.
"""


async def reflector_node(
    state: dict[str, Any],
    llm: Any = None,
    quality_threshold: float = 7.0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Reflect on tool execution results and decide next steps.

    This node:
    1. Evaluates quality of tool results
    2. Decides if more tools needed
    3. Routes to executor for retry or responder for final answer

    Args:
        state: Current agent state
        llm: Language model for reflection
        quality_threshold: Minimum quality score (0-10)
        max_retries: Maximum retry attempts per task

    Returns:
        Updated state with reflection and routing decision
    """
    if not llm:
        # No LLM for reflection - proceed to response
        state["next_action"] = "respond"
        return state

    user_input = state.get("user_input", "")
    plan = state.get("plan", "")
    tools_used = state.get("tools_used", [])
    reflections = state.get("reflections", [])

    # Format tool results
    tool_results_str = _format_tool_results(tools_used)

    # Build reflection prompt
    reflection_prompt = REFLECTION_PROMPT.format(
        user_input=user_input,
        plan=plan,
        tool_results=tool_results_str,
    )

    try:
        # Call LLM for reflection
        response = await llm.ainvoke([{"role": "system", "content": reflection_prompt}])

        # Extract content
        if hasattr(response, "content"):
            content = response.content
        elif hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content
        else:
            content = str(response)

        # Parse reflection response
        reflection_data = _parse_reflection_response(content)

        # Update state
        quality_score = reflection_data.get("quality_score", 5.0)
        state["quality_score"] = quality_score

        reflection_text = reflection_data.get("reasoning", content)
        reflections.append(reflection_text)
        state["reflections"] = reflections

        # Track token usage
        if hasattr(response, "usage") and response.usage:
            current_usage = state.get("token_usage", {})
            current_usage["reflection"] = current_usage.get("reflection", 0) + getattr(
                response.usage, "total_tokens", 0
            )
            state["token_usage"] = current_usage

        # Decide next action
        has_enough_info = reflection_data.get("has_enough_info", True)
        needs_different_approach = reflection_data.get(
            "needs_different_approach", False
        )
        next_tool_calls = reflection_data.get("next_tool_calls", [])

        # Check retry limit
        current_retries = len([r for r in reflections if "retry" in r.lower()])

        if has_enough_info and quality_score >= quality_threshold:
            # Good quality, proceed to response
            state["next_action"] = "respond"
            logger.info(
                f"Reflection: Quality {quality_score}/10, proceeding to response"
            )

        elif next_tool_calls and current_retries < max_retries:
            # Need more tools
            state["pending_tool_calls"] = next_tool_calls
            state["next_action"] = "execute"
            logger.info(
                f"Reflection: Quality {quality_score}/10, "
                f"scheduling {len(next_tool_calls)} more tool calls"
            )

        elif needs_different_approach and current_retries < max_retries:
            # Try different approach - go back to planner
            state["next_action"] = "plan"
            reflections.append(
                f"[Retry {current_retries + 1}]: Trying different approach"
            )
            state["reflections"] = reflections
            logger.info(
                f"Reflection: Trying different approach (retry {current_retries + 1})"
            )

        else:
            # Give up and respond with best effort
            state["next_action"] = "respond"
            logger.info(
                f"Reflection: Quality {quality_score}/10, "
                f"proceeding to response (max retries or no better option)"
            )

        # Add reflection to messages
        messages = state.get("messages", [])
        messages.append(
            {"role": "assistant", "content": f"[Reflection]: {reflection_text}"}
        )
        state["messages"] = messages

    except Exception as e:
        logger.error(f"Reflection failed: {e}")
        state["next_action"] = "respond"

    return state


def _format_tool_results(tools_used: list[dict]) -> str:
    """Format tool results for the reflection prompt"""
    if not tools_used:
        return "No tools used yet."

    parts = []
    for i, tool in enumerate(tools_used, 1):
        tool_name = tool.get("tool_name", "unknown")
        result = tool.get("result", "")
        success = tool.get("success", True)
        duration = tool.get("duration_ms", 0)

        status = "✓" if success else "✗"
        parts.append(f"{i}. [{status}] {tool_name} ({duration}ms):\n   {result[:500]}")

    return "\n\n".join(parts)


def _parse_reflection_response(content: str) -> dict[str, Any]:
    """Parse the reflection response from LLM"""
    # Try to extract JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try markdown code block
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            try:
                return json.loads(content[start:end].strip())
            except json.JSONDecodeError:
                pass

    # Try to find JSON object
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

    # Default: assume we have enough info
    return {
        "quality_score": 5.0,
        "has_enough_info": True,
        "needs_different_approach": False,
        "missing_info": "",
        "next_tool_calls": [],
        "reasoning": content,
    }


def should_continue_reflecting(state: dict[str, Any]) -> str:
    """
    Routing function: decide next step after reflection.
    """
    next_action = state.get("next_action", "respond")

    if next_action == "execute" and state.get("pending_tool_calls"):
        return "execute"
    if next_action == "plan":
        return "plan"
    return "respond"
