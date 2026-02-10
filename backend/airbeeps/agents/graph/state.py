"""
Agent State definition for LangGraph.

Defines the state structure that flows through the agent graph,
including budget management and state compression.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal

from langgraph.graph import add_messages


@dataclass
class BudgetConfig:
    """Configuration for agent budget limits"""

    token_budget: int = 8000  # Max tokens for this turn
    max_iterations: int = 10  # Max reasoning loops
    max_tool_calls: int = 20  # Max tool invocations
    cost_limit_usd: float = 0.50  # Abort if cost exceeds this
    max_parallel_tools: int = 3  # Limit concurrent tool calls
    compression_threshold: int = 10  # Compress after this many messages


@dataclass
class ToolCallRecord:
    """Record of a tool call"""

    tool_name: str
    tool_input: dict[str, Any]
    result: str
    success: bool
    duration_ms: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


class AgentState:
    """
    Agent state that flows through the LangGraph.

    This is a TypedDict-compatible class for LangGraph.
    """

    def __init__(
        self,
        # Core state
        messages: list | None = None,
        user_input: str = "",
        plan: str | None = None,
        current_step: int = 0,
        final_answer: str | None = None,
        # Tool execution
        tools_used: list[ToolCallRecord] | None = None,
        pending_tool_calls: list[dict] | None = None,
        # Reflection
        reflections: list[str] | None = None,
        quality_score: float | None = None,
        # Memory
        memory_context: dict | None = None,
        # Budget tracking
        token_budget: int = 8000,
        token_usage: dict[str, int] | None = None,
        max_iterations: int = 10,
        iterations: int = 0,
        max_tool_calls: int = 20,
        cost_limit_usd: float = 0.50,
        cost_spent_usd: float = 0.0,
        # State compression
        compressed_history: str | None = None,
        compression_count: int = 0,
        # Control flow
        next_action: Literal["plan", "execute", "reflect", "respond", "abort"] = "plan",
        abort_reason: str | None = None,
    ):
        self.messages = messages or []
        self.user_input = user_input
        self.plan = plan
        self.current_step = current_step
        self.final_answer = final_answer

        self.tools_used = tools_used or []
        self.pending_tool_calls = pending_tool_calls or []

        self.reflections = reflections or []
        self.quality_score = quality_score

        self.memory_context = memory_context or {}

        self.token_budget = token_budget
        self.token_usage = token_usage or {}
        self.max_iterations = max_iterations
        self.iterations = iterations
        self.max_tool_calls = max_tool_calls
        self.cost_limit_usd = cost_limit_usd
        self.cost_spent_usd = cost_spent_usd

        self.compressed_history = compressed_history
        self.compression_count = compression_count

        self.next_action = next_action
        self.abort_reason = abort_reason

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "messages": self.messages,
            "user_input": self.user_input,
            "plan": self.plan,
            "current_step": self.current_step,
            "final_answer": self.final_answer,
            "tools_used": [
                {
                    "tool_name": tc.tool_name,
                    "tool_input": tc.tool_input,
                    "result": tc.result,
                    "success": tc.success,
                    "duration_ms": tc.duration_ms,
                }
                for tc in self.tools_used
            ],
            "pending_tool_calls": self.pending_tool_calls,
            "reflections": self.reflections,
            "quality_score": self.quality_score,
            "memory_context": self.memory_context,
            "token_budget": self.token_budget,
            "token_usage": self.token_usage,
            "max_iterations": self.max_iterations,
            "iterations": self.iterations,
            "max_tool_calls": self.max_tool_calls,
            "cost_limit_usd": self.cost_limit_usd,
            "cost_spent_usd": self.cost_spent_usd,
            "compressed_history": self.compressed_history,
            "compression_count": self.compression_count,
            "next_action": self.next_action,
            "abort_reason": self.abort_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        """Create state from dictionary"""
        # Convert tool records
        tools_used = []
        for tc in data.get("tools_used", []):
            if isinstance(tc, dict):
                tools_used.append(
                    ToolCallRecord(
                        tool_name=tc["tool_name"],
                        tool_input=tc["tool_input"],
                        result=tc["result"],
                        success=tc["success"],
                        duration_ms=tc["duration_ms"],
                    )
                )
            else:
                tools_used.append(tc)

        return cls(
            messages=data.get("messages", []),
            user_input=data.get("user_input", ""),
            plan=data.get("plan"),
            current_step=data.get("current_step", 0),
            final_answer=data.get("final_answer"),
            tools_used=tools_used,
            pending_tool_calls=data.get("pending_tool_calls", []),
            reflections=data.get("reflections", []),
            quality_score=data.get("quality_score"),
            memory_context=data.get("memory_context", {}),
            token_budget=data.get("token_budget", 8000),
            token_usage=data.get("token_usage", {}),
            max_iterations=data.get("max_iterations", 10),
            iterations=data.get("iterations", 0),
            max_tool_calls=data.get("max_tool_calls", 20),
            cost_limit_usd=data.get("cost_limit_usd", 0.50),
            cost_spent_usd=data.get("cost_spent_usd", 0.0),
            compressed_history=data.get("compressed_history"),
            compression_count=data.get("compression_count", 0),
            next_action=data.get("next_action", "plan"),
            abort_reason=data.get("abort_reason"),
        )


# TypedDict version for LangGraph compatibility
from typing import TypedDict


class AgentStateDict(TypedDict, total=False):
    """TypedDict version for LangGraph"""

    # Core state
    messages: Annotated[list, add_messages]
    user_input: str
    plan: str | None
    current_step: int
    final_answer: str | None

    # Tool execution
    tools_used: list[dict]
    pending_tool_calls: list[dict]

    # Reflection
    reflections: list[str]
    quality_score: float | None

    # Memory
    memory_context: dict

    # Budget tracking
    token_budget: int
    token_usage: dict[str, int]
    max_iterations: int
    iterations: int
    max_tool_calls: int
    cost_limit_usd: float
    cost_spent_usd: float

    # State compression
    compressed_history: str | None
    compression_count: int

    # Control flow
    next_action: str
    abort_reason: str | None
