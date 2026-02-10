"""
LangGraph-based Agent Execution Engine.

This module provides an alternative execution engine that uses LangGraph
for orchestration, with support for:
- Budget management
- Planning and reflection
- State persistence
- Streaming execution
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.ai_models.client_factory import create_chat_model
from airbeeps.assistants.models import Assistant

from .descriptions import (
    get_action_description,
    get_observation_description,
    get_tool_display_name,
)
from .graph import AgentGraphConfig, create_agent_graph
from .graph.state import BudgetConfig
from .mcp.registry import mcp_registry
from .mcp.tools_adapter import MCPToolAdapter
from .security import ContentFilter, PermissionChecker
from .tools.base import AgentToolConfig
from .tools.knowledge_base import KnowledgeBaseTool
from .tools.registry import tool_registry
from .tracing.instrumentation import get_tracer
from .tracing.metrics import get_metrics_collector
from .tracing.pii_redactor import get_redactor

logger = logging.getLogger(__name__)


class LangGraphAgentEngine:
    """
    Agent execution engine using LangGraph for orchestration.

    This is an alternative to the basic ReAct-style executor,
    providing more sophisticated orchestration with:
    - Budget controls
    - Planning and reflection
    - State compression
    - Parallel tool execution
    """

    def __init__(
        self,
        assistant: Assistant,
        session: AsyncSession | None = None,
        system_prompt_override: str | None = None,
        user: Any | None = None,
        enable_security: bool = True,
    ):
        self.assistant = assistant
        self.session = session
        self.system_prompt_override = system_prompt_override
        self.user = user
        self.enable_security = enable_security

        # Components
        self.llm = None
        self.tools: list[Any] = []
        self.graph = None

        # Security
        self.permission_checker = PermissionChecker() if enable_security else None
        self.content_filter = ContentFilter() if enable_security else None

        # Build config from assistant settings
        self.graph_config = self._build_graph_config()

    def _build_graph_config(self) -> AgentGraphConfig:
        """Build graph config from assistant settings"""
        import os

        # Get user_id if available
        user_id = str(getattr(self.user, "id", "")) if self.user else None

        # Check for checkpointing config
        enable_checkpointing = getattr(
            self.assistant, "agent_enable_checkpointing", False
        )
        checkpoint_db_url = os.environ.get("DATABASE_URL") or os.environ.get(
            "POSTGRES_URL"
        )

        # Can also be set via env var override
        if (
            os.environ.get("AIRBEEPS_ENABLE_LANGGRAPH_CHECKPOINTING", "").lower()
            == "true"
        ):
            enable_checkpointing = True

        return AgentGraphConfig(
            budget=BudgetConfig(
                token_budget=getattr(self.assistant, "agent_token_budget", 8000),
                max_iterations=self.assistant.agent_max_iterations or 10,
                max_tool_calls=getattr(self.assistant, "agent_max_tool_calls", 20),
                cost_limit_usd=getattr(self.assistant, "agent_cost_limit_usd", 0.50),
                max_parallel_tools=getattr(
                    self.assistant, "agent_max_parallel_tools", 3
                ),
            ),
            enable_planning=getattr(self.assistant, "agent_enable_planning", True),
            enable_reflection=getattr(self.assistant, "agent_enable_reflection", True),
            reflection_threshold=getattr(
                self.assistant, "agent_reflection_threshold", 7.0
            ),
            max_parallel_tools=getattr(self.assistant, "agent_max_parallel_tools", 3),
            # Checkpointing for state persistence
            enable_checkpointing=enable_checkpointing,
            checkpoint_db_url=checkpoint_db_url,
            # Memory service will be set during initialization if available
            memory_service=None,  # Set in initialize()
            assistant_id=str(self.assistant.id),
            user_id=user_id,
            embedding_model_id=getattr(self.assistant, "embedding_model_id", None),
        )

    async def initialize(self):
        """Initialize the engine"""
        self.llm = self._create_llm()
        await self._load_tools()

        # Try to load memory service if available
        await self._load_memory_service()

        await self._build_graph()

    async def _load_memory_service(self):
        """Load memory service for context retrieval during planning"""
        try:
            from .memory.service import MemoryService

            if self.session:
                memory_service = MemoryService(self.session)
                self.graph_config.memory_service = memory_service
                logger.debug("Memory service loaded for LangGraph planning")
        except ImportError:
            logger.debug("Memory service not available")
        except Exception as e:
            logger.warning(f"Failed to load memory service: {e}")

    def _create_llm(self):
        """Create LLM client"""
        model = self.assistant.model
        provider = model.provider

        return create_chat_model(
            provider=provider,
            model_name=model.name,
            temperature=self.assistant.temperature,
            **self.assistant.config,
        )

    async def _load_tools(self):
        """Load all tools (local and MCP)"""
        # Load local tools
        for tool_name in self.assistant.agent_enabled_tools:
            try:
                tool_config = AgentToolConfig(
                    enabled=True,
                    parameters=self.assistant.agent_tool_config.get(tool_name, {}),
                )

                if tool_name in ["knowledge_base_query", "knowledge_base_search"]:
                    tool_config.parameters["knowledge_base_ids"] = [
                        str(kb_id) for kb_id in self.assistant.knowledge_base_ids
                    ]

                    if tool_name == "knowledge_base_query":
                        tool = KnowledgeBaseTool(
                            config=tool_config, session=self.session
                        )
                    else:
                        from .tools.knowledge_base import KnowledgeBaseSearchTool

                        tool = KnowledgeBaseSearchTool(
                            config=tool_config, session=self.session
                        )
                else:
                    tool = tool_registry.get_tool(tool_name, tool_config)

                self.tools.append(tool)
                logger.info(f"Loaded tool: {tool_name}")

            except Exception as e:
                logger.error(f"Failed to load tool {tool_name}: {e}")

        # Load MCP tools
        try:
            for mcp_server in self.assistant.mcp_servers:
                if not mcp_server.is_active:
                    continue

                try:
                    if not mcp_registry.is_registered(mcp_server.name):
                        await mcp_registry.register_server(mcp_server)

                    client = await mcp_registry.get_server(mcp_server.name)
                    mcp_tools = await client.list_tools()

                    for tool_info in mcp_tools:
                        adapter = MCPToolAdapter(mcp_client=client, tool_info=tool_info)
                        self.tools.append(adapter)
                        logger.info(f"Loaded MCP tool: {tool_info['name']}")

                except Exception as e:
                    logger.error(
                        f"Failed to load MCP tools from {mcp_server.name}: {e}"
                    )

        except Exception:
            # MCP servers relationship not loaded
            pass

    async def _build_graph(self):
        """Build the LangGraph execution graph with optional checkpointing"""
        checkpointer = None

        # Initialize checkpointer if enabled and DB URL is available
        if (
            self.graph_config.enable_checkpointing
            and self.graph_config.checkpoint_db_url
        ):
            try:
                from .graph import create_checkpointer

                checkpointer = await create_checkpointer(
                    self.graph_config.checkpoint_db_url
                )
                if checkpointer:
                    logger.info(
                        "LangGraph checkpointer initialized for state persistence"
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize checkpointer: {e}")

        self.graph = await create_agent_graph(
            llm=self.llm,
            tools=self.tools,
            tool_executor=self._execute_tool,
            config=self.graph_config,
            checkpointer=checkpointer,
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool with security layer and tracing"""
        import time

        tracer = get_tracer()
        metrics = get_metrics_collector()
        redactor = get_redactor()

        with tracer.start_as_current_span(f"tool_{tool_name}") as span:
            start_time = time.time()

            span.set_attribute("tool.name", tool_name)
            span.set_attribute("agent.assistant_id", str(self.assistant.id))
            if self.user:
                span.set_attribute("agent.user_id", str(getattr(self.user, "id", "")))

            # Redacted input for tracing
            redacted_input = redactor.redact_dict(tool_input)
            span.set_attribute("tool.input", str(redacted_input)[:500])

            # Find tool
            tool = None
            for t in self.tools:
                if t.name == tool_name:
                    tool = t
                    break

            if not tool:
                span.set_attribute("tool.success", False)
                span.set_attribute("tool.error", "Tool not found")
                metrics.record_tool_call(tool_name, success=False, latency_ms=0)
                return f"Error: Tool '{tool_name}' not found"

            # Permission check
            if self.enable_security and self.permission_checker:
                perm_result = await self.permission_checker.can_use_tool(
                    self.user, tool_name, check_quota=True
                )
                if not perm_result.allowed:
                    span.set_attribute("tool.success", False)
                    span.set_attribute(
                        "tool.error", f"Permission denied: {perm_result.reason}"
                    )
                    metrics.record_tool_call(tool_name, success=False, latency_ms=0)
                    return f"Error: {perm_result.reason}"

            # Content filter
            if self.enable_security and self.content_filter:
                filter_result = await self.content_filter.filter_input(
                    tool_name, tool_input
                )
                if filter_result.action.value == "block":
                    span.set_attribute("tool.success", False)
                    span.set_attribute("tool.error", "Input blocked by filter")
                    metrics.record_tool_call(tool_name, success=False, latency_ms=0)
                    return f"Error: Input blocked - {', '.join(filter_result.warnings)}"
                tool_input = filter_result.modified_content or tool_input

            try:
                result = await tool.execute(**tool_input)

                # Output filter
                if self.enable_security and self.content_filter:
                    output_result = await self.content_filter.filter_output(
                        tool_name, result
                    )
                    result = output_result.modified_content or str(result)

                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("tool.success", True)
                span.set_attribute("tool.latency_ms", latency_ms)

                # Redacted output for tracing
                redacted_output = redactor.redact(str(result))
                span.set_attribute("tool.output_preview", redacted_output[:500])

                # Record metrics
                metrics.record_tool_call(
                    tool_name,
                    success=True,
                    latency_ms=latency_ms,
                    assistant_id=str(self.assistant.id),
                )

                return str(result)

            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("tool.success", False)
                span.set_attribute("tool.error", str(e))
                span.set_attribute("tool.latency_ms", latency_ms)
                span.record_exception(e)

                metrics.record_tool_call(
                    tool_name,
                    success=False,
                    latency_ms=latency_ms,
                    assistant_id=str(self.assistant.id),
                )

                logger.error(f"Tool execution error for {tool_name}: {e}")
                return f"Error: {e}"

    async def execute(
        self,
        user_input: str,
        conversation_id: Any | None = None,
        chat_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Execute agent task using LangGraph.

        Returns:
            Dict with output, iterations, token_usage, cost_spent, etc.
        """
        import time

        tracer = get_tracer()
        metrics = get_metrics_collector()
        redactor = get_redactor()

        with tracer.start_as_current_span("agent_execution") as span:
            start_time = time.time()

            # Set context attributes
            span.set_attribute("agent.assistant_id", str(self.assistant.id))
            if self.user:
                span.set_attribute("agent.user_id", str(getattr(self.user, "id", "")))
            if conversation_id:
                span.set_attribute("agent.conversation_id", str(conversation_id))
            span.set_attribute("agent.input_length", len(user_input))

            # Redacted input preview
            redacted_input = redactor.redact(user_input)
            span.set_attribute("agent.input_preview", redacted_input[:500])

            if not self.graph:
                await self.initialize()

            # Build initial state
            messages = []
            if chat_history:
                messages.extend(chat_history)
            messages.append({"role": "user", "content": user_input})

            initial_state = {
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
                "token_budget": self.graph_config.budget.token_budget,
                "token_usage": {},
                "max_iterations": self.graph_config.budget.max_iterations,
                "iterations": 0,
                "max_tool_calls": self.graph_config.budget.max_tool_calls,
                "cost_limit_usd": self.graph_config.budget.cost_limit_usd,
                "cost_spent_usd": 0.0,
                "compressed_history": None,
                "compression_count": 0,
                "next_action": "plan",
                "abort_reason": None,
            }

            # Execute graph
            config = {}
            if conversation_id:
                config["configurable"] = {"thread_id": str(conversation_id)}

            try:
                final_state = await self.graph.ainvoke(initial_state, config)

                latency_ms = (time.time() - start_time) * 1000
                iterations = final_state.get("iterations", 0)
                cost_spent = final_state.get("cost_spent_usd", 0.0)
                token_usage = final_state.get("token_usage", {})
                total_tokens = sum(token_usage.values()) if token_usage else 0

                # Set success attributes
                span.set_attribute("agent.success", True)
                span.set_attribute("agent.latency_ms", latency_ms)
                span.set_attribute("agent.iterations", iterations)
                span.set_attribute("agent.cost_usd", cost_spent)
                span.set_attribute("agent.tokens_used", total_tokens)
                span.set_attribute(
                    "agent.tools_used_count", len(final_state.get("tools_used", []))
                )

                # Redacted output preview
                output = final_state.get("final_answer", "")
                redacted_output = redactor.redact(output)
                span.set_attribute("agent.output_preview", redacted_output[:500])

                # Record metrics
                metrics.record_agent_execution(
                    success=True,
                    latency_ms=latency_ms,
                    iterations=iterations,
                    cost_usd=cost_spent,
                    tokens_used=total_tokens,
                    assistant_id=str(self.assistant.id),
                )

                return {
                    "output": output,
                    "iterations": iterations,
                    "token_usage": token_usage,
                    "cost_spent": cost_spent,
                    "tools_used": final_state.get("tools_used", []),
                }

            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("agent.success", False)
                span.set_attribute("agent.latency_ms", latency_ms)
                span.set_attribute("agent.error", str(e))
                span.record_exception(e)

                metrics.record_agent_execution(
                    success=False,
                    latency_ms=latency_ms,
                    iterations=0,
                    assistant_id=str(self.assistant.id),
                )

                raise

    async def stream_execute(
        self,
        user_input: str,
        conversation_id: Any | None = None,
        chat_history: list[dict] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream execute agent task.

        Yields events for each phase of execution.
        """
        if not self.graph:
            await self.initialize()

        # Build initial state
        messages = []
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": user_input})

        initial_state = {
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
            "token_budget": self.graph_config.budget.token_budget,
            "token_usage": {},
            "max_iterations": self.graph_config.budget.max_iterations,
            "iterations": 0,
            "max_tool_calls": self.graph_config.budget.max_tool_calls,
            "cost_limit_usd": self.graph_config.budget.cost_limit_usd,
            "cost_spent_usd": 0.0,
            "compressed_history": None,
            "compression_count": 0,
            "next_action": "plan",
            "abort_reason": None,
        }

        config = {}
        if conversation_id:
            config["configurable"] = {"thread_id": str(conversation_id)}

        # Track previous state for diff
        last_tools_count = 0
        last_reflections_count = 0

        async for event in self.graph.astream(initial_state, config):
            for node_name, node_output in event.items():
                # Budget warnings
                if node_name == "budget_checker":
                    if node_output.get("abort_reason"):
                        yield {
                            "type": "budget_warning",
                            "data": {
                                "reason": node_output.get("abort_reason"),
                                "iterations": node_output.get("iterations"),
                                "cost_spent": node_output.get("cost_spent_usd"),
                            },
                        }

                # Planning phase
                elif node_name == "planner":
                    plan = node_output.get("plan", "")
                    pending_calls = node_output.get("pending_tool_calls", [])

                    if plan:
                        yield {
                            "type": "planning",
                            "data": {
                                "plan": plan,
                                "tool_calls_planned": len(pending_calls),
                            },
                        }

                # Tool execution
                elif node_name == "executor":
                    tools_used = node_output.get("tools_used", [])
                    new_tools = tools_used[last_tools_count:]
                    last_tools_count = len(tools_used)

                    for tool_record in new_tools:
                        tool_name = tool_record.get("tool_name", "")
                        tool_input = tool_record.get("tool_input", {})
                        result = tool_record.get("result", "")
                        success = tool_record.get("success", True)

                        # Yield action
                        yield {
                            "type": "agent_action",
                            "data": {
                                "tool": tool_name,
                                "tool_display_name": get_tool_display_name(tool_name),
                                "input": tool_input,
                                "description": get_action_description(
                                    tool_name, tool_input
                                ),
                            },
                        }

                        # Yield observation
                        yield {
                            "type": "agent_observation",
                            "data": {
                                "tool": tool_name,
                                "tool_display_name": get_tool_display_name(tool_name),
                                "observation": result,
                                "success": success,
                                "description": get_observation_description(
                                    tool_name, result
                                ),
                            },
                        }

                # Reflection
                elif node_name == "reflector":
                    reflections = node_output.get("reflections", [])
                    new_reflections = reflections[last_reflections_count:]
                    last_reflections_count = len(reflections)

                    quality_score = node_output.get("quality_score")

                    if new_reflections:
                        yield {
                            "type": "reflection",
                            "data": {
                                "reflection": new_reflections[-1],
                                "quality_score": quality_score,
                            },
                        }

                # Final response
                elif node_name == "responder":
                    final_answer = node_output.get("final_answer", "")

                    if final_answer:
                        # Simulate streaming for the final answer
                        chunk_size = 50
                        for i in range(0, len(final_answer), chunk_size):
                            yield {
                                "type": "content_chunk",
                                "data": {
                                    "content": final_answer[i : i + chunk_size],
                                    "is_final": i + chunk_size >= len(final_answer),
                                },
                            }

                        # Token usage
                        token_usage = node_output.get("token_usage", {})
                        if token_usage:
                            yield {
                                "type": "token_usage",
                                "data": {
                                    "input_tokens": sum(
                                        v
                                        for k, v in token_usage.items()
                                        if "input" in k or "planning" in k
                                    ),
                                    "output_tokens": sum(
                                        v
                                        for k, v in token_usage.items()
                                        if "output" in k or "response" in k
                                    ),
                                    "total_tokens": sum(token_usage.values()),
                                },
                            }


# Factory function to get the appropriate executor
async def get_agent_executor(
    assistant: Assistant,
    session: AsyncSession | None = None,
    user: Any | None = None,
    use_langgraph: bool = True,
):
    """
    Factory function to get the appropriate agent executor.

    Args:
        assistant: The assistant configuration
        session: Database session
        user: Current user
        use_langgraph: Whether to use LangGraph executor (default True)

    Returns:
        Initialized agent executor
    """
    if use_langgraph:
        executor = LangGraphAgentEngine(
            assistant=assistant,
            session=session,
            user=user,
        )
    else:
        # Use the original ReAct-style executor
        from .executor import AgentExecutionEngine

        executor = AgentExecutionEngine(
            assistant=assistant,
            session=session,
            user=user,
        )

    await executor.initialize()
    return executor
