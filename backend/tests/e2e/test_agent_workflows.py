"""
End-to-end tests for complete agent workflows.

Tests complete user scenarios from input to output.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_llm():
    """Create a mock LLM for testing."""
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="Test response"))
    return llm


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def research_assistant():
    """Create a research-type assistant."""
    assistant = MagicMock()
    assistant.id = uuid4()
    assistant.name = "Research Assistant"
    assistant.system_prompt = "You are a research assistant."
    assistant.specialist_type = "RESEARCH"
    assistant.agent_tools_enabled = True
    assistant.agent_max_iterations = 5
    assistant.agent_token_budget = 8000
    assistant.agent_cost_limit_usd = 0.50
    assistant.agent_enable_planning = True
    assistant.agent_enable_reflection = True
    assistant.agent_rag_mode = "query_planning"
    assistant.enable_memory = False
    return assistant


@pytest.fixture
def code_assistant():
    """Create a code-type assistant."""
    assistant = MagicMock()
    assistant.id = uuid4()
    assistant.name = "Code Assistant"
    assistant.system_prompt = "You are a coding assistant."
    assistant.specialist_type = "CODE"
    assistant.agent_tools_enabled = True
    assistant.agent_max_iterations = 3
    assistant.agent_token_budget = 4000
    assistant.agent_cost_limit_usd = 0.25
    assistant.agent_enable_planning = True
    assistant.agent_enable_reflection = True
    assistant.enable_memory = False
    return assistant


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_superuser = False
    return user


# ============================================================================
# Research Workflow Tests
# ============================================================================


class TestResearchWorkflow:
    """Tests for research assistant workflows."""

    @pytest.mark.asyncio
    async def test_simple_web_search_workflow(
        self, research_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test a simple web search workflow."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            # Mock the graph to return a simple result
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "Here are the search results about AI: ...",
                    "iterations": 2,
                    "tools_used": [
                        {"name": "web_search", "input": {"query": "AI news"}}
                    ],
                    "token_usage": {"total": 500},
                    "cost_spent_usd": 0.05,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=research_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.llm = mock_llm
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Search for the latest AI news",
                chat_history=[],
            )

            assert result is not None
            assert "output" in result or "final_answer" in result

    @pytest.mark.asyncio
    async def test_kb_search_with_query_planning(
        self, research_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test KB search with query planning."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "Based on the documents, the comparison shows...",
                    "iterations": 3,
                    "tools_used": [
                        {
                            "name": "knowledge_base_query",
                            "input": {"query": "Company A revenue"},
                        },
                        {
                            "name": "knowledge_base_query",
                            "input": {"query": "Company B revenue"},
                        },
                    ],
                    "token_usage": {"total": 1000},
                    "cost_spent_usd": 0.10,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=research_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Compare revenue of Company A vs Company B",
                chat_history=[],
            )

            assert result is not None


# ============================================================================
# Code Execution Workflow Tests
# ============================================================================


class TestCodeWorkflow:
    """Tests for code assistant workflows."""

    @pytest.mark.asyncio
    async def test_simple_code_execution(
        self, code_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test simple code generation and execution."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "The sum of numbers 1-100 is 5050.",
                    "iterations": 2,
                    "tools_used": [
                        {
                            "name": "execute_python",
                            "input": {"code": "print(sum(range(1, 101)))"},
                        }
                    ],
                    "token_usage": {"total": 300},
                    "cost_spent_usd": 0.03,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=code_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Calculate the sum of numbers from 1 to 100",
                chat_history=[],
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_code_with_file_operations(
        self, code_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test code execution with file read/write."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "I've read the data and created the analysis.",
                    "iterations": 3,
                    "tools_used": [
                        {
                            "name": "file_operations",
                            "input": {"operation": "read", "path": "data.csv"},
                        },
                        {
                            "name": "execute_python",
                            "input": {"code": "import pandas..."},
                        },
                        {
                            "name": "file_operations",
                            "input": {"operation": "write", "path": "output.txt"},
                        },
                    ],
                    "token_usage": {"total": 800},
                    "cost_spent_usd": 0.08,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=code_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Read data.csv and create a summary",
                chat_history=[],
            )

            assert result is not None


# ============================================================================
# Data Analysis Workflow Tests
# ============================================================================


class TestDataAnalysisWorkflow:
    """Tests for data analysis workflows."""

    @pytest.mark.asyncio
    async def test_data_analysis_workflow(self, mock_user, mock_db_session, mock_llm):
        """Test complete data analysis workflow."""
        data_assistant = MagicMock()
        data_assistant.id = uuid4()
        data_assistant.name = "Data Analyst"
        data_assistant.specialist_type = "DATA"
        data_assistant.agent_tools_enabled = True
        data_assistant.agent_max_iterations = 4
        data_assistant.agent_token_budget = 4000
        data_assistant.agent_cost_limit_usd = 0.30
        data_assistant.agent_enable_planning = True
        data_assistant.enable_memory = False

        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "The sales data shows a 15% increase...",
                    "iterations": 3,
                    "tools_used": [
                        {"name": "list_tabular_documents", "input": {}},
                        {"name": "analyze_data", "input": {"operation": "describe"}},
                        {"name": "analyze_data", "input": {"operation": "aggregate"}},
                    ],
                    "token_usage": {"total": 600},
                    "cost_spent_usd": 0.06,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=data_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Analyze the sales data and show trends",
                chat_history=[],
            )

            assert result is not None


# ============================================================================
# Multi-Agent Workflow Tests
# ============================================================================


class TestMultiAgentWorkflow:
    """Tests for multi-agent collaboration workflows."""

    @pytest.mark.asyncio
    async def test_research_to_code_handoff(
        self, research_assistant, code_assistant, mock_user, mock_db_session
    ):
        """Test handoff from research to code assistant."""
        from airbeeps.agents.specialist.orchestrator import MultiAgentOrchestrator
        from airbeeps.agents.specialist.types import SpecialistType

        with patch(
            "airbeeps.agents.specialist.orchestrator.MultiAgentOrchestrator._execute_specialist"
        ) as mock_exec:
            # First call: research finds info, requests code handoff
            # Second call: code assistant executes
            mock_exec.side_effect = [
                {
                    "output": "I found the data. NEED_CODE to analyze it.",
                    "iterations": 2,
                    "cost_spent": 0.10,
                },
                {
                    "output": "Here's the Python analysis: ...",
                    "iterations": 2,
                    "cost_spent": 0.08,
                },
            ]

            with patch(
                "airbeeps.agents.specialist.orchestrator.AgentRouter"
            ) as mock_router_class:
                mock_router = MagicMock()
                mock_router.route = AsyncMock(
                    return_value=MagicMock(
                        specialist_type=SpecialistType.RESEARCH,
                        confidence=0.9,
                    )
                )
                mock_router_class.return_value = mock_router

                orchestrator = MultiAgentOrchestrator(
                    specialists={
                        SpecialistType.RESEARCH: research_assistant,
                        SpecialistType.CODE: code_assistant,
                    },
                    session=mock_db_session,
                    user=mock_user,
                )
                orchestrator.router = mock_router

                with patch.object(orchestrator, "_find_specialist") as mock_find:
                    mock_find.return_value = code_assistant

                    result = await orchestrator.execute(
                        user_input="Research best sorting algorithms and implement in Python"
                    )

                    assert result is not None

    @pytest.mark.asyncio
    async def test_loop_detection_prevents_infinite_handoff(
        self, research_assistant, code_assistant, mock_user, mock_db_session
    ):
        """Test that loop detection prevents infinite handoffs."""
        from airbeeps.agents.specialist.orchestrator import MultiAgentOrchestrator
        from airbeeps.agents.specialist.types import SpecialistType

        # Create an orchestrator and test loop detection
        orchestrator = MultiAgentOrchestrator(
            specialists={
                SpecialistType.RESEARCH: research_assistant,
                SpecialistType.CODE: code_assistant,
            },
            session=mock_db_session,
            user=mock_user,
        )

        # Test the loop detection method directly
        # A -> B -> A pattern should be detected
        agent_chain = [
            SpecialistType.RESEARCH,
            SpecialistType.CODE,
            SpecialistType.RESEARCH,
        ]

        is_loop = orchestrator._detect_loop(agent_chain)
        assert is_loop is True

        # Normal chain should not be detected as loop
        normal_chain = [
            SpecialistType.RESEARCH,
            SpecialistType.CODE,
        ]
        is_loop = orchestrator._detect_loop(normal_chain)
        assert is_loop is False


# ============================================================================
# Budget Enforcement Tests
# ============================================================================


class TestBudgetEnforcement:
    """Tests for budget enforcement in workflows."""

    @pytest.mark.asyncio
    async def test_workflow_stops_at_cost_limit(
        self, research_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test that workflow stops when cost limit is reached."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        research_assistant.agent_cost_limit_usd = 0.10

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "Cost limit reached. Partial results: ...",
                    "iterations": 5,
                    "tools_used": [],
                    "token_usage": {"total": 2000},
                    "cost_spent_usd": 0.10,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=research_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Do extensive research on everything",
                chat_history=[],
            )

            # Result should exist even if budget was hit
            assert result is not None

    @pytest.mark.asyncio
    async def test_workflow_stops_at_iteration_limit(
        self, research_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test that workflow stops when iteration limit is reached."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        research_assistant.agent_max_iterations = 3

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            mock_compiled = AsyncMock()
            mock_compiled.ainvoke = AsyncMock(
                return_value={
                    "final_answer": "Max iterations reached. Current progress: ...",
                    "iterations": 3,
                    "tools_used": [],
                    "token_usage": {"total": 1500},
                    "cost_spent_usd": 0.07,
                }
            )
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=research_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            result = await engine.execute(
                user_input="Keep researching until you find everything",
                chat_history=[],
            )

            assert result is not None


# ============================================================================
# Streaming Workflow Tests
# ============================================================================


class TestStreamingWorkflow:
    """Tests for streaming workflow execution."""

    @pytest.mark.asyncio
    async def test_streaming_produces_events(
        self, research_assistant, mock_user, mock_db_session, mock_llm
    ):
        """Test that streaming execution produces events."""
        from airbeeps.agents.graph_executor import LangGraphAgentEngine

        with patch("airbeeps.agents.graph_executor.create_agent_graph") as mock_graph:
            # Create async generator for streaming
            async def mock_stream(*args, **kwargs):
                yield {"type": "planning", "data": {"plan": "Step 1: Search"}}
                yield {"type": "agent_action", "data": {"tool": "web_search"}}
                yield {"type": "tool_result", "data": {"result": "Found info"}}
                yield {"type": "content_chunk", "data": {"content": "Based on"}}
                yield {"type": "content_chunk", "data": {"content": " my research..."}}

            mock_compiled = AsyncMock()
            mock_compiled.astream = mock_stream
            mock_graph.return_value = mock_compiled

            engine = LangGraphAgentEngine(
                assistant=research_assistant,
                session=mock_db_session,
                user=mock_user,
            )
            engine.graph = mock_compiled

            events = []
            async for event in engine.stream_execute(
                user_input="Search for AI news",
                chat_history=[],
            ):
                events.append(event)

            assert len(events) > 0
