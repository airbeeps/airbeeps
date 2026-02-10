"""
Unit tests for LangGraph Agent Nodes.

Tests for planner, executor, reflector, responder, and budget_checker nodes.
All tests use mocked LLM to ensure no real API calls are made.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestPlannerNode:
    """Tests for the planner node."""

    def test_parse_plan_response_direct_json(self):
        """Should parse direct JSON response."""
        from airbeeps.agents.graph.nodes.planner import _parse_plan_response

        content = (
            '{"needs_tools": true, "reasoning": "Need to search", "tool_calls": []}'
        )
        result = _parse_plan_response(content)

        assert result["needs_tools"] is True
        assert result["reasoning"] == "Need to search"

    def test_parse_plan_response_markdown_json(self):
        """Should parse JSON from markdown code block."""
        from airbeeps.agents.graph.nodes.planner import _parse_plan_response

        content = """Here's my plan:
```json
{"needs_tools": false, "reasoning": "Direct answer", "answer": "42"}
```
"""
        result = _parse_plan_response(content)

        assert result["needs_tools"] is False
        assert result["answer"] == "42"

    def test_parse_plan_response_embedded_json(self):
        """Should extract JSON from surrounding text."""
        from airbeeps.agents.graph.nodes.planner import _parse_plan_response

        content = 'Let me think... {"needs_tools": true, "tool_calls": [{"tool": "search"}]} ...done'
        result = _parse_plan_response(content)

        assert result["needs_tools"] is True
        assert len(result["tool_calls"]) == 1

    def test_parse_plan_response_invalid_json(self):
        """Should return direct answer for invalid JSON."""
        from airbeeps.agents.graph.nodes.planner import _parse_plan_response

        content = "This is just plain text without JSON"
        result = _parse_plan_response(content)

        assert result["needs_tools"] is False
        assert result["answer"] == content

    def test_should_use_tool_with_pending_calls(self):
        """Should route to execute when pending tool calls exist."""
        from airbeeps.agents.graph.nodes.planner import should_use_tool

        state = {"pending_tool_calls": [{"tool": "search", "input": {}}]}
        result = should_use_tool(state)

        assert result == "execute"

    def test_should_use_tool_with_final_answer(self):
        """Should route to respond when final answer exists."""
        from airbeeps.agents.graph.nodes.planner import should_use_tool

        state = {"final_answer": "Here is the answer", "pending_tool_calls": []}
        result = should_use_tool(state)

        assert result == "respond"

    def test_should_use_tool_empty_state(self):
        """Should route to respond when no pending calls or answer."""
        from airbeeps.agents.graph.nodes.planner import should_use_tool

        state = {}
        result = should_use_tool(state)

        assert result == "respond"

    @pytest.mark.asyncio
    async def test_planner_node_no_llm(self):
        """Should handle missing LLM gracefully."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        state = {"user_input": "test query", "token_usage": {}}
        result = await planner_node(state, llm=None)

        assert result["next_action"] == "respond"
        assert "Error" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_planner_node_direct_answer(self):
        """Should route to respond for direct answers."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"needs_tools": false, "reasoning": "Simple question", "answer": "The answer is 42"}',
                usage=MagicMock(
                    prompt_tokens=10, completion_tokens=20, total_tokens=30
                ),
            )
        )

        state = {
            "user_input": "What is the meaning of life?",
            "messages": [],
            "token_usage": {},
        }
        result = await planner_node(state, llm=mock_llm)

        assert result["next_action"] == "respond"
        assert result["final_answer"] == "The answer is 42"

    @pytest.mark.asyncio
    async def test_planner_node_with_tools(self):
        """Should route to execute when tools are needed."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "needs_tools": True,
                        "reasoning": "Need to search for current info",
                        "tool_calls": [
                            {"tool": "web_search", "input": {"query": "weather"}}
                        ],
                    }
                ),
                usage=MagicMock(
                    prompt_tokens=50, completion_tokens=30, total_tokens=80
                ),
            )
        )

        mock_tool = MagicMock()
        mock_tool.name = "web_search"
        mock_tool.description = "Search the web"
        mock_tool.get_input_schema = MagicMock(return_value={"query": "string"})

        state = {"user_input": "What's the weather?", "messages": [], "token_usage": {}}
        result = await planner_node(state, llm=mock_llm, tools=[mock_tool])

        assert result["next_action"] == "execute"
        assert len(result["pending_tool_calls"]) == 1
        assert result["pending_tool_calls"][0]["tool"] == "web_search"

    @pytest.mark.asyncio
    async def test_planner_node_with_memory_service(self):
        """Should integrate memory context when available."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"needs_tools": false, "reasoning": "Using context", "answer": "Based on our history..."}',
                usage=None,
            )
        )

        mock_memory = AsyncMock()
        mock_memory.recall_memories = AsyncMock(
            return_value=[{"type": "fact", "content": "User prefers Python"}]
        )

        state = {
            "user_input": "What language should I use?",
            "messages": [],
            "token_usage": {},
        }
        result = await planner_node(
            state,
            llm=mock_llm,
            memory_service=mock_memory,
            assistant_id="550e8400-e29b-41d4-a716-446655440000",
            user_id="550e8400-e29b-41d4-a716-446655440001",
        )

        assert "memory_context" in result
        mock_memory.recall_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_planner_node_exception_handling(self):
        """Should handle LLM exceptions gracefully."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM connection failed"))

        state = {"user_input": "test", "messages": [], "token_usage": {}}
        result = await planner_node(state, llm=mock_llm)

        assert result["next_action"] == "respond"
        assert "error" in result["final_answer"].lower()


