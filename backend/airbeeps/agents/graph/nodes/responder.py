"""
Responder Node for LangGraph.

Responsible for:
- Generating final response
- Synthesizing tool results
- Formatting output
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

RESPONSE_PROMPT = """Based on the following information, provide a helpful and accurate response to the user.

Original request: {user_input}

{context_section}

Provide a clear, well-structured response. If you used information from tools, cite the sources appropriately.
"""


async def responder_node(
    state: dict[str, Any],
    llm: Any = None,
) -> dict[str, Any]:
    """
    Generate final response.

    This node:
    1. Synthesizes all gathered information
    2. Generates coherent response
    3. Marks state as complete

    Args:
        state: Current agent state
        llm: Language model for response generation

    Returns:
        Updated state with final answer
    """
    user_input = state.get("user_input", "")
    final_answer = state.get("final_answer")
    abort_reason = state.get("abort_reason")

    # If we already have a final answer (from planning or abort), use it
    if final_answer:
        # If aborted, append context
        if abort_reason:
            tools_used = state.get("tools_used", [])
            if tools_used:
                final_answer += "\n\n" + _format_partial_results(tools_used)

        state["final_answer"] = final_answer
        state["next_action"] = "done"
        return state

    # Generate response from LLM
    if not llm:
        # No LLM - construct response from tool results
        tools_used = state.get("tools_used", [])
        if tools_used:
            state["final_answer"] = _format_tool_response(user_input, tools_used)
        else:
            state["final_answer"] = (
                "I apologize, but I was unable to complete the request."
            )

        state["next_action"] = "done"
        return state

    # Build context for response
    context_parts = []

    # Add plan if available
    plan = state.get("plan")
    if plan:
        context_parts.append(f"Approach taken: {plan}")

    # Add tool results
    tools_used = state.get("tools_used", [])
    if tools_used:
        context_parts.append("Information gathered:")
        for tool in tools_used:
            if tool.get("success"):
                context_parts.append(
                    f"- From {tool['tool_name']}: {tool['result'][:1000]}"
                )

    # Add reflections
    reflections = state.get("reflections", [])
    if reflections:
        context_parts.append(f"Analysis: {reflections[-1]}")

    # Add memory context
    memory_context = state.get("memory_context", {})
    if memory_context:
        context_parts.append(f"Relevant context: {memory_context}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context."
    )

    # Build prompt
    response_prompt = RESPONSE_PROMPT.format(
        user_input=user_input,
        context_section=context_section,
    )

    try:
        # Generate response
        response = await llm.ainvoke(
            [
                {"role": "system", "content": response_prompt},
                {"role": "user", "content": user_input},
            ]
        )

        # Extract content
        if hasattr(response, "content"):
            content = response.content
        elif hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content
        else:
            content = str(response)

        state["final_answer"] = content

        # Track token usage
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            current_usage = state.get("token_usage", {})
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or (
                input_tokens + output_tokens
            )

            current_usage["response_input"] = input_tokens
            current_usage["response_output"] = output_tokens
            current_usage["response"] = total_tokens
            state["token_usage"] = current_usage

            # Use model-aware cost estimation
            try:
                from ..cost_estimator import estimate_cost

                model_name = state.get("model_name", "default")
                response_cost = estimate_cost(input_tokens, output_tokens, model_name)
                state["cost_spent_usd"] = state.get("cost_spent_usd", 0) + response_cost
            except ImportError:
                # Fallback to rough estimate
                state["cost_spent_usd"] = state.get("cost_spent_usd", 0) + (
                    total_tokens / 1000 * 0.01
                )

        logger.info(f"Response generated, {total_tokens} tokens used")

    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        state["final_answer"] = _format_fallback_response(user_input, tools_used)

    state["next_action"] = "done"
    return state


def _format_tool_response(user_input: str, tools_used: list[dict]) -> str:
    """Format a response from tool results without LLM"""
    parts = ["Here's what I found for your request:\n"]

    for tool in tools_used:
        if tool.get("success"):
            parts.append(f"**{tool['tool_name']}:**\n{tool['result']}\n")

    if not any(t.get("success") for t in tools_used):
        parts = ["I encountered some issues while processing your request:\n"]
        for tool in tools_used:
            parts.append(f"- {tool['tool_name']}: {tool['result']}\n")

    return "\n".join(parts)


def _format_partial_results(tools_used: list[dict]) -> str:
    """Format partial results when aborted"""
    if not tools_used:
        return ""

    successful = [t for t in tools_used if t.get("success")]
    if not successful:
        return ""

    parts = ["Based on what I was able to find:"]
    for tool in successful[:3]:  # Limit to 3 results
        parts.append(f"- {tool['result'][:500]}")

    return "\n".join(parts)


def _format_fallback_response(user_input: str, tools_used: list[dict]) -> str:
    """Generate fallback response when LLM fails"""
    if tools_used and any(t.get("success") for t in tools_used):
        return _format_tool_response(user_input, tools_used)

    return (
        "I apologize, but I encountered an issue while generating a response. "
        "Please try rephrasing your request or try again later."
    )
