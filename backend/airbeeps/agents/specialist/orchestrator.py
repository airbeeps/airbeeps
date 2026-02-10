"""
Multi-Agent Orchestrator.

Orchestrates collaboration between specialist agents with:
- Loop detection to prevent infinite agent ping-pong
- Budget enforcement during handoffs
- Collaboration logging and tracing
"""

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from .router import AgentRouter
from .types import SpecialistType, get_specialist_config

logger = logging.getLogger(__name__)


@dataclass
class HandoffRequest:
    """Request to hand off to another specialist"""

    from_specialist: SpecialistType
    to_specialist: SpecialistType
    reason: str
    context: str  # Relevant context to pass to the next specialist
    partial_result: str | None = None  # Any partial work completed


@dataclass
class AgentCollaborationConfig:
    """Configuration for multi-agent collaboration"""

    max_handoffs: int = 3  # Maximum number of handoffs per task
    max_total_iterations: int = 15  # Maximum iterations across all agents
    cost_limit_usd: float = 1.00  # Total cost limit for collaboration
    cost_limit_per_handoff: float = 0.25  # Cost limit per specialist
    loop_detection_window: int = 4  # Window size for loop detection
    enable_parallel_specialists: bool = False  # Allow parallel execution (future)


@dataclass
class CollaborationStep:
    """Record of a single step in multi-agent collaboration"""

    step_number: int
    specialist_type: SpecialistType
    specialist_id: UUID | None
    input_context: str
    output: str
    iterations: int
    cost_usd: float
    duration_ms: float
    handoff_requested: SpecialistType | None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollaborationResult:
    """Result of multi-agent collaboration"""

    success: bool
    final_output: str
    steps: list[CollaborationStep] = field(default_factory=list)
    total_iterations: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0
    error: str | None = None
    error_type: str | None = (
        None  # "LOOP_DETECTED", "BUDGET_EXCEEDED", "MAX_HANDOFFS", etc.
    )
    agent_chain: list[SpecialistType] = field(default_factory=list)