class TestExecutorNode:
    """Tests for the executor node."""

    @pytest.mark.asyncio
    async def test_executor_node_no_pending_calls(self):
        """Should route to reflect when no pending calls."""
        from airbeeps.agents.graph.nodes.executor import executor_node

        state = {"pending_tool_calls": [], "messages": []}
        result = await executor_node(state)

        assert result["next_action"] == "reflect"

    @pytest.mark.asyncio
    async def test_executor_node_no_executor(self):
        """Should route to reflect when no tool executor."""
        from airbeeps.agents.graph.nodes.executor import executor_node

        state = {"pending_tool_calls": [{"tool": "test"}], "messages": []}
        result = await executor_node(state, tool_executor=None)

        assert result["next_action"] == "reflect"

    @pytest.mark.asyncio
    async def test_executor_node_successful_execution(self):
        """Should execute tools and record results."""
        from airbeeps.agents.graph.nodes.executor import executor_node

        async def mock_executor(tool_name: str, tool_input: dict):
            return f"Result for {tool_name}"

        state = {
            "pending_tool_calls": [{"tool": "search", "input": {"query": "test"}}],
            "tools_used": [],
            "messages": [],
        }

        result = await executor_node(state, tool_executor=mock_executor)

        assert result["next_action"] == "reflect"
        assert len(result["tools_used"]) == 1
        assert result["tools_used"][0]["success"] is True
        assert result["pending_tool_calls"] == []

    @pytest.mark.asyncio
    async def test_executor_node_tool_limit(self):
        """Should respect tool call limits."""
        from airbeeps.agents.graph.nodes.executor import executor_node

        state = {
            "pending_tool_calls": [{"tool": "test"}],
            "tools_used": [{"tool_name": f"tool_{i}"} for i in range(20)],
            "max_tool_calls": 20,
            "messages": [],
        }

        result = await executor_node(state)

        # When no executor is provided, pending calls remain but we route to reflect
        assert result["next_action"] == "reflect"

    @pytest.mark.asyncio
    async def test_executor_node_cost_tracking(self):
        """Should track execution costs."""
        from airbeeps.agents.graph.nodes.executor import executor_node

        async def mock_executor(tool_name: str, tool_input: dict):
            return "Result"

        state = {
            "pending_tool_calls": [{"tool": "search", "input": {}}],
            "tools_used": [],
            "messages": [],
            "cost_spent_usd": 0.0,
        }

        result = await executor_node(state, tool_executor=mock_executor)

        assert "last_execution_stats" in result
        assert result["last_execution_stats"]["total_calls"] == 1


