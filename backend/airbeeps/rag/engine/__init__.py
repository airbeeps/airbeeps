"""
RAG Engine abstraction layer.

Provides a pluggable interface for different RAG backends:
- VectorEngine: Traditional vector similarity search (Chroma, Milvus, etc.)
- Future: HybridEngine, GraphEngine, LightRAGEngine

Usage:
    from airbeeps.rag.engine import get_engine, EngineType

    engine = get_engine(EngineType.VECTOR)
    results = await engine.retrieve(query, kb_id, ...)
"""

from .base import BaseRAGEngine, EngineType, RetrievalResult
from .factory import (
    get_engine,
    get_engine_for_kb,
    list_available_engines,
    register_engine,
)
from .vector import VectorEngine

__all__ = [
    "BaseRAGEngine",
    "EngineType",
    "RetrievalResult",
    "VectorEngine",
    "get_engine",
    "get_engine_for_kb",
    "list_available_engines",
    "register_engine",
]
