"""
RAG (Retrieval-Augmented Generation) Module.

SOTA RAG system built on LlamaIndex with:
- Multiple vector store backends (Qdrant, ChromaDB, PGVector, Milvus)
- Semantic and hierarchical document chunking
- Query transformation (HyDE, multi-query, step-back)
- Hybrid retrieval (dense + BM25 with RRF fusion)
- Cross-encoder reranking
- RAGAS-based evaluation

Agentic RAG features:
- Query planning and decomposition
- Self-RAG with relevance judgement
- Multi-hop retrieval for complex queries
"""

from .doc_processor import DocumentProcessor, ProcessedChunk, get_document_processor
from .embeddings import EmbeddingService, FakeEmbedding, get_embedding_service
from .evaluator import EvaluationResult, EvaluationSample, RAGEvaluator, get_evaluator
from .hybrid_retriever import HybridRetrieverBuilder, build_hybrid_retriever
from .index_manager import IndexManager, get_index_manager
from .multi_hop import MultiHopResult, MultiHopRetriever, get_multi_hop_retriever
from .query_planner import QueryPlanResult, QueryPlanner, get_query_planner
from .query_transform import QueryTransformer, QueryTransformType, get_query_transformer
from .reranker import RerankerFactory, RerankerType, get_reranker
from .self_rag import SelfRAG, SelfRAGResult, get_self_rag
from .service import RAGService, RetrievalConfig, RetrievalResult
from .stores import VectorStoreFactory, VectorStoreType, get_vector_store

__all__ = [
    # Service
    "RAGService",
    "RetrievalResult",
    "RetrievalConfig",
    # Document Processing
    "DocumentProcessor",
    "ProcessedChunk",
    "get_document_processor",
    # Embeddings
    "EmbeddingService",
    "FakeEmbedding",
    "get_embedding_service",
    # Index Management
    "IndexManager",
    "get_index_manager",
    # Vector Stores
    "VectorStoreFactory",
    "VectorStoreType",
    "get_vector_store",
    # Query Transformation
    "QueryTransformer",
    "QueryTransformType",
    "get_query_transformer",
    # Hybrid Retrieval
    "HybridRetrieverBuilder",
    "build_hybrid_retriever",
    # Reranking
    "RerankerFactory",
    "RerankerType",
    "get_reranker",
    # Evaluation
    "RAGEvaluator",
    "EvaluationResult",
    "EvaluationSample",
    "get_evaluator",
    # Agentic RAG
    "QueryPlanner",
    "QueryPlanResult",
    "get_query_planner",
    "SelfRAG",
    "SelfRAGResult",
    "get_self_rag",
    "MultiHopRetriever",
    "MultiHopResult",
    "get_multi_hop_retriever",
]