class TestToolExecutionResult:
    """Tests for ToolExecutionResult dataclass."""

    def test_tool_execution_result_to_dict(self):
        """Should convert to dictionary correctly."""
        from airbeeps.agents.graph.nodes.executor import ToolExecutionResult

        result = ToolExecutionResult(
            tool_name="search",
            tool_input={"query": "test"},
            result="Found results",
            success=True,
            duration_ms=100,
        )

        data = result.to_dict()

        assert data["tool_name"] == "search"
        assert data["success"] is True
        assert data["duration_ms"] == 100

    def test_tool_execution_result_failure(self):
        """Should handle failure results."""
        from airbeeps.agents.graph.nodes.executor import ToolExecutionResult

        result = ToolExecutionResult(
            tool_name="api",
            tool_input={},
            result="Error: Connection failed",
            success=False,
            duration_ms=50,
            error_type="ConnectionError",
        )

        assert result.success is False
        assert result.error_type == "ConnectionError"


class TestParallelExecutor:
    """Tests for ParallelExecutor class."""

    def test_parallel_executor_timeout_lookup(self):
        """Should use tool-specific timeouts."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        executor = ParallelExecutor(
            default_timeout=30,
            tool_timeouts={"slow_tool": 60, "fast_tool": 5},
        )

        assert executor._get_timeout("slow_tool") == 60
        assert executor._get_timeout("fast_tool") == 5
        assert executor._get_timeout("unknown_tool") == 30

    def test_parallel_executor_retryable_check(self):
        """Should identify retryable errors."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        executor = ParallelExecutor()

        assert executor._is_retryable("timeout", "")
        assert executor._is_retryable(None, "Rate limit exceeded")
        assert executor._is_retryable(None, "Connection reset")
        assert not executor._is_retryable(None, "Invalid input")

    @pytest.mark.asyncio
    async def test_parallel_executor_batch_execution(self):
        """Should execute batch with concurrency limit."""
        from airbeeps.agents.graph.nodes.executor import ParallelExecutor

        call_order = []

        async def mock_executor(tool_name: str, tool_input: dict):
            call_order.append(tool_name)
            return f"Result: {tool_name}"

        executor = ParallelExecutor(max_concurrent=2)
        calls = [
            {"tool": "tool1", "input": {}},
            {"tool": "tool2", "input": {}},
            {"tool": "tool3", "input": {}},
        ]

        results = await executor.execute_batch(mock_executor, calls)

        assert len(results) == 3
        assert all(r.success for r in results)


class TestReflectorNode:
    """Tests for the reflector node."""

    def test_parse_reflection_response_valid_json(self):
        """Should parse valid JSON reflection."""
        from airbeeps.agents.graph.nodes.reflector import _parse_reflection_response

        content = (
            '{"quality_score": 8, "has_enough_info": true, "reasoning": "Good results"}'
        )
        result = _parse_reflection_response(content)

        assert result["quality_score"] == 8
        assert result["has_enough_info"] is True

    def test_parse_reflection_response_invalid(self):
        """Should provide defaults for invalid JSON."""
        from airbeeps.agents.graph.nodes.reflector import _parse_reflection_response

        content = "This is not JSON"
        result = _parse_reflection_response(content)

        assert result["quality_score"] == 5.0
        assert result["has_enough_info"] is True

    def test_format_tool_results_empty(self):
        """Should handle empty tool results."""
        from airbeeps.agents.graph.nodes.reflector import _format_tool_results

        result = _format_tool_results([])
        assert result == "No tools used yet."

    def test_format_tool_results_with_data(self):
        """Should format tool results correctly."""
        from airbeeps.agents.graph.nodes.reflector import _format_tool_results

        tools = [
            {
                "tool_name": "search",
                "result": "Found 10 results",
                "success": True,
                "duration_ms": 200,
            },
            {
                "tool_name": "api",
                "result": "Error",
                "success": False,
                "duration_ms": 50,
            },
        ]

        result = _format_tool_results(tools)

        assert "search" in result
        assert "✓" in result
        assert "✗" in result

    @pytest.mark.asyncio
    async def test_reflector_node_no_llm(self):
        """Should proceed to respond without LLM."""
        from airbeeps.agents.graph.nodes.reflector import reflector_node

        state = {"messages": []}
        result = await reflector_node(state, llm=None)

        assert result["next_action"] == "respond"

    @pytest.mark.asyncio
    async def test_reflector_node_high_quality(self):
        """Should proceed to respond with high quality score."""
        from airbeeps.agents.graph.nodes.reflector import reflector_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"quality_score": 9, "has_enough_info": true, "reasoning": "Excellent"}',
                usage=MagicMock(total_tokens=50),
            )
        )

        state = {
            "user_input": "test",
            "plan": "search and respond",
            "tools_used": [
                {
                    "tool_name": "search",
                    "result": "data",
                    "success": True,
                    "duration_ms": 100,
                }
            ],
            "reflections": [],
            "messages": [],
            "token_usage": {},
        }

        result = await reflector_node(state, llm=mock_llm, quality_threshold=7.0)

        assert result["next_action"] == "respond"
        assert result["quality_score"] == 9

    @pytest.mark.asyncio
    async def test_reflector_node_needs_more_tools(self):
        """Should route to execute when more tools needed."""
        from airbeeps.agents.graph.nodes.reflector import reflector_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "quality_score": 5,
                        "has_enough_info": False,
                        "next_tool_calls": [{"tool": "api", "input": {}}],
                        "reasoning": "Need more data",
                    }
                ),
                usage=MagicMock(total_tokens=60),
            )
        )

        state = {
            "user_input": "test",
            "plan": "",
            "tools_used": [],
            "reflections": [],
            "messages": [],
            "token_usage": {},
        }

        result = await reflector_node(state, llm=mock_llm)

        assert result["next_action"] == "execute"
        assert len(result["pending_tool_calls"]) == 1

    def test_should_continue_reflecting_execute(self):
        """Should return execute when pending calls exist."""
        from airbeeps.agents.graph.nodes.reflector import should_continue_reflecting

        state = {"next_action": "execute", "pending_tool_calls": [{"tool": "test"}]}
        assert should_continue_reflecting(state) == "execute"

    def test_should_continue_reflecting_plan(self):
        """Should return plan when replan needed."""
        from airbeeps.agents.graph.nodes.reflector import should_continue_reflecting

        state = {"next_action": "plan"}
        assert should_continue_reflecting(state) == "plan"


