"""
Multi-Agent Execution Engine.

This module provides an execution engine that leverages multi-agent
collaboration with specialist agents for complex tasks.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.models import AgentCollaborationLog, CollaborationStatusEnum
from airbeeps.assistants.models import Assistant

from .graph_executor import get_agent_executor
from .specialist import (
    AgentCollaborationConfig,
    AgentRouter,
    CollaborationResult,
    MultiAgentOrchestrator,
    SpecialistType,
)

logger = logging.getLogger(__name__)


class MultiAgentEngine:
    """
    Multi-agent execution engine.

    This engine routes requests to specialist agents and orchestrates
    collaboration between them for complex tasks.
    """

    def __init__(
        self,
        assistants: dict[SpecialistType, Assistant],
        session: AsyncSession | None = None,
        user: Any | None = None,
        config: AgentCollaborationConfig | None = None,
    ):
        """
        Initialize the multi-agent engine.

        Args:
            assistants: Mapping of specialist types to assistant configurations
            session: Database session
            user: Current user
            config: Collaboration configuration
        """
        self.assistants = assistants
        self.session = session
        self.user = user
        self.config = config or AgentCollaborationConfig()

        # Create router
        self.router = AgentRouter(
            llm=None,  # Will be set during initialization
            use_llm_classification=False,  # Start with keyword-based
        )

        self.orchestrator: MultiAgentOrchestrator | None = None
        self._initialized = False

    async def initialize(self):
        """Initialize the engine and create orchestrator"""
        if self._initialized:
            return

        # Create executor factory
        async def create_executor(assistant, session, user):
            return await get_agent_executor(
                assistant=assistant,
                session=session,
                user=user,
                use_langgraph=True,
            )

        # Create orchestrator
        self.orchestrator = MultiAgentOrchestrator(
            router=self.router,
            executor_factory=create_executor,
            config=self.config,
            session=self.session,
        )

        self._initialized = True
        logger.info(
            f"MultiAgentEngine initialized with {len(self.assistants)} specialists: "
            f"{[s.value for s in self.assistants.keys()]}"
        )

    async def execute(
        self,
        user_input: str,
        conversation_id: UUID | None = None,
        chat_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a task with multi-agent collaboration.

        Args:
            user_input: The user's request
            conversation_id: Optional conversation ID
            chat_history: Previous conversation history

        Returns:
            Dict with output, collaboration details, etc.
        """
        if not self._initialized:
            await self.initialize()

        # Execute collaboration
        result = await self.orchestrator.execute(
            user_input=user_input,
            conversation_id=conversation_id,
            user=self.user,
            assistants=self.assistants,
            chat_history=chat_history,
        )

        # Log collaboration if session available
        if self.session:
            await self._log_collaboration(user_input, result, conversation_id)

        return {
            "output": result.final_output,
            "success": result.success,
            "agent_chain": [s.value for s in result.agent_chain],
            "total_iterations": result.total_iterations,
            "total_cost_usd": result.total_cost_usd,
            "total_duration_ms": result.total_duration_ms,
            "steps": [
                {
                    "specialist": step.specialist_type.value,
                    "output": step.output[:500]
                    if len(step.output) > 500
                    else step.output,
                    "iterations": step.iterations,
                    "cost_usd": step.cost_usd,
                    "duration_ms": step.duration_ms,
                }
                for step in result.steps
            ],
            "error": result.error,
            "error_type": result.error_type,
        }

    async def stream_execute(
        self,
        user_input: str,
        conversation_id: UUID | None = None,
        chat_history: list[dict] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream execute with multi-agent collaboration.

        Yields events for each phase of collaboration.
        """
        if not self._initialized:
            await self.initialize()

        async for event in self.orchestrator.stream_execute(
            user_input=user_input,
            conversation_id=conversation_id,
            user=self.user,
            assistants=self.assistants,
            chat_history=chat_history,
        ):
            yield event

    async def _log_collaboration(
        self,
        user_input: str,
        result: CollaborationResult,
        conversation_id: UUID | None,
    ):
        """Log collaboration to database"""
        try:
            # Determine status
            if result.success:
                status = CollaborationStatusEnum.COMPLETED
            elif result.error_type == "LOOP_DETECTED":
                status = CollaborationStatusEnum.LOOP_DETECTED
            elif result.error_type == "BUDGET_EXCEEDED":
                status = CollaborationStatusEnum.BUDGET_EXCEEDED
            else:
                status = CollaborationStatusEnum.FAILED

            # Get initial assistant ID
            initial_assistant_id = None
            if result.agent_chain:
                first_specialist = result.agent_chain[0]
                if first_specialist in self.assistants:
                    initial_assistant_id = self.assistants[first_specialist].id

            log = AgentCollaborationLog(
                conversation_id=conversation_id,
                user_id=self.user.id if self.user else None,
                initial_assistant_id=initial_assistant_id,
                user_input=user_input,
                final_output=result.final_output,
                status=status,
                agent_chain=[s.value for s in result.agent_chain],
                steps=[
                    {
                        "step": step.step_number,
                        "specialist": step.specialist_type.value,
                        "assistant_id": str(step.specialist_id)
                        if step.specialist_id
                        else None,
                        "input_context": step.input_context,
                        "output": step.output,
                        "iterations": step.iterations,
                        "cost_usd": step.cost_usd,
                        "duration_ms": step.duration_ms,
                        "handoff_requested": step.handoff_requested.value
                        if step.handoff_requested
                        else None,
                        "timestamp": step.timestamp.isoformat(),
                    }
                    for step in result.steps
                ],
                total_iterations=result.total_iterations,
                total_cost_usd=result.total_cost_usd,
                total_duration_ms=result.total_duration_ms,
                handoff_count=len(result.agent_chain) - 1 if result.agent_chain else 0,
                error_message=result.error,
                error_type=result.error_type,
                completed_at=datetime.utcnow(),
            )

            self.session.add(log)
            await self.session.commit()

            logger.debug(f"Logged collaboration: {log.id}")

        except Exception as e:
            logger.error(f"Failed to log collaboration: {e}")


async def get_multiagent_executor(
    assistants: dict[SpecialistType, Assistant],
    session: AsyncSession | None = None,
    user: Any | None = None,
    config: AgentCollaborationConfig | None = None,
) -> MultiAgentEngine:
    """
    Factory function to create a multi-agent executor.

    Args:
        assistants: Mapping of specialist types to assistant configurations
        session: Database session
        user: Current user
        config: Collaboration configuration

    Returns:
        Initialized MultiAgentEngine
    """
    engine = MultiAgentEngine(
        assistants=assistants,
        session=session,
        user=user,
        config=config,
    )
    await engine.initialize()
    return engine
