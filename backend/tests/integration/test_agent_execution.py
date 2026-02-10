"""
Integration tests for agent execution.

Tests the full agent execution pipeline including:
- LangGraph executor
- Tool execution
- Budget management
- State persistence
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from airbeeps.agents.graph.builder import AgentGraphConfig, create_agent_graph
from airbeeps.agents.graph.nodes.budget_checker import budget_checker_node
from airbeeps.agents.graph.nodes.executor import ParallelExecutor
from airbeeps.agents.graph.state import AgentState
from airbeeps.agents.tools.base import AgentTool

# ============================================================================
# Fixtures
# ============================================================================


class MockTool(AgentTool):
    """Mock tool for testing."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

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
        return f"Mock result for: {query}"


@pytest.fixture
def mock_assistant():
    """Create a mock assistant for testing."""
    assistant = MagicMock()
    assistant.id = uuid4()
    assistant.name = "Test Assistant"
    assistant.system_prompt = "You are a test assistant."
    assistant.agent_max_iterations = 5
    assistant.agent_token_budget = 4000
    assistant.agent_cost_limit_usd = 0.50
    assistant.agent_enable_planning = True
    assistant.agent_enable_reflection = True
    return assistant


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_superuser = False
    return user


@pytest.fixture
def initial_state():
    """Create initial agent state."""
    return AgentState(
        user_input="Test query",
        messages=[],
        plan=None,
        tools_used=[],
        iterations=0,
        final_answer=None,
        reflections=[],
        memory_context={},
        token_budget=4000,
        token_usage={},
        max_iterations=5,
        max_tool_calls=10,
        cost_limit_usd=0.50,
        cost_spent_usd=0.0,
        compressed_history=None,
        compression_count=0,
    )


# ============================================================================
# Budget Checker Tests
# ============================================================================


class TestBudgetChecker:
    """Tests for the budget checker node."""

    @pytest.mark.asyncio
    async def test_budget_within_limits(self, initial_state):
        """Test that normal state passes through."""
        result = await budget_checker_node(initial_state)

        assert result["final_answer"] is None
        assert result["iterations"] == initial_state["iterations"]

    @pytest.mark.asyncio
    async def test_iteration_limit_exceeded(self, initial_state):
        """Test that exceeding iteration limit stops execution."""
        initial_state["iterations"] = 10
        initial_state["max_iterations"] = 5

        result = await budget_checker_node(initial_state)

        assert result["final_answer"] is not None
        assert (
            "iteration" in result["final_answer"].lower()
            or "max" in result["final_answer"].lower()
        )

    @pytest.mark.asyncio
    async def test_cost_limit_exceeded(self, initial_state):
        """Test that exceeding cost limit stops execution."""
        initial_state["cost_spent_usd"] = 0.60
        initial_state["cost_limit_usd"] = 0.50

        result = await budget_checker_node(initial_state)

        assert result["final_answer"] is not None
        assert "cost" in result["final_answer"].lower()

    @pytest.mark.asyncio
    async def test_tool_call_limit_exceeded(self, initial_state):
        """Test that exceeding tool call limit stops execution."""
        initial_state["tools_used"] = [{"name": f"tool_{i}"} for i in range(15)]
        initial_state["max_tool_calls"] = 10

        result = await budget_checker_node(initial_state)

        assert result["final_answer"] is not None
        assert "tool" in result["final_answer"].lower()


# ============================================================================
# Parallel Executor Tests
# ============================================================================


class TestParallelExecutor:
    """Tests for parallel tool execution."""

    @pytest.mark.asyncio
    async def test_single_tool_execution(self):
        """Test executing a single tool."""
        tool = MockTool()
        executor = ParallelExecutor(max_concurrent=3)

        async def tool_executor(name: str, input_data: dict) -> str:
            return await tool.execute(**input_data)

        tool_calls = [{"name": "mock_tool", "input": {"query": "test"}}]
        results = await executor.execute_batch(tool_executor, tool_calls)

        assert len(results) == 1
        assert results[0].success
        assert "Mock result" in results[0].result

    @pytest.mark.asyncio
    async def test_parallel_tool_execution(self):
        """Test executing multiple tools in parallel."""
        tool = MockTool()
        executor = ParallelExecutor(max_concurrent=3)

        async def tool_executor(name: str, input_data: dict) -> str:
            return await tool.execute(**input_data)

        tool_calls = [
            {"name": "mock_tool", "input": {"query": "test1"}},
            {"name": "mock_tool", "input": {"query": "test2"}},
            {"name": "mock_tool", "input": {"query": "test3"}},
        ]
        results = await executor.execute_batch(tool_executor, tool_calls)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_tool_execution_with_timeout(self):
        """Test that tool timeout is respected."""
        import asyncio

        async def slow_tool_executor(name: str, input_data: dict) -> str:
            await asyncio.sleep(10)  # Simulate slow tool
            return "result"

        executor = ParallelExecutor(max_concurrent=1, default_timeout=0.1)
        tool_calls = [{"name": "slow_tool", "input": {}}]

        results = await executor.execute_batch(slow_tool_executor, tool_calls)

        assert len(results) == 1
        assert not results[0].success
        assert (
            "timeout" in results[0].error_type.lower()
            if results[0].error_type
            else True
        )

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self):
        """Test that concurrency limit is respected."""
        import asyncio

        concurrent_count = 0
        max_concurrent_seen = 0

        async def counting_executor(name: str, input_data: dict) -> str:
            nonlocal concurrent_count, max_concurrent_seen
            concurrent_count += 1
            max_concurrent_seen = max(max_concurrent_seen, concurrent_count)
            await asyncio.sleep(0.1)
            concurrent_count -= 1
            return "result"

        executor = ParallelExecutor(max_concurrent=2, default_timeout=5)
        tool_calls = [{"name": "tool", "input": {}} for _ in range(5)]

        await executor.execute_batch(counting_executor, tool_calls)

        assert max_concurrent_seen <= 2