class TestResponderNode:
    """Tests for the responder node."""

    def test_format_tool_response(self):
        """Should format tool responses correctly."""
        from airbeeps.agents.graph.nodes.responder import _format_tool_response

        tools = [
            {"tool_name": "search", "result": "Found 5 items", "success": True},
            {"tool_name": "api", "result": "Error", "success": False},
        ]

        result = _format_tool_response("test query", tools)

        assert "search" in result
        assert "Found 5 items" in result

    def test_format_tool_response_all_failed(self):
        """Should indicate issues when all tools failed."""
        from airbeeps.agents.graph.nodes.responder import _format_tool_response

        tools = [{"tool_name": "api", "result": "Error", "success": False}]

        result = _format_tool_response("test", tools)

        assert "issues" in result.lower()

    @pytest.mark.asyncio
    async def test_responder_node_with_final_answer(self):
        """Should use existing final answer."""
        from airbeeps.agents.graph.nodes.responder import responder_node

        state = {"final_answer": "Pre-computed answer"}
        result = await responder_node(state)

        assert result["final_answer"] == "Pre-computed answer"
        assert result["next_action"] == "done"

    @pytest.mark.asyncio
    async def test_responder_node_abort_with_partial_results(self):
        """Should include partial results when aborted."""
        from airbeeps.agents.graph.nodes.responder import responder_node

        state = {
            "final_answer": "Budget exceeded",
            "abort_reason": "Cost limit reached",
            "tools_used": [
                {"tool_name": "search", "result": "Partial data", "success": True}
            ],
        }

        result = await responder_node(state)

        assert "Budget exceeded" in result["final_answer"]
        assert result["next_action"] == "done"

    @pytest.mark.asyncio
    async def test_responder_node_no_llm(self):
        """Should format response from tools without LLM."""
        from airbeeps.agents.graph.nodes.responder import responder_node

        state = {
            "user_input": "test",
            "tools_used": [
                {"tool_name": "search", "result": "Data found", "success": True}
            ],
        }

        result = await responder_node(state, llm=None)

        assert "Data found" in result["final_answer"]
        assert result["next_action"] == "done"

    @pytest.mark.asyncio
    async def test_responder_node_with_llm(self):
        """Should generate response with LLM."""
        from airbeeps.agents.graph.nodes.responder import responder_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content="Here is a comprehensive answer based on the search results.",
                usage=MagicMock(
                    prompt_tokens=100, completion_tokens=50, total_tokens=150
                ),
            )
        )

        state = {
            "user_input": "What is X?",
            "plan": "Search and synthesize",
            "tools_used": [
                {"tool_name": "search", "result": "X is a thing", "success": True}
            ],
            "messages": [],
            "token_usage": {},
        }

        result = await responder_node(state, llm=mock_llm)

        assert "comprehensive answer" in result["final_answer"]
        assert result["next_action"] == "done"
        mock_llm.ainvoke.assert_called_once()


