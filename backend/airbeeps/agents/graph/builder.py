"""
LangGraph Agent Builder.

Creates the agent execution graph with:
- Budget management
- Planning and reflection patterns
- State persistence
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, StateGraph

from .nodes.budget_checker import budget_checker_node
from .nodes.executor import executor_node
from .nodes.planner import planner_node
from .nodes.reflector import reflector_node
from .nodes.responder import responder_node
from .state import AgentStateDict, BudgetConfig

logger = logging.getLogger(__name__)


@dataclass
class AgentGraphConfig:
    """Configuration for the agent graph"""

    # Budget settings
    budget: BudgetConfig = field(default_factory=BudgetConfig)

    # Feature toggles
    enable_planning: bool = True
    enable_reflection: bool = True
    reflection_threshold: float = 7.0
    max_retries: int = 3

    # Parallel execution
    max_parallel_tools: int = 3
    tool_timeout_seconds: int = 30

    # Checkpointing
    enable_checkpointing: bool = False
    checkpoint_db_url: str | None = None

    # Memory service integration
    memory_service: Any = None
    assistant_id: str | None = None
    user_id: str | None = None
    embedding_model_id: str | None = None


async def create_agent_graph(
    llm: Any,
    tools: list[Any],
    tool_executor: Callable[[str, dict], Any],
    config: AgentGraphConfig | None = None,
    checkpointer: Any = None,
):
    """
    Create a LangGraph agent execution graph.

    The graph structure:

    [START] -> budget_checker -> planner -> executor -> reflector -> responder -> [END]
                    ^                                        |
                    |________________________________________|
                    (if more tools needed or retry)

    Args:
        llm: Language model instance
        tools: List of available tools
        tool_executor: Async function to execute tools
        config: Graph configuration
        checkpointer: Optional state checkpointer for persistence

    Returns:
        Compiled StateGraph
    """
    config = config or AgentGraphConfig()

    # Create the graph
    graph = StateGraph(AgentStateDict)

    # Create node functions with bound dependencies
    async def budget_node(state: dict) -> dict:
        return await budget_checker_node(state)

    async def plan_node(state: dict) -> dict:
        if config.enable_planning:
            return await planner_node(
                state,
                llm=llm,
                tools=tools,
                memory_service=config.memory_service,
                assistant_id=config.assistant_id,
                user_id=config.user_id,
                embedding_model_id=config.embedding_model_id,
            )
        # Skip planning - go directly to respond
        state["next_action"] = "respond"
        return state

    async def exec_node(state: dict) -> dict:
        return await executor_node(
            state,
            tool_executor=tool_executor,
            max_parallel=config.max_parallel_tools,
        )

    async def reflect_node(state: dict) -> dict:
        if config.enable_reflection:
            return await reflector_node(
                state,
                llm=llm,
                quality_threshold=config.reflection_threshold,
                max_retries=config.max_retries,
            )
        # Skip reflection - go to respond
        state["next_action"] = "respond"
        return state

    async def respond_node(state: dict) -> dict:
        return await responder_node(state, llm=llm)

    # Add nodes to graph
    graph.add_node("budget_checker", budget_node)
    graph.add_node("planner", plan_node)
    graph.add_node("executor", exec_node)
    graph.add_node("reflector", reflect_node)
    graph.add_node("responder", respond_node)

    # Set entry point
    graph.set_entry_point("budget_checker")

    # Add edges
    # From budget_checker: continue to planner or abort to responder
    graph.add_conditional_edges(
        "budget_checker",
        _route_from_budget,
        {
            "continue": "planner",
            "abort": "responder",
        },
    )

    # From planner: to executor (if tools needed) or responder (if direct answer)
    graph.add_conditional_edges(
        "planner",
        _route_from_planner,
        {
            "execute": "executor",
            "respond": "responder",
        },
    )

    # From executor: always to reflector
    graph.add_edge("executor", "reflector")

    # From reflector: back to budget_checker (loop) or to responder
    graph.add_conditional_edges(
        "reflector",
        _route_from_reflector,
        {
            "continue": "budget_checker",
            "respond": "responder",
        },
    )

    # From responder: end
    graph.add_edge("responder", END)

    # Compile the graph
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


def _route_from_budget(state: dict) -> str:
    """Route from budget checker"""
    if state.get("next_action") == "abort":
        return "abort"
    return "continue"


def _route_from_planner(state: dict) -> str:
    """Route from planner"""
    if state.get("pending_tool_calls"):
        return "execute"
    return "respond"


def _route_from_reflector(state: dict) -> str:
    """Route from reflector"""
    next_action = state.get("next_action", "respond")

    if next_action in ["execute", "plan"]:
        return "continue"
    return "respond"


async def create_checkpointer(db_url: str):
    """
    Create a PostgreSQL checkpointer for state persistence.

    This allows conversations to be resumed even after server restart.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
        await checkpointer.setup()
        return checkpointer
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-postgres not installed, state persistence disabled"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to create checkpointer: {e}")
        return None