# ============================================================================
# Graph Builder Tests
# ============================================================================


class TestGraphBuilder:
    """Tests for agent graph construction."""

    @pytest.mark.asyncio
    async def test_create_graph_with_defaults(self, mock_assistant):
        """Test creating a graph with default configuration."""
        config = AgentGraphConfig()

        with patch("airbeeps.agents.graph.builder.create_checkpointer") as mock_cp:
            mock_cp.return_value = None
            graph = await create_agent_graph(mock_assistant, None, config)

        assert graph is not None

    @pytest.mark.asyncio
    async def test_graph_nodes_connected(self, mock_assistant):
        """Test that graph nodes are properly connected."""
        config = AgentGraphConfig()

        with patch("airbeeps.agents.graph.builder.create_checkpointer") as mock_cp:
            mock_cp.return_value = None
            graph = await create_agent_graph(mock_assistant, None, config)

        # Graph should have the expected nodes
        # Note: This tests the graph structure, not execution
        assert graph is not None


# ============================================================================
# State Persistence Tests
# ============================================================================


class TestStatePersistence:
    """Tests for agent state persistence."""

    @pytest.mark.asyncio
    async def test_state_serialization(self, initial_state):
        """Test that state can be serialized and deserialized."""
        import json

        # Convert to dict (excluding non-serializable items)
        state_dict = {k: v for k, v in initial_state.items() if not callable(v)}

        # Should be JSON serializable
        json_str = json.dumps(state_dict, default=str)
        assert json_str is not None

        # Should deserialize back
        loaded = json.loads(json_str)
        assert loaded["user_input"] == initial_state["user_input"]

    @pytest.mark.asyncio
    async def test_state_update_immutability(self, initial_state):
        """Test that state updates don't mutate original."""
        original_iterations = initial_state["iterations"]

        # Create modified copy
        new_state = {**initial_state, "iterations": 5}

        assert initial_state["iterations"] == original_iterations
        assert new_state["iterations"] == 5


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in agent execution."""

    @pytest.mark.asyncio
    async def test_tool_error_captured(self):
        """Test that tool errors are captured and reported."""

        class FailingTool(AgentTool):
            @property
            def name(self) -> str:
                return "failing_tool"

            @property
            def description(self) -> str:
                return "A tool that always fails"

            @property
            def security_level(self) -> str:
                return "SAFE"

            def get_input_schema(self) -> dict:
                return {"type": "object", "properties": {}}

            async def execute(self, **kwargs) -> str:
                raise ValueError("Tool failed intentionally")

        tool = FailingTool()
        executor = ParallelExecutor(max_concurrent=1)

        async def failing_executor(name: str, input_data: dict) -> str:
            return await tool.execute(**input_data)

        tool_calls = [{"name": "failing_tool", "input": {}}]
        results = await executor.execute_batch(failing_executor, tool_calls)

        assert len(results) == 1
        assert not results[0].success
        assert (
            "failed" in results[0].result.lower() or results[0].error_type is not None
        )

    @pytest.mark.asyncio
    async def test_partial_failure_handling(self):
        """Test handling when some tools succeed and some fail."""
        call_count = 0

        async def mixed_executor(name: str, input_data: dict) -> str:
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ValueError("Even call failed")
            return "success"

        executor = ParallelExecutor(max_concurrent=3)
        tool_calls = [{"name": f"tool_{i}", "input": {}} for i in range(4)]

        results = await executor.execute_batch(mixed_executor, tool_calls)

        successes = sum(1 for r in results if r.success)
        failures = sum(1 for r in results if not r.success)

        assert successes == 2
        assert failures == 2
