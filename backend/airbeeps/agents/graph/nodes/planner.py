"""
Planner Node for LangGraph.

Responsible for:
- Analyzing user input
- Retrieving relevant memories for context
- Decomposing tasks into sub-goals
- Deciding which tools to use
- Creating execution plan
"""

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """You are a planning assistant. Analyze the user's request and create a plan.

{memory_context}

Given the user's request, decide:
1. Can you answer directly without tools? If yes, set "needs_tools": false
2. If tools are needed, which tools and in what order?

Available tools:
{tools_description}

Respond with a JSON object:
{{
    "needs_tools": true/false,
    "reasoning": "Your analysis of the request",
    "plan": ["Step 1: ...", "Step 2: ..."],
    "tool_calls": [
        {{"tool": "tool_name", "input": {{"param": "value"}}}},
        ...
    ]
}}

If you can answer directly without tools, respond with:
{{
    "needs_tools": false,
    "reasoning": "Why no tools are needed",
    "answer": "Your direct answer"
}}
"""

PLANNING_PROMPT_WITH_MEMORY = """You are a planning assistant with access to relevant context from previous interactions.

Previous relevant context:
{memory_context}

Given the user's request, decide:
1. Can you answer directly without tools? If yes, set "needs_tools": false
2. If tools are needed, which tools and in what order?

Available tools:
{tools_description}

Respond with a JSON object:
{{
    "needs_tools": true/false,
    "reasoning": "Your analysis of the request",
    "plan": ["Step 1: ...", "Step 2: ..."],
    "tool_calls": [
        {{"tool": "tool_name", "input": {{"param": "value"}}}},
        ...
    ]
}}

If you can answer directly without tools, respond with:
{{
    "needs_tools": false,
    "reasoning": "Why no tools are needed",
    "answer": "Your direct answer"
}}
"""


