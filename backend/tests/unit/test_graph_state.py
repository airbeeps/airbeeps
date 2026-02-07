"""
Unit tests for Agent State and Cost Estimation.

Tests for AgentState, BudgetConfig, ToolCallRecord, and cost estimation functions.
"""

from datetime import datetime

import pytest


class TestBudgetConfig:
    """Tests for BudgetConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        from airbeeps.agents.graph.state import BudgetConfig

        config = BudgetConfig()

        assert config.token_budget == 8000
        assert config.max_iterations == 10
        assert config.max_tool_calls == 20
        assert config.cost_limit_usd == 0.50
        assert config.max_parallel_tools == 3
        assert config.compression_threshold == 10

    def test_custom_values(self):
        """Should accept custom values."""
        from airbeeps.agents.graph.state import BudgetConfig

        config = BudgetConfig(
            token_budget=16000,
            max_iterations=20,
            cost_limit_usd=1.00,
        )

        assert config.token_budget == 16000
        assert config.max_iterations == 20
        assert config.cost_limit_usd == 1.00


class TestToolCallRecord:
    """Tests for ToolCallRecord dataclass."""

    def test_create_record(self):
        """Should create a tool call record."""
        from airbeeps.agents.graph.state import ToolCallRecord

        record = ToolCallRecord(
            tool_name="search",
            tool_input={"query": "test"},
            result="Found 5 results",
            success=True,
            duration_ms=250,
        )

        assert record.tool_name == "search"
        assert record.success is True
        assert record.duration_ms == 250
        assert isinstance(record.timestamp, datetime)

    def test_record_with_timestamp(self):
        """Should accept custom timestamp."""
        from airbeeps.agents.graph.state import ToolCallRecord

        custom_time = datetime(2026, 1, 30, 12, 0, 0)
        record = ToolCallRecord(
            tool_name="api",
            tool_input={},
            result="OK",
            success=True,
            duration_ms=100,
            timestamp=custom_time,
        )

        assert record.timestamp == custom_time


class TestAgentState:
    """Tests for AgentState class."""

    def test_default_initialization(self):
        """Should initialize with defaults."""
        from airbeeps.agents.graph.state import AgentState

        state = AgentState()

        assert state.messages == []
        assert state.user_input == ""
        assert state.plan is None
        assert state.iterations == 0
        assert state.cost_spent_usd == 0.0
        assert state.next_action == "plan"

    def test_custom_initialization(self):
        """Should accept custom values."""
        from airbeeps.agents.graph.state import AgentState

        state = AgentState(
            user_input="What is AI?",
            max_iterations=5,
            cost_limit_usd=0.25,
        )

        assert state.user_input == "What is AI?"
        assert state.max_iterations == 5
        assert state.cost_limit_usd == 0.25

    def test_to_dict(self):
        """Should convert to dictionary."""
        from airbeeps.agents.graph.state import AgentState, ToolCallRecord

        state = AgentState(
            user_input="test",
            plan="Search and respond",
            iterations=2,
            cost_spent_usd=0.05,
        )
        state.tools_used = [
            ToolCallRecord(
                tool_name="search",
                tool_input={"q": "test"},
                result="data",
                success=True,
                duration_ms=100,
            )
        ]

        data = state.to_dict()

        assert data["user_input"] == "test"
        assert data["plan"] == "Search and respond"
        assert data["iterations"] == 2
        assert len(data["tools_used"]) == 1
        assert data["tools_used"][0]["tool_name"] == "search"

    def test_from_dict(self):
        """Should create state from dictionary."""
        from airbeeps.agents.graph.state import AgentState

        data = {
            "user_input": "test query",
            "plan": "Execute plan",
            "iterations": 3,
            "cost_spent_usd": 0.10,
            "tools_used": [
                {
                    "tool_name": "api",
                    "tool_input": {},
                    "result": "OK",
                    "success": True,
                    "duration_ms": 50,
                }
            ],
            "messages": [{"role": "user", "content": "hi"}],
        }

        state = AgentState.from_dict(data)

        assert state.user_input == "test query"
        assert state.plan == "Execute plan"
        assert state.iterations == 3
        assert len(state.tools_used) == 1
        assert state.tools_used[0].tool_name == "api"

    def test_from_dict_minimal(self):
        """Should handle minimal dictionary."""
        from airbeeps.agents.graph.state import AgentState

        data = {}
        state = AgentState.from_dict(data)

        assert state.user_input == ""
        assert state.messages == []
        assert state.iterations == 0


class TestAgentStateDict:
    """Tests for AgentStateDict TypedDict."""

    def test_typed_dict_structure(self):
        """Should have correct type annotations."""
        from airbeeps.agents.graph.state import AgentStateDict

        # Verify the TypedDict has expected keys
        annotations = AgentStateDict.__annotations__

        assert "messages" in annotations
        assert "user_input" in annotations
        assert "plan" in annotations
        assert "tools_used" in annotations
        assert "cost_limit_usd" in annotations


class TestCostEstimator:
    """Tests for cost estimation functions."""

    def test_get_model_pricing_exact_match(self):
        """Should return exact match pricing."""
        from airbeeps.agents.graph.cost_estimator import get_model_pricing

        input_price, output_price = get_model_pricing("gpt-4o")

        assert input_price == 2.50
        assert output_price == 10.00

    def test_get_model_pricing_partial_match(self):
        """Should match partial model names."""
        from airbeeps.agents.graph.cost_estimator import get_model_pricing

        # Should match "claude-3-5-sonnet"
        input_price, output_price = get_model_pricing("claude-3-5-sonnet-20241022")

        assert input_price == 3.00
        assert output_price == 15.00

    def test_get_model_pricing_default(self):
        """Should return default for unknown models."""
        from airbeeps.agents.graph.cost_estimator import get_model_pricing

        input_price, output_price = get_model_pricing("unknown-model-xyz")

        assert input_price == 1.00
        assert output_price == 3.00

    def test_estimate_cost(self):
        """Should calculate cost correctly."""
        from airbeeps.agents.graph.cost_estimator import estimate_cost

        # GPT-4o: $2.50/1M input, $10.00/1M output
        cost = estimate_cost(1000, 500, "gpt-4o")

        # (1000/1M * 2.50) + (500/1M * 10.00) = 0.0025 + 0.005 = 0.0075
        assert abs(cost - 0.0075) < 0.0001

    def test_estimate_cost_large_tokens(self):
        """Should handle large token counts."""
        from airbeeps.agents.graph.cost_estimator import estimate_cost

        cost = estimate_cost(100000, 50000, "gpt-4o-mini")

        # (100000/1M * 0.15) + (50000/1M * 0.60) = 0.015 + 0.03 = 0.045
        assert abs(cost - 0.045) < 0.001

    def test_estimate_tokens_empty(self):
        """Should return 0 for empty text."""
        from airbeeps.agents.graph.cost_estimator import estimate_tokens

        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_estimate_tokens(self):
        """Should estimate tokens from text."""
        from airbeeps.agents.graph.cost_estimator import estimate_tokens

        # ~4 chars per token
        text = "A" * 100
        tokens = estimate_tokens(text)

        assert tokens == 25  # 100 / 4

    def test_estimate_message_tokens(self):
        """Should estimate tokens from messages."""
        from airbeeps.agents.graph.cost_estimator import estimate_message_tokens

        messages = [
            {"content": "Hello world"},  # 11 chars = ~2-3 tokens
            {"content": "How are you?"},  # 12 chars = ~3 tokens
        ]

        tokens = estimate_message_tokens(messages)
        assert tokens > 0

    def test_estimate_message_tokens_with_list_content(self):
        """Should handle list content in messages."""
        from airbeeps.agents.graph.cost_estimator import estimate_message_tokens

        messages = [
            {"content": [{"text": "Part 1"}, {"text": "Part 2"}]},
        ]

        tokens = estimate_message_tokens(messages)
        assert tokens > 0

    def test_estimate_remaining_budget(self):
        """Should calculate remaining budget correctly."""
        from airbeeps.agents.graph.cost_estimator import estimate_remaining_budget

        state = {
            "cost_spent_usd": 0.25,
            "cost_limit_usd": 0.50,
        }

        result = estimate_remaining_budget(state)

        assert result["remaining_usd"] == 0.25
        assert result["percentage_used"] == 50.0
        assert result["should_abort"] is False

    def test_estimate_remaining_budget_low(self):
        """Should indicate abort when budget critically low."""
        from airbeeps.agents.graph.cost_estimator import estimate_remaining_budget

        state = {
            "cost_spent_usd": 0.48,
            "cost_limit_usd": 0.50,
        }

        result = estimate_remaining_budget(state)

        assert abs(result["remaining_usd"] - 0.02) < 0.0001
        assert result["should_abort"] is True

    def test_estimate_tool_cost_with_api(self):
        """Should estimate cost for API tools."""
        from airbeeps.agents.graph.cost_estimator import estimate_tool_cost

        cost = estimate_tool_cost("web_search", {"query": "test"})
        assert cost == 0.001

    def test_estimate_tool_cost_internal(self):
        """Should return 0 for internal tools."""
        from airbeeps.agents.graph.cost_estimator import estimate_tool_cost

        cost = estimate_tool_cost("knowledge_base", {"query": "test"})
        assert cost == 0.0


class TestCostTracker:
    """Tests for CostTracker class."""

    def test_initialization(self):
        """Should initialize with defaults."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker()

        assert tracker.total_cost == 0.0
        assert tracker.llm_calls == 0
        assert tracker.tool_calls == 0

    def test_record_llm_call(self):
        """Should record LLM call and calculate cost."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker(model_name="gpt-4o-mini")
        cost = tracker.record_llm_call(1000, 500)

        assert cost > 0
        assert tracker.llm_calls == 1
        assert tracker.input_tokens == 1000
        assert tracker.output_tokens == 500

    def test_record_tool_call(self):
        """Should record tool call."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker()
        cost = tracker.record_tool_call("web_search", {"query": "test"})

        assert cost == 0.001
        assert tracker.tool_calls == 1

    def test_is_over_budget(self):
        """Should detect when over budget."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker(cost_limit=0.10)
        tracker.total_cost = 0.05

        assert tracker.is_over_budget() is False

        tracker.total_cost = 0.10
        assert tracker.is_over_budget() is True

    def test_get_remaining(self):
        """Should calculate remaining budget."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker(cost_limit=0.50)
        tracker.total_cost = 0.20

        assert tracker.get_remaining() == 0.30

    def test_get_remaining_over_budget(self):
        """Should return 0 when over budget."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker(cost_limit=0.10)
        tracker.total_cost = 0.15

        assert tracker.get_remaining() == 0

    def test_get_summary(self):
        """Should return complete summary."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker(model_name="gpt-4o", cost_limit=0.50)
        tracker.record_llm_call(1000, 500)
        tracker.record_tool_call("search", {})

        summary = tracker.get_summary()

        assert summary["llm_calls"] == 1
        assert summary["tool_calls"] == 1
        assert summary["cost_limit_usd"] == 0.50
        assert summary["is_over_budget"] is False
        assert "remaining_usd" in summary

    def test_multiple_calls_accumulate(self):
        """Should accumulate costs across multiple calls."""
        from airbeeps.agents.graph.cost_estimator import CostTracker

        tracker = CostTracker(model_name="gpt-4o-mini")

        tracker.record_llm_call(1000, 500)
        tracker.record_llm_call(2000, 1000)
        tracker.record_tool_call("web_search", {})

        assert tracker.llm_calls == 2
        assert tracker.tool_calls == 1
        assert tracker.input_tokens == 3000
        assert tracker.output_tokens == 1500
        assert tracker.total_cost > 0
