"""
Multi-Agent Specialist System.

This module provides specialist agent types, routing, and orchestration
for multi-agent collaboration with:
- Specialist agent types (RESEARCH, CODE, DATA, GENERAL)
- Intent-based routing to appropriate specialists
- Multi-agent orchestration with loop detection
- Budget enforcement during handoffs
"""

from .orchestrator import (
    AgentCollaborationConfig,
    CollaborationResult,
    HandoffRequest,
    MultiAgentOrchestrator,
)
from .router import AgentRouter, RoutingDecision
from .types import SpecialistConfig, SpecialistType, get_specialist_config

__all__ = [
    # Types
    "SpecialistType",
    "SpecialistConfig",
    "get_specialist_config",
    # Router
    "AgentRouter",
    "RoutingDecision",
    # Orchestrator
    "MultiAgentOrchestrator",
    "CollaborationResult",
    "HandoffRequest",
    "AgentCollaborationConfig",
]
