"""
Engine factory: create and manage RAG engine instances.

Provides a pluggable registry for engine types and a factory
function to get engine instances.
"""

import logging

from .base import BaseRAGEngine, EngineType
from .vector import VectorEngine

logger = logging.getLogger(__name__)


# Engine type -> implementation class registry
_engine_registry: dict[EngineType, type[BaseRAGEngine]] = {
    EngineType.VECTOR: VectorEngine,
}

# Singleton instances per engine type (optional caching)
_engine_instances: dict[EngineType, BaseRAGEngine] = {}


def register_engine(
    engine_type: EngineType,
    engine_class: type[BaseRAGEngine],
) -> None:
    """
    Register an engine implementation for an engine type.

    Use this to add support for new RAG engine types.

    Args:
        engine_type: The engine type to register
        engine_class: The engine class implementing BaseRAGEngine
    """
    _engine_registry[engine_type] = engine_class
    # Clear cached instance if exists
    _engine_instances.pop(engine_type, None)
    logger.info(
        f"Registered RAG engine: {engine_type.value} -> {engine_class.__name__}"
    )


def get_engine(
    engine_type: EngineType = EngineType.VECTOR,
    use_cache: bool = True,
    **kwargs,
) -> BaseRAGEngine:
    """
    Get a RAG engine instance.

    Args:
        engine_type: Type of engine to get (default: VECTOR)
        use_cache: Whether to return cached instance (default: True)
        **kwargs: Additional arguments passed to engine constructor

    Returns:
        RAG engine instance

    Raises:
        ValueError: If engine type is not registered
    """
    if engine_type not in _engine_registry:
        available = [e.value for e in _engine_registry]
        raise ValueError(
            f"Unknown engine type: {engine_type.value}. "
            f"Available: {', '.join(available)}"
        )

    # Return cached instance if available and requested
    if use_cache and engine_type in _engine_instances:
        return _engine_instances[engine_type]

    # Create new instance
    engine_class = _engine_registry[engine_type]
    engine = engine_class(**kwargs)

    # Cache if requested
    if use_cache:
        _engine_instances[engine_type] = engine

    logger.debug(f"Created RAG engine: {engine_type.value}")
    return engine


def get_engine_for_kb(
    kb_config: dict | None = None,
    **kwargs,
) -> BaseRAGEngine:
    """
    Get the appropriate RAG engine for a knowledge base.

    Reads the engine_type from KB config and returns the
    corresponding engine instance.

    Args:
        kb_config: Knowledge base configuration dict
        **kwargs: Additional arguments passed to engine constructor

    Returns:
        RAG engine instance appropriate for the KB
    """
    if not kb_config:
        return get_engine(EngineType.VECTOR, **kwargs)

    engine_type_str = kb_config.get("engine_type", "vector")

    try:
        engine_type = EngineType(engine_type_str)
    except ValueError:
        logger.warning(
            f"Unknown engine_type '{engine_type_str}' in KB config, "
            f"falling back to vector"
        )
        engine_type = EngineType.VECTOR

    # If engine type is valid but not registered (not yet implemented), fall back to vector
    if engine_type not in _engine_registry:
        logger.warning(
            f"Engine type '{engine_type.value}' is not registered/implemented, "
            f"falling back to vector"
        )
        engine_type = EngineType.VECTOR

    return get_engine(engine_type, **kwargs)


def list_available_engines() -> list[str]:
    """List all registered engine types."""
    return [e.value for e in _engine_registry]


# Placeholder stubs for future engine types
# These will raise NotImplementedError until implemented


class HybridEngine(BaseRAGEngine):
    """
    Hybrid RAG engine combining vector + keyword search.

    TODO: Implement when needed.
    """

    engine_type = EngineType.HYBRID

    async def index_documents(self, *args, **kwargs):
        raise NotImplementedError("HybridEngine not yet implemented")

    async def delete_documents(self, *args, **kwargs):
        raise NotImplementedError("HybridEngine not yet implemented")

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError("HybridEngine not yet implemented")

    async def get_collection_info(self, *args, **kwargs):
        raise NotImplementedError("HybridEngine not yet implemented")


class GraphEngine(BaseRAGEngine):
    """
    Graph-based RAG engine.

    TODO: Implement when adding graph RAG support.
    """

    engine_type = EngineType.GRAPH

    async def index_documents(self, *args, **kwargs):
        raise NotImplementedError("GraphEngine not yet implemented")

    async def delete_documents(self, *args, **kwargs):
        raise NotImplementedError("GraphEngine not yet implemented")

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError("GraphEngine not yet implemented")

    async def get_collection_info(self, *args, **kwargs):
        raise NotImplementedError("GraphEngine not yet implemented")


class LightRAGEngine(BaseRAGEngine):
    """
    LightRAG implementation.

    TODO: Implement when adding LightRAG support.
    """

    engine_type = EngineType.LIGHTRAG

    async def index_documents(self, *args, **kwargs):
        raise NotImplementedError("LightRAGEngine not yet implemented")

    async def delete_documents(self, *args, **kwargs):
        raise NotImplementedError("LightRAGEngine not yet implemented")

    async def retrieve(self, *args, **kwargs):
        raise NotImplementedError("LightRAGEngine not yet implemented")

    async def get_collection_info(self, *args, **kwargs):
        raise NotImplementedError("LightRAGEngine not yet implemented")
