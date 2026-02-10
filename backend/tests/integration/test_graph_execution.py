"""
Integration tests for LangGraph agent execution.

Tests full graph runs with mocked LLM to ensure no real API calls.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestFullGraphExecution:
    """Tests for full agent graph execution flow."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mocked LLM."""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def mock_assistant(self):
        """Create a mock assistant."""
        assistant = MagicMock()
        assistant.id = uuid4()
        assistant.name = "Test Assistant"
        assistant.system_prompt = "You are a helpful assistant."
        assistant.agent_max_iterations = 5
        assistant.agent_token_budget = 4000
        assistant.agent_cost_limit_usd = 0.50
        assistant.agent_enable_planning = True
        assistant.agent_enable_reflection = True
        return assistant

    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool."""
        from airbeeps.agents.tools.base import AgentTool

        class MockTool(AgentTool):
            @property
            def name(self) -> str:
                return "mock_search"

            @property
            def description(self) -> str:
                return "A mock search tool"

            @property
            def security_level(self) -> str:
                return "SAFE"

            def get_input_schema(self) -> dict:
                return {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                }

            async def execute(self, query: str) -> str:
                return f"Search results for: {query}"

        return MockTool()

    @pytest.mark.asyncio
    async def test_direct_answer_flow(self, mock_llm):
        """Test flow when planner decides no tools needed."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        # Mock LLM to return direct answer
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"needs_tools": false, "reasoning": "Simple question", "answer": "The answer is 42"}',
                usage=MagicMock(
                    prompt_tokens=10, completion_tokens=20, total_tokens=30
                ),
            )
        )

        state = {
            "user_input": "What is 6 times 7?",
            "messages": [],
            "token_usage": {},
        }

        result = await planner_node(state, llm=mock_llm)

        assert result["next_action"] == "respond"
        assert result["final_answer"] == "The answer is 42"

    @pytest.mark.asyncio
    async def test_tool_execution_flow(self, mock_llm, mock_tool):
        """Test flow when planner decides to use tools."""
        from airbeeps.agents.graph.nodes.executor import executor_node
        from airbeeps.agents.graph.nodes.planner import planner_node
        from airbeeps.agents.graph.nodes.reflector import reflector_node

        # Step 1: Planner decides to use tool
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"needs_tools": true, "reasoning": "Need current info", "tool_calls": [{"tool": "mock_search", "input": {"query": "latest news"}}]}',
                usage=MagicMock(
                    prompt_tokens=50, completion_tokens=30, total_tokens=80
                ),
            )
        )

        state = {
            "user_input": "What's the latest news?",
            "messages": [],
            "token_usage": {},
        }

        plan_result = await planner_node(state, llm=mock_llm, tools=[mock_tool])

        assert plan_result["next_action"] == "execute"
        assert len(plan_result["pending_tool_calls"]) == 1

        # Step 2: Executor runs the tool
        async def mock_executor(tool_name: str, tool_input: dict):
            return await mock_tool.execute(**tool_input)

        exec_result = await executor_node(plan_result, tool_executor=mock_executor)

        assert exec_result["next_action"] == "reflect"
        assert len(exec_result["tools_used"]) == 1

        # Step 3: Reflector evaluates results
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"quality_score": 8, "has_enough_info": true, "reasoning": "Good results"}',
                usage=MagicMock(total_tokens=50),
            )
        )

        reflect_result = await reflector_node(exec_result, llm=mock_llm)

        assert reflect_result["next_action"] == "respond"
        assert reflect_result["quality_score"] == 8

    @pytest.mark.asyncio
    async def test_budget_abort_flow(self, mock_llm):
        """Test flow when budget is exceeded."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {
            "user_input": "Complex query",
            "iterations": 0,
            "cost_spent_usd": 0.55,  # Over budget
            "cost_limit_usd": 0.50,
            "tools_used": [],
            "messages": [],
        }

        result = await budget_checker_node(state)

        assert result["next_action"] == "abort"
        assert "cost" in result["abort_reason"].lower()

    @pytest.mark.asyncio
    async def test_iteration_limit_flow(self, mock_llm):
        """Test flow when iteration limit is reached."""
        from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node

        state = {
            "user_input": "Complex query",
            "iterations": 10,
            "max_iterations": 10,
            "cost_spent_usd": 0.0,
            "cost_limit_usd": 0.50,
            "tools_used": [],
            "messages": [],
        }

        result = await budget_checker_node(state)

        assert result["next_action"] == "abort"
        assert "iteration" in result["abort_reason"].lower()

    @pytest.mark.asyncio
    async def test_responder_with_tool_results(self, mock_llm):
        """Test responder synthesizes tool results."""
        from airbeeps.agents.graph.nodes.responder import responder_node

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content="Based on my search, here is a comprehensive answer...",
                usage=MagicMock(
                    prompt_tokens=100, completion_tokens=50, total_tokens=150
                ),
            )
        )

        state = {
            "user_input": "What is Python?",
            "plan": "Search and respond",
            "tools_used": [
                {
                    "tool_name": "search",
                    "result": "Python is a programming language",
                    "success": True,
                }
            ],
            "reflections": [],
            "messages": [],
            "token_usage": {},
        }

        result = await responder_node(state, llm=mock_llm)

        assert result["next_action"] == "done"
        assert "comprehensive" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_reflection_retry_flow(self, mock_llm, mock_tool):
        """Test flow when reflector requests more tools."""
        from airbeeps.agents.graph.nodes.reflector import reflector_node

        # Reflector requests more tools
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"quality_score": 4, "has_enough_info": false, "next_tool_calls": [{"tool": "search", "input": {"query": "more specific"}}], "reasoning": "Need more data"}',
                usage=MagicMock(total_tokens=60),
            )
        )

        state = {
            "user_input": "Complex question",
            "plan": "Search",
            "tools_used": [
                {
                    "tool_name": "search",
                    "result": "Incomplete",
                    "success": True,
                    "duration_ms": 100,
                }
            ],
            "reflections": [],
            "messages": [],
            "token_usage": {},
        }

        result = await reflector_node(state, llm=mock_llm)

        assert result["next_action"] == "execute"
        assert len(result["pending_tool_calls"]) == 1


class TestGraphWithMemory:
    """Tests for graph execution with memory integration."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mocked memory service."""
        memory = AsyncMock()
        memory.recall_memories = AsyncMock(
            return_value=[
                {"type": "preference", "content": "User prefers detailed explanations"},
            ]
        )
        return memory

    @pytest.mark.asyncio
    async def test_planner_uses_memory_context(self, mock_memory_service):
        """Test that planner incorporates memory context."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"needs_tools": false, "reasoning": "Using context", "answer": "Based on your preference for detail..."}',
                usage=None,
            )
        )

        state = {
            "user_input": "Explain this concept",
            "messages": [],
            "token_usage": {},
        }

        result = await planner_node(
            state,
            llm=mock_llm,
            memory_service=mock_memory_service,
            assistant_id="550e8400-e29b-41d4-a716-446655440000",
            user_id="550e8400-e29b-41d4-a716-446655440001",
        )

        assert "memory_context" in result
        mock_memory_service.recall_memories.assert_called_once()


class TestGraphStateManagement:
    """Tests for graph state management."""

    def test_state_to_dict(self):
        """Test AgentState serialization."""
        from airbeeps.agents.graph.state import AgentState

        state = AgentState(
            user_input="test",
            iterations=2,
            cost_spent_usd=0.05,
        )

        state_dict = state.to_dict()

        assert state_dict["user_input"] == "test"
        assert state_dict["iterations"] == 2
        assert state_dict["cost_spent_usd"] == 0.05

    def test_state_from_dict(self):
        """Test AgentState deserialization."""
        from airbeeps.agents.graph.state import AgentState

        data = {
            "user_input": "test query",
            "iterations": 3,
            "cost_spent_usd": 0.10,
        }

        state = AgentState.from_dict(data)

        assert state.user_input == "test query"
        assert state.iterations == 3

    def test_budget_config_defaults(self):
        """Test BudgetConfig has sensible defaults."""
        from airbeeps.agents.graph.state import BudgetConfig

        config = BudgetConfig()

        assert config.token_budget == 8000
        assert config.max_iterations == 10
        assert config.cost_limit_usd == 0.50


class TestGraphErrorHandling:
    """Tests for error handling in graph execution."""

    @pytest.mark.asyncio
    async def test_planner_handles_llm_error(self):
        """Test planner handles LLM errors gracefully."""
        from airbeeps.agents.graph.nodes.planner import planner_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM API error"))

        state = {
            "user_input": "test",
            "messages": [],
            "token_usage": {},
        }

        result = await planner_node(state, llm=mock_llm)

        assert result["next_action"] == "respond"
        assert "error" in result["final_answer"].lower()

    @pytest.mark.asyncio
    async def test_executor_handles_tool_error(self):
        """Test executor handles tool errors gracefully."""
        from airbeeps.agents.graph.nodes.executor import executor_node

        async def failing_executor(tool_name: str, tool_input: dict):
            raise Exception("Tool execution failed")

        state = {
            "pending_tool_calls": [{"tool": "test", "input": {}}],
            "tools_used": [],
            "messages": [],
        }

        result = await executor_node(state, tool_executor=failing_executor)

        assert result["next_action"] == "reflect"
        assert len(result["tools_used"]) == 1
        assert result["tools_used"][0]["success"] is False