async def planner_node(
    state: dict[str, Any],
    llm: Any = None,
    tools: list | None = None,
    memory_service: Any = None,
    assistant_id: uuid.UUID | str | None = None,
    user_id: uuid.UUID | str | None = None,
    embedding_model_id: str | None = None,
) -> dict[str, Any]:
    """
    Plan the task execution.

    This node:
    1. Retrieves relevant memories from previous interactions
    2. Analyzes the user input
    3. Decides if tools are needed
    4. Creates a plan with tool calls
    5. Routes to executor or responder

    Args:
        state: Current agent state
        llm: Language model for planning
        tools: Available tools list
        memory_service: Optional memory service for context retrieval
        assistant_id: Assistant ID for memory lookup
        user_id: User ID for memory lookup
        embedding_model_id: Model ID for memory embeddings

    Returns:
        Updated state with plan
    """
    if not llm:
        logger.error("No LLM provided to planner node")
        state["next_action"] = "respond"
        state["final_answer"] = "Error: Planning failed - no LLM configured"
        return state

    user_input = state.get("user_input", "")
    messages = state.get("messages", [])

    # Build tools description
    tools_description = "None available"
    if tools:
        tools_desc_parts = []
        for tool in tools:
            name = tool.name if hasattr(tool, "name") else str(tool)
            desc = tool.description if hasattr(tool, "description") else ""
            schema = (
                tool.get_input_schema() if hasattr(tool, "get_input_schema") else {}
            )
            tools_desc_parts.append(
                f"- {name}: {desc}\n  Parameters: {json.dumps(schema)}"
            )
        tools_description = "\n".join(tools_desc_parts)

    # Retrieve relevant memories if memory service is available
    memory_context = ""
    if memory_service and assistant_id and user_id:
        try:
            # Convert string IDs to UUIDs if needed
            if isinstance(assistant_id, str):
                assistant_id = uuid.UUID(assistant_id)
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)

            memories = await memory_service.recall_memories(
                query=user_input,
                assistant_id=assistant_id,
                user_id=user_id,
                top_k=3,
                embedding_model_id=embedding_model_id,
            )

            if memories:
                memory_parts = []
                for m in memories:
                    memory_parts.append(f"- [{m['type']}] {m['content']}")
                memory_context = "\n".join(memory_parts)
                state["memory_context"] = memories
                logger.debug(f"Retrieved {len(memories)} memories for planning")
        except Exception as e:
            logger.warning(f"Failed to retrieve memories for planning: {e}")

    # Build planning prompt
    if memory_context:
        planning_prompt = PLANNING_PROMPT_WITH_MEMORY.format(
            memory_context=memory_context,
            tools_description=tools_description,
        )
    else:
        planning_prompt = PLANNING_PROMPT.format(
            memory_context="",
            tools_description=tools_description,
        )

    # Build messages for LLM
    planning_messages = [
        {"role": "system", "content": planning_prompt},
    ]

    # Add context from previous messages if available
    if messages:
        # Add last few messages for context
        for msg in messages[-3:]:
            planning_messages.append(msg)

    # Add current user input
    planning_messages.append({"role": "user", "content": user_input})

    try:
        # Call LLM for planning
        response = await llm.ainvoke(planning_messages)

        # Extract content
        if hasattr(response, "content"):
            content = response.content
        elif hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content
        else:
            content = str(response)

        # Track token usage and cost
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or (
                input_tokens + output_tokens
            )

            state["token_usage"]["planning"] = total_tokens
            state["token_usage"]["planning_input"] = input_tokens
            state["token_usage"]["planning_output"] = output_tokens

            # Track cost using model-aware estimation
            try:
                from ..cost_estimator import estimate_cost

                model_name = state.get("model_name", "default")
                planning_cost = estimate_cost(input_tokens, output_tokens, model_name)
                state["cost_spent_usd"] = state.get("cost_spent_usd", 0) + planning_cost
            except ImportError:
                # Fallback to rough estimate
                state["cost_spent_usd"] = state.get("cost_spent_usd", 0) + (
                    total_tokens / 1000 * 0.01
                )

        # Parse planning response
        plan_data = _parse_plan_response(content)

        state["plan"] = plan_data.get("reasoning", "")

        if plan_data.get("needs_tools", False):
            # Tools needed - set up tool calls
            tool_calls = plan_data.get("tool_calls", [])

            if tool_calls:
                state["pending_tool_calls"] = tool_calls
                state["next_action"] = "execute"
                logger.info(f"Plan created with {len(tool_calls)} tool calls")
            else:
                # No tool calls but needs_tools=True - try to extract from plan
                state["next_action"] = "respond"
                state["final_answer"] = plan_data.get("reasoning", content)
        else:
            # No tools needed - direct answer
            state["final_answer"] = plan_data.get("answer", content)
            state["next_action"] = "respond"
            logger.info("Plan indicates direct answer without tools")

        # Add to messages
        state["messages"] = messages + [
            {"role": "assistant", "content": f"[Planning]: {state['plan']}"}
        ]

    except Exception as e:
        logger.error(f"Planning failed: {e}")
        state["next_action"] = "respond"
        state["final_answer"] = f"I encountered an error while planning: {e}"

    return state


def _parse_plan_response(content: str) -> dict[str, Any]:
    """Parse the planning response from LLM"""
    # Try to extract JSON from the response
    try:
        # Direct JSON parse
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown code block
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            try:
                return json.loads(content[start:end].strip())
            except json.JSONDecodeError:
                pass

    # Try to find JSON object anywhere in text
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

    # Failed to parse - return as direct answer
    return {
        "needs_tools": False,
        "reasoning": "Could not parse planning response",
        "answer": content,
    }


def should_use_tool(state: dict[str, Any]) -> str:
    """
    Routing function: decide if we should use tools or respond directly.
    """
    if state.get("pending_tool_calls"):
        return "execute"
    if state.get("final_answer"):
        return "respond"
    return "respond"
