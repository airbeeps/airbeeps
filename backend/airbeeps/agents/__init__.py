"""
Agent module - AI agents with tool calling capabilities

This module provides:
- Tool execution engine (ReAct-style and LangGraph-based)
- MCP server integration
- Security layer (sandbox, permissions, content filtering)
- Built-in tools (knowledge base, web search, code execution, file operations)
- Tracing and observability (OpenTelemetry-based)
- Multi-agent system with specialist agents, routing, and orchestration (Phase 6)
- Resilience patterns: retry, circuit breaker, health checks (Phase 7)
"""

from .executor import AgentExecutionEngine
from .graph_executor import LangGraphAgentEngine, get_agent_executor
from .multiagent_executor import MultiAgentEngine, get_multiagent_executor
from .resilience import (
    # Circuit Breaker
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    HealthRegistry,
    # Health
    HealthStatus,
    # Retry
    RetryConfig,
    ToolExecutionError,
    execute_tool_with_retry,
    execute_with_retry,
    get_circuit_breaker,
    get_health_registry,
    # Metrics
    get_metrics_recorder,
    # API
    health_router,
    register_health_check,
)
from .specialist import (
    AgentCollaborationConfig,
    AgentRouter,
    CollaborationResult,
    HandoffRequest,
    MultiAgentOrchestrator,
    RoutingDecision,
    SpecialistConfig,
    SpecialistType,
    get_specialist_config,
)
from .tools import AgentTool, AgentToolConfig, ToolSecurityLevel, tool_registry

__all__ = [
    # Executors
    "AgentExecutionEngine",
    "LangGraphAgentEngine",
    "get_agent_executor",
    "MultiAgentEngine",
    "get_multiagent_executor",
    # Tools
    "AgentTool",
    "AgentToolConfig",
    "ToolSecurityLevel",
    "tool_registry",
    # Multi-Agent (Phase 6)
    "SpecialistType",
    "SpecialistConfig",
    "get_specialist_config",
    "AgentRouter",
    "RoutingDecision",
    "MultiAgentOrchestrator",
    "CollaborationResult",
    "HandoffRequest",
    "AgentCollaborationConfig",
    # Resilience (Phase 7)
    "RetryConfig",
    "execute_with_retry",
    "execute_tool_with_retry",
    "ToolExecutionError",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitOpenError",
    "get_circuit_breaker",
    "HealthStatus",
    "HealthRegistry",
    "get_health_registry",
    "register_health_check",
    "get_metrics_recorder",
    "health_router",
]