class AgentGraphRunner:
    """
    Helper class for running the agent graph.

    Provides convenience methods for execution and streaming.
    """

    def __init__(
        self,
        llm: Any,
        tools: list[Any],
        tool_executor: Callable[[str, dict], Any],
        config: AgentGraphConfig | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.tool_executor = tool_executor
        self.config = config or AgentGraphConfig()
        self._graph = None

    async def initialize(self, checkpointer: Any = None):
        """Initialize the graph"""
        self._graph = await create_agent_graph(
            llm=self.llm,
            tools=self.tools,
            tool_executor=self.tool_executor,
            config=self.config,
            checkpointer=checkpointer,
        )

    async def run(
        self,
        user_input: str,
        chat_history: list[dict] | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run the agent graph to completion.

        Args:
            user_input: User's input message
            chat_history: Previous messages in the conversation
            thread_id: Optional thread ID for state persistence

        Returns:
            Final state with output
        """
        if not self._graph:
            await self.initialize()

        # Build initial state
        initial_state = self._build_initial_state(user_input, chat_history)

        # Run config
        config = {}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}

        # Execute graph
        final_state = await self._graph.ainvoke(initial_state, config)

        return {
            "output": final_state.get("final_answer", ""),
            "iterations": final_state.get("iterations", 0),
            "token_usage": final_state.get("token_usage", {}),
            "cost_spent": final_state.get("cost_spent_usd", 0.0),
            "tools_used": final_state.get("tools_used", []),
            "reflections": final_state.get("reflections", []),
        }

    async def stream(
        self,
        user_input: str,
        chat_history: list[dict] | None = None,
        thread_id: str | None = None,
    ):
        """
        Stream agent graph execution.

        Yields events for each node execution.
        """
        if not self._graph:
            await self.initialize()

        initial_state = self._build_initial_state(user_input, chat_history)

        config = {}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}

        async for event in self._graph.astream(initial_state, config):
            # Convert graph events to agent events
            for node_name, node_output in event.items():
                if node_name == "planner":
                    yield {
                        "type": "planning",
                        "data": {
                            "plan": node_output.get("plan", ""),
                            "tool_calls": node_output.get("pending_tool_calls", []),
                        },
                    }

                elif node_name == "executor":
                    for tool_result in node_output.get("tools_used", [])[
                        -1:
                    ]:  # Last result
                        yield {
                            "type": "tool_result",
                            "data": tool_result,
                        }

                elif node_name == "reflector":
                    yield {
                        "type": "reflection",
                        "data": {
                            "quality_score": node_output.get("quality_score"),
                            "reflection": node_output.get("reflections", [])[-1:],
                        },
                    }

                elif node_name == "responder":
                    yield {
                        "type": "final_answer",
                        "data": {
                            "answer": node_output.get("final_answer", ""),
                        },
                    }

                elif node_name == "budget_checker":
                    if node_output.get("abort_reason"):
                        yield {
                            "type": "budget_warning",
                            "data": {
                                "reason": node_output.get("abort_reason"),
                                "iterations": node_output.get("iterations"),
                                "cost_spent": node_output.get("cost_spent_usd"),
                            },
                        }

    def _build_initial_state(
        self,
        user_input: str,
        chat_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Build initial state for graph execution"""
        messages = []

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": user_input})

        return {
            "messages": messages,
            "user_input": user_input,
            "plan": None,
            "current_step": 0,
            "final_answer": None,
            "tools_used": [],
            "pending_tool_calls": [],
            "reflections": [],
            "quality_score": None,
            "memory_context": {},
            "token_budget": self.config.budget.token_budget,
            "token_usage": {},
            "max_iterations": self.config.budget.max_iterations,
            "iterations": 0,
            "max_tool_calls": self.config.budget.max_tool_calls,
            "cost_limit_usd": self.config.budget.cost_limit_usd,
            "cost_spent_usd": 0.0,
            "compressed_history": None,
            "compression_count": 0,
            "next_action": "plan",
            "abort_reason": None,
        }