class TestBudgetCheckerNode:
    """Tests for the budget checker node."""

    def test_estimate_tokens(self):
        """Should estimate tokens from messages."""
        from airbeeps.agents.graph.nodes.budget_checker import estimate_tokens

        messages = [
            {"content": "This is a test message with some content."},
            {"content": "Another message here."},
        ]

        tokens = estimate_tokens(messages)
        assert tokens > 0
        assert tokens < 100  # Reasonable estimate

    def test_estimate_tokens_list_content(self):
        """Should handle list content in messages."""
        from airbeeps.agents.graph.nodes.budget_checker import estimate_tokens

        messages = [
            {"content": [{"text": "Part one"}, {"text": "Part two"}]},
        ]

        tokens = estimate_tokens(messages)
        assert tokens > 0

    @pytest.mark.asyncio
    async def test_compress_state_few_messages(self):
        """Should not compress when few messages."""
        from airbeeps.agents.graph.nodes.budget_checker import compress_state

        state = {"messages": [{"role": "user", "content": "Hi"}]}
        result = await compress_state(state)

        assert result == state  # No change

    @pytest.mark.asyncio
    async def test_compress_state_many_messages(self):
        """Should compress old messages."""
        from airbeeps.agents.graph.nodes.budget_checker import compress_state

        messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
        state = {"messages": messages}

        result = await compress_state(state)

        assert len(result["messages"]) < 10
        assert result["compression_count"] == 1
        assert "compressed_history" in result

    @pytest.mark.asyncio
    async def test_budget_checker_iteration_limit(self):
        """Should abort when iteration limit reached."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {"iterations": 10, "max_iterations": 10, "messages": []}
        result = await budget_checker_node(state)

        assert result["next_action"] == "abort"
        assert "iterations" in result["abort_reason"].lower()

    @pytest.mark.asyncio
    async def test_budget_checker_cost_limit(self):
        """Should abort when cost limit reached."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {
            "iterations": 0,
            "cost_spent_usd": 0.50,
            "cost_limit_usd": 0.50,
            "messages": [],
        }

        result = await budget_checker_node(state)

        assert result["next_action"] == "abort"
        assert "cost" in result["abort_reason"].lower()

    @pytest.mark.asyncio
    async def test_budget_checker_tool_limit(self):
        """Should abort when tool call limit reached."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {
            "iterations": 0,
            "cost_spent_usd": 0,
            "cost_limit_usd": 0.50,
            "tools_used": [{"name": f"tool_{i}"} for i in range(20)],
            "max_tool_calls": 20,
            "messages": [],
        }

        result = await budget_checker_node(state)

        assert result["next_action"] == "abort"
        assert "tool" in result["abort_reason"].lower()

    @pytest.mark.asyncio
    async def test_budget_checker_normal_flow(self):
        """Should continue normally when under limits."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {
            "iterations": 2,
            "max_iterations": 10,
            "cost_spent_usd": 0.10,
            "cost_limit_usd": 0.50,
            "tools_used": [],
            "max_tool_calls": 20,
            "messages": [],
        }

        result = await budget_checker_node(state)

        assert result["next_action"] != "abort"
        assert result["iterations"] == 3

    @pytest.mark.asyncio
    async def test_budget_checker_budget_warning(self):
        """Should set warning when approaching limit."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {
            "iterations": 0,
            "cost_spent_usd": 0.46,
            "cost_limit_usd": 0.50,
            "tools_used": [],
            "messages": [],
        }

        result = await budget_checker_node(state)

        assert "budget_warning" in result
        assert result["next_action"] != "abort"

    def test_should_continue_abort(self):
        """Should route to responder on abort."""
        from airbeeps.agents.graph.nodes.budget_checker import should_continue

        state = {"next_action": "abort"}
        assert should_continue(state) == "responder"

    def test_should_continue_plan(self):
        """Should return next action from state."""
        from airbeeps.agents.graph.nodes.budget_checker import should_continue

        state = {"next_action": "plan"}
        assert should_continue(state) == "plan"
