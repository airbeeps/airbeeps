"""
Budget Checker Node for LangGraph.

Checks and enforces budget limits before each iteration:
- Token budget
- Iteration limit
- Cost limit
- Tool call limit

Also handles state compression when approaching token limits.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def estimate_tokens(messages: list[dict]) -> int:
    """
    Estimate token count for messages.

    Uses cost_estimator module if available, otherwise simple estimation.
    """
    try:
        from ..cost_estimator import estimate_message_tokens

        return estimate_message_tokens(messages)
    except ImportError:
        pass

    # Fallback: ~4 chars per token for English text
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total_chars += len(part["text"])

    return total_chars // 4


async def compress_state(state: dict[str, Any], llm: Any = None) -> dict[str, Any]:
    """
    Compress old messages to save tokens.

    Summarizes older messages while keeping recent context.
    """
    messages = state.get("messages", [])

    if len(messages) <= 5:
        return state

    # Split messages: keep last 5, summarize the rest
    old_messages = messages[:-5]
    recent_messages = messages[-5:]

    # Create summary of old messages
    summary_parts = []
    for msg in old_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 100:
            content = content[:100] + "..."
        summary_parts.append(f"[{role}]: {content}")

    summary = "Previous conversation summary:\n" + "\n".join(summary_parts)

    # If LLM is provided, use it for better summarization
    if llm:
        try:
            summary_prompt = (
                "Summarize this conversation history in 2-3 sentences, "
                "preserving key information and context:\n\n" + "\n".join(summary_parts)
            )
            response = await llm.ainvoke([{"role": "user", "content": summary_prompt}])
            if hasattr(response, "content"):
                summary = f"Previous context: {response.content}"
            elif hasattr(response, "choices") and response.choices:
                summary = f"Previous context: {response.choices[0].message.content}"
        except Exception as e:
            logger.warning(f"LLM summarization failed, using simple summary: {e}")

    # Replace old messages with summary
    new_messages = [{"role": "system", "content": summary}] + recent_messages

    state["messages"] = new_messages
    state["compressed_history"] = summary
    state["compression_count"] = state.get("compression_count", 0) + 1

    logger.info(
        f"Compressed {len(old_messages)} messages to summary. "
        f"Compression count: {state['compression_count']}"
    )

    return state


async def budget_checker_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Check budgets and compress state if needed.

    This node runs at the start of each iteration to:
    1. Check token budget and compress if needed
    2. Check iteration limit
    3. Check cost limit
    4. Check tool call limit

    Sets next_action to "abort" if any limit is exceeded.
    """
    # 1. Check iteration limit
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 10)

    if iterations >= max_iterations:
        logger.warning(f"Max iterations reached: {iterations}/{max_iterations}")
        state["next_action"] = "abort"
        state["abort_reason"] = f"Maximum iterations ({max_iterations}) reached"
        state["final_answer"] = (
            "I've reached the maximum number of reasoning steps. "
            "Here's a summary of what I found so far..."
        )
        return state

    # 2. Check cost limit
    cost_spent = state.get("cost_spent_usd", 0.0)
    cost_limit = state.get("cost_limit_usd", 0.50)

    if cost_spent >= cost_limit:
        logger.warning(f"Cost limit reached: ${cost_spent:.4f}/${cost_limit:.2f}")
        state["next_action"] = "abort"
        state["abort_reason"] = f"Cost limit (${cost_limit:.2f}) reached"
        state["final_answer"] = (
            f"I've reached the cost limit for this conversation (${cost_limit:.2f}). "
            "Summarizing what I found..."
        )
        return state

    # Early warning if approaching budget limit (>90% used)
    budget_percentage = (cost_spent / cost_limit * 100) if cost_limit > 0 else 0
    if budget_percentage >= 90:
        logger.warning(
            f"Budget nearly exhausted: ${cost_spent:.4f}/${cost_limit:.2f} ({budget_percentage:.1f}%)"
        )
        # Don't abort, but add warning to state
        state["budget_warning"] = f"Budget is {budget_percentage:.1f}% used"

    # 3. Check tool call limit
    tools_used = state.get("tools_used", [])
    max_tool_calls = state.get("max_tool_calls", 20)

    if len(tools_used) >= max_tool_calls:
        logger.warning(f"Tool call limit reached: {len(tools_used)}/{max_tool_calls}")
        state["next_action"] = "abort"
        state["abort_reason"] = f"Tool call limit ({max_tool_calls}) reached"
        state["final_answer"] = (
            "I've used the maximum number of tool calls for this conversation. "
            "Based on what I found..."
        )
        return state

    # 4. Check token budget and compress if needed
    messages = state.get("messages", [])
    estimated_tokens = estimate_tokens(messages)
    token_budget = state.get("token_budget", 8000)

    if estimated_tokens > token_budget * 0.8:
        logger.info(
            f"Approaching token limit ({estimated_tokens}/{token_budget}), compressing state"
        )
        state = await compress_state(state)

    # Update iteration count
    state["iterations"] = iterations + 1

    # Continue to next phase (planner by default)
    if state.get("next_action") != "abort":
        # Determine next action based on current state
        if not state.get("plan"):
            state["next_action"] = "plan"
        elif state.get("pending_tool_calls"):
            state["next_action"] = "execute"
        else:
            state["next_action"] = "plan"

    return state


def should_continue(state: dict[str, Any]) -> str:
    """
    Routing function for conditional edges.

    Returns the next node to route to based on state.
    """
    next_action = state.get("next_action", "plan")

    if next_action == "abort":
        return "responder"

    return next_action