class MultiAgentOrchestrator:
    """
    Orchestrates collaboration between specialist agents.

    Features:
    - Routes initial request to appropriate specialist
    - Handles handoffs between specialists
    - Detects and prevents loops
    - Enforces budgets across collaboration
    - Logs collaboration for analysis
    """

    def __init__(
        self,
        router: AgentRouter,
        executor_factory: Any,  # Callable to create agent executors
        config: AgentCollaborationConfig | None = None,
        session: Any | None = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            router: Agent router for classification
            executor_factory: Factory function to create agent executors
            config: Collaboration configuration
            session: Database session for logging
        """
        self.router = router
        self.executor_factory = executor_factory
        self.config = config or AgentCollaborationConfig()
        self.session = session

    async def execute(
        self,
        user_input: str,
        conversation_id: UUID | None = None,
        user: Any | None = None,
        assistants: dict[SpecialistType, Any] | None = None,
        chat_history: list[dict] | None = None,
    ) -> CollaborationResult:
        """
        Execute a task with multi-agent collaboration.

        Args:
            user_input: The user's request
            conversation_id: Optional conversation ID for persistence
            user: Current user for permissions
            assistants: Mapping of specialist types to assistant configs
            chat_history: Previous conversation history

        Returns:
            CollaborationResult with final output and collaboration details
        """
        start_time = time.time()

        # Initialize tracking
        agent_chain: list[SpecialistType] = []
        steps: list[CollaborationStep] = []
        total_iterations = 0
        total_cost = 0.0
        current_context = user_input

        # Route to initial specialist
        available_specialists = (
            list(assistants.keys()) if assistants else list(SpecialistType)
        )
        routing = await self.router.route(user_input, available_specialists)

        current_specialist = routing.specialist_type
        agent_chain.append(current_specialist)

        logger.info(
            f"Starting multi-agent collaboration: initial specialist={current_specialist.value}, "
            f"confidence={routing.confidence:.2f}"
        )

        handoff_count = 0

        while handoff_count <= self.config.max_handoffs:
            # Check for loops
            loop_detected = self._detect_loop(agent_chain)
            if loop_detected:
                logger.warning(f"Loop detected in agent chain: {agent_chain}")
                return CollaborationResult(
                    success=False,
                    final_output="I encountered a loop while trying to answer your question. "
                    "Let me provide what I have so far.",
                    steps=steps,
                    total_iterations=total_iterations,
                    total_cost_usd=total_cost,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    error="Loop detected in agent collaboration",
                    error_type="LOOP_DETECTED",
                    agent_chain=agent_chain,
                )

            # Check budget limits
            if total_cost >= self.config.cost_limit_usd:
                logger.warning(
                    f"Cost limit exceeded: {total_cost:.4f} >= {self.config.cost_limit_usd}"
                )
                return CollaborationResult(
                    success=False,
                    final_output="I've reached the cost limit for this request. "
                    "Here's what I found so far.",
                    steps=steps,
                    total_iterations=total_iterations,
                    total_cost_usd=total_cost,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    error="Cost limit exceeded",
                    error_type="BUDGET_EXCEEDED",
                    agent_chain=agent_chain,
                )

            if total_iterations >= self.config.max_total_iterations:
                logger.warning(f"Iteration limit exceeded: {total_iterations}")
                return CollaborationResult(
                    success=False,
                    final_output="I've reached the maximum number of steps for this request.",
                    steps=steps,
                    total_iterations=total_iterations,
                    total_cost_usd=total_cost,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    error="Max iterations exceeded",
                    error_type="MAX_ITERATIONS",
                    agent_chain=agent_chain,
                )

            # Get specialist configuration
            spec_config = get_specialist_config(current_specialist)
            cost_limit_for_step = min(
                spec_config.cost_limit_usd,
                self.config.cost_limit_per_handoff,
                self.config.cost_limit_usd - total_cost,
            )

            # Get assistant for this specialist
            assistant = assistants.get(current_specialist) if assistants else None

            if not assistant:
                logger.warning(
                    f"No assistant configured for {current_specialist.value}"
                )
                # Fall back to GENERAL if available
                if current_specialist != SpecialistType.GENERAL and assistants:
                    assistant = assistants.get(SpecialistType.GENERAL)
                    if assistant:
                        current_specialist = SpecialistType.GENERAL

            if not assistant:
                return CollaborationResult(
                    success=False,
                    final_output="I don't have the right specialist available for this task.",
                    steps=steps,
                    total_iterations=total_iterations,
                    total_cost_usd=total_cost,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    error=f"No assistant for specialist type: {current_specialist.value}",
                    error_type="NO_SPECIALIST",
                    agent_chain=agent_chain,
                )

            # Execute with current specialist
            step_start = time.time()

            try:
                executor = await self.executor_factory(
                    assistant=assistant,
                    session=self.session,
                    user=user,
                )

                # Build prompt with specialist context
                specialist_prompt = self._build_specialist_prompt(
                    user_input=current_context,
                    specialist_type=current_specialist,
                    previous_steps=steps,
                )

                result = await executor.execute(
                    user_input=specialist_prompt,
                    conversation_id=conversation_id,
                    chat_history=chat_history,
                )

                step_output = result.get("output", "")
                step_iterations = result.get("iterations", 0)
                step_cost = result.get("cost_spent", 0.0)
                step_duration = (time.time() - step_start) * 1000

            except Exception as e:
                logger.error(f"Specialist execution failed: {e}")
                step_output = f"Error during execution: {e!s}"
                step_iterations = 0
                step_cost = 0.0
                step_duration = (time.time() - step_start) * 1000

            # Check for handoff request
            handoff_requested = self.router.parse_handoff_request(step_output)

            # Record step
            step = CollaborationStep(
                step_number=len(steps) + 1,
                specialist_type=current_specialist,
                specialist_id=assistant.id if hasattr(assistant, "id") else None,
                input_context=current_context[:500],
                output=step_output,
                iterations=step_iterations,
                cost_usd=step_cost,
                duration_ms=step_duration,
                handoff_requested=handoff_requested,
            )
            steps.append(step)

            # Update totals
            total_iterations += step_iterations
            total_cost += step_cost

            # Handle handoff or complete
            if handoff_requested:
                # Validate handoff is allowed
                if handoff_requested not in spec_config.can_handoff_to:
                    logger.warning(
                        f"{current_specialist.value} cannot hand off to {handoff_requested.value}"
                    )
                    # Complete with current output
                    break

                # Check if we have the requested specialist
                if assistants and handoff_requested not in assistants:
                    logger.warning(
                        f"Requested specialist {handoff_requested.value} not available"
                    )
                    break

                # Prepare handoff context
                current_context = self._prepare_handoff_context(
                    original_input=user_input,
                    previous_output=step_output,
                    from_specialist=current_specialist,
                    to_specialist=handoff_requested,
                )

                current_specialist = handoff_requested
                agent_chain.append(current_specialist)
                handoff_count += 1

                logger.info(
                    f"Handoff #{handoff_count}: {agent_chain[-2].value} -> {current_specialist.value}"
                )
            else:
                # No handoff requested, task complete
                break

        # Compile final result
        final_output = steps[-1].output if steps else "Unable to process request"

        # Clean handoff markers from output
        final_output = self._clean_handoff_markers(final_output)

        return CollaborationResult(
            success=True,
            final_output=final_output,
            steps=steps,
            total_iterations=total_iterations,
            total_cost_usd=total_cost,
            total_duration_ms=(time.time() - start_time) * 1000,
            agent_chain=agent_chain,
        )

    async def stream_execute(
        self,
        user_input: str,
        conversation_id: UUID | None = None,
        user: Any | None = None,
        assistants: dict[SpecialistType, Any] | None = None,
        chat_history: list[dict] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream execute with multi-agent collaboration.

        Yields events for each phase of collaboration.
        """
        start_time = time.time()

        # Route to initial specialist
        available_specialists = (
            list(assistants.keys()) if assistants else list(SpecialistType)
        )
        routing = await self.router.route(user_input, available_specialists)

        current_specialist = routing.specialist_type
        agent_chain = [current_specialist]

        yield {
            "type": "routing",
            "data": {
                "specialist": current_specialist.value,
                "confidence": routing.confidence,
                "reasoning": routing.reasoning,
            },
        }

        handoff_count = 0
        current_context = user_input
        total_cost = 0.0

        while handoff_count <= self.config.max_handoffs:
            # Check for loops
            if self._detect_loop(agent_chain):
                yield {
                    "type": "error",
                    "data": {
                        "error": "LOOP_DETECTED",
                        "message": "Loop detected in agent collaboration",
                        "agent_chain": [s.value for s in agent_chain],
                    },
                }
                return

            # Get assistant
            assistant = assistants.get(current_specialist) if assistants else None
            if not assistant:
                yield {
                    "type": "error",
                    "data": {
                        "error": "NO_SPECIALIST",
                        "message": f"No assistant for {current_specialist.value}",
                    },
                }
                return

            # Signal start of specialist execution
            yield {
                "type": "specialist_start",
                "data": {
                    "specialist": current_specialist.value,
                    "specialist_name": get_specialist_config(current_specialist).name,
                    "step_number": handoff_count + 1,
                },
            }

            try:
                executor = await self.executor_factory(
                    assistant=assistant,
                    session=self.session,
                    user=user,
                )

                specialist_prompt = self._build_specialist_prompt(
                    user_input=current_context,
                    specialist_type=current_specialist,
                    previous_steps=[],
                )

                # Stream from executor
                step_output = ""
                async for event in executor.stream_execute(
                    user_input=specialist_prompt,
                    conversation_id=conversation_id,
                    chat_history=chat_history,
                ):
                    # Add specialist context to events
                    event["specialist"] = current_specialist.value

                    # Collect output for handoff detection
                    if event["type"] == "content_chunk":
                        step_output += event["data"].get("content", "")

                    yield event

                # Check for handoff after streaming complete
                handoff_requested = self.router.parse_handoff_request(step_output)

                if handoff_requested:
                    spec_config = get_specialist_config(current_specialist)

                    if handoff_requested in spec_config.can_handoff_to:
                        if assistants and handoff_requested in assistants:
                            yield {
                                "type": "handoff",
                                "data": {
                                    "from_specialist": current_specialist.value,
                                    "to_specialist": handoff_requested.value,
                                    "handoff_number": handoff_count + 1,
                                },
                            }

                            current_context = self._prepare_handoff_context(
                                original_input=user_input,
                                previous_output=step_output,
                                from_specialist=current_specialist,
                                to_specialist=handoff_requested,
                            )

                            current_specialist = handoff_requested
                            agent_chain.append(current_specialist)
                            handoff_count += 1
                            continue

                # No handoff, we're done
                break

            except Exception as e:
                logger.error(f"Specialist streaming failed: {e}")
                yield {
                    "type": "error",
                    "data": {
                        "error": "EXECUTION_ERROR",
                        "message": str(e),
                        "specialist": current_specialist.value,
                    },
                }
                return

        # Signal completion
        yield {
            "type": "collaboration_complete",
            "data": {
                "agent_chain": [s.value for s in agent_chain],
                "handoff_count": handoff_count,
                "total_duration_ms": (time.time() - start_time) * 1000,
            },
        }

    def _detect_loop(self, agent_chain: list[SpecialistType]) -> bool:
        """
        Detect if the agent chain contains a loop.

        Looks for patterns like:
        - A -> B -> A (simple ping-pong)
        - A -> B -> C -> A (circular)
        - A -> B -> A -> B (repeated pattern)
        """
        if len(agent_chain) < 3:
            return False

        window = self.config.loop_detection_window

        # Check for simple loops (A -> B -> A)
        if len(agent_chain) >= 3:
            recent = agent_chain[-3:]
            if recent[0] == recent[2]:
                return True

        # Check for repeated patterns in window
        if len(agent_chain) >= window * 2:
            recent = agent_chain[-window * 2 :]
            first_half = recent[:window]
            second_half = recent[window:]
            if first_half == second_half:
                return True

        # Check for same specialist appearing too many times
        recent = agent_chain[-window:] if len(agent_chain) >= window else agent_chain
        for specialist in SpecialistType:
            if recent.count(specialist) >= 3:
                return True

        return False

    def _build_specialist_prompt(
        self,
        user_input: str,
        specialist_type: SpecialistType,
        previous_steps: list[CollaborationStep],
    ) -> str:
        """Build the prompt for a specialist agent"""
        prompt_parts = []

        # Add context from previous steps if any
        if previous_steps:
            prompt_parts.append("Previous work done by other specialists:")
            for step in previous_steps[-2:]:  # Only last 2 steps for context
                prompt_parts.append(
                    f"\n[{step.specialist_type.value}]:\n{step.output[:500]}..."
                    if len(step.output) > 500
                    else f"\n[{step.specialist_type.value}]:\n{step.output}"
                )
            prompt_parts.append("\n---\n")

        prompt_parts.append(user_input)

        return "\n".join(prompt_parts)

    def _prepare_handoff_context(
        self,
        original_input: str,
        previous_output: str,
        from_specialist: SpecialistType,
        to_specialist: SpecialistType,
    ) -> str:
        """Prepare context for handoff to another specialist"""
        # Remove handoff markers from output
        clean_output = self._clean_handoff_markers(previous_output)

        return f"""Original request: {original_input}

The {from_specialist.value} specialist has done some work and needs your help:

{clean_output}

Please continue working on the original request using your specialized tools."""

    def _clean_handoff_markers(self, text: str) -> str:
        """Remove handoff markers from text"""
        markers = ["NEED_RESEARCH", "NEED_CODE", "NEED_DATA"]
        result = text
        for marker in markers:
            result = result.replace(marker, "")
        return result.strip()
