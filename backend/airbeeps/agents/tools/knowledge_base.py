"""
Knowledge base query tool for agents.

Uses LlamaIndex-based RAG service for retrieval.
Supports agentic patterns: query planning, self-RAG, multi-hop retrieval.
"""

import logging
import uuid
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .base import AgentTool, AgentToolConfig, ToolSecurityLevel
from .registry import tool_registry

logger = logging.getLogger(__name__)


class AgenticRAGMode(str, Enum):
    """Agentic RAG execution modes."""

    STANDARD = "standard"  # Basic retrieval
    QUERY_PLANNING = "query_planning"  # Decompose complex queries
    SELF_RAG = "self_rag"  # Self-critique and retry
    MULTI_HOP = "multi_hop"  # Chain multiple retrievals


@tool_registry.register
class KnowledgeBaseTool(AgentTool):
    """Tool for querying knowledge base using LlamaIndex RAG."""

    def __init__(
        self,
        config: AgentToolConfig | None = None,
        session: AsyncSession | None = None,
    ):
        super().__init__(config)
        self.session = session
        self.knowledge_base_ids = (
            config.parameters.get("knowledge_base_ids", []) if config else []
        )

    @property
    def name(self) -> str:
        return "knowledge_base_query"

    @property
    def description(self) -> str:
        return "Query information from knowledge base. Useful for retrieving relevant documents and context."

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant information in the knowledge base",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, top_k: int = 5) -> Any:
        """Execute knowledge base query using LlamaIndex RAG."""
        try:
            if not self.session:
                return "Error: Database session not available"

            if not self.knowledge_base_ids:
                return "Error: No knowledge base configured"

            from airbeeps.rag.service import RAGService

            rag_service = RAGService(self.session)

            # Query each knowledge base
            all_results = []
            for kb_id_str in self.knowledge_base_ids:
                try:
                    kb_id = uuid.UUID(kb_id_str)
                    results = await rag_service.relevance_search(
                        query=query,
                        knowledge_base_id=kb_id,
                        k=top_k,
                        use_hybrid=True,
                        use_rerank=True,
                    )
                    all_results.extend(results)
                except Exception:
                    continue

            if not all_results:
                return "No relevant information found in knowledge base."

            # Sort by score and take top_k
            all_results.sort(key=lambda x: x.score, reverse=True)
            all_results = all_results[:top_k]

            # Format results
            formatted_results = []
            for i, result in enumerate(all_results, 1):
                content = result.content
                metadata = result.metadata or {}

                ref_parts = []
                if result.title:
                    ref_parts.append(f"title={result.title}")
                if metadata.get("file_path"):
                    ref_parts.append(f"file={metadata.get('file_path')}")
                if metadata.get("row_number"):
                    ref_parts.append(f"row={metadata.get('row_number')}")
                if metadata.get("sheet"):
                    ref_parts.append(f"sheet={metadata.get('sheet')}")
                if metadata.get("page_number"):
                    ref_parts.append(f"page={metadata.get('page_number')}")
                if metadata.get("source_url"):
                    ref_parts.append(f"url={metadata.get('source_url')}")

                ref_suffix = f" [{' | '.join(ref_parts)}]" if ref_parts else ""
                formatted_results.append(f"[{i}] {content}\n{ref_suffix}".strip())

            return (
                "Knowledge base references (use the bracketed numbers for citations):\n"
                + "\n\n".join(formatted_results)
            )

        except Exception as e:
            return f"Error querying knowledge base: {e!s}"


@tool_registry.register
class KnowledgeBaseSearchTool(AgentTool):
    """
    Alternative knowledge base tool optimized for search.

    Returns structured results suitable for further processing.
    """

    def __init__(
        self,
        config: AgentToolConfig | None = None,
        session: AsyncSession | None = None,
    ):
        super().__init__(config)
        self.session = session
        self.knowledge_base_ids = (
            config.parameters.get("knowledge_base_ids", []) if config else []
        )

    @property
    def name(self) -> str:
        return "knowledge_base_search"

    @property
    def description(self) -> str:
        return "Search the knowledge base and return structured results with metadata."

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5,
                },
                "use_hybrid": {
                    "type": "boolean",
                    "description": "Use hybrid search (vector + keyword)",
                    "default": True,
                },
                "use_rerank": {
                    "type": "boolean",
                    "description": "Apply reranking to results",
                    "default": True,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_rerank: bool = True,
    ) -> dict[str, Any]:
        """Execute structured search."""
        try:
            if not self.session:
                return {"error": "Database session not available", "results": []}

            if not self.knowledge_base_ids:
                return {"error": "No knowledge base configured", "results": []}

            from airbeeps.rag.service import RAGService

            rag_service = RAGService(self.session)

            all_results = []
            for kb_id_str in self.knowledge_base_ids:
                try:
                    kb_id = uuid.UUID(kb_id_str)
                    results = await rag_service.relevance_search(
                        query=query,
                        knowledge_base_id=kb_id,
                        k=top_k,
                        use_hybrid=use_hybrid,
                        use_rerank=use_rerank,
                    )
                    all_results.extend(results)
                except Exception:
                    continue

            # Sort and limit
            all_results.sort(key=lambda x: x.score, reverse=True)
            all_results = all_results[:top_k]

            return {
                "query": query,
                "results": [
                    {
                        "content": r.content,
                        "score": r.score,
                        "title": r.title,
                        "document_id": r.document_id,
                        "chunk_id": r.chunk_id,
                        "metadata": r.metadata,
                    }
                    for r in all_results
                ],
                "total": len(all_results),
            }

        except Exception as e:
            return {"error": str(e), "results": []}


@tool_registry.register
class AgenticKnowledgeBaseTool(AgentTool):
    """
    Advanced knowledge base tool with agentic RAG patterns.

    Supports:
    - Query planning: Decompose complex queries into sub-queries
    - Self-RAG: Self-critique and adaptive retry
    - Multi-hop: Chain multiple retrievals for complex reasoning
    """

    def __init__(
        self,
        config: AgentToolConfig | None = None,
        session: AsyncSession | None = None,
    ):
        super().__init__(config)
        self.session = session
        self.knowledge_base_ids = (
            config.parameters.get("knowledge_base_ids", []) if config else []
        )

    @property
    def name(self) -> str:
        return "agentic_knowledge_base"

    @property
    def description(self) -> str:
        return (
            "Advanced knowledge base search with agentic capabilities. "
            "Use 'query_planning' mode for complex multi-part questions. "
            "Use 'self_rag' mode when you need high-confidence answers. "
            "Use 'multi_hop' mode for questions requiring reasoning across multiple topics."
        )

    @property
    def security_level(self) -> ToolSecurityLevel:
        return ToolSecurityLevel.SAFE

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "mode": {
                    "type": "string",
                    "description": "Agentic mode: 'standard', 'query_planning', 'self_rag', or 'multi_hop'",
                    "enum": ["standard", "query_planning", "self_rag", "multi_hop"],
                    "default": "standard",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "max_attempts": {
                    "type": "integer",
                    "description": "Max attempts for self_rag mode",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 5,
                },
                "max_hops": {
                    "type": "integer",
                    "description": "Max hops for multi_hop mode",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        mode: str = "standard",
        top_k: int = 5,
        max_attempts: int = 3,
        max_hops: int = 3,
    ) -> dict[str, Any]:
        """Execute agentic knowledge base query."""
        try:
            if not self.session:
                return {"error": "Database session not available", "results": []}

            if not self.knowledge_base_ids:
                return {"error": "No knowledge base configured", "results": []}

            from airbeeps.rag.service import RAGService

            rag_service = RAGService(self.session)

            # Get first KB ID (primary)
            kb_id = uuid.UUID(self.knowledge_base_ids[0])

            # Get LLM for agentic patterns
            llm = await self._get_llm()

            agentic_mode = AgenticRAGMode(mode)

            if agentic_mode == AgenticRAGMode.QUERY_PLANNING:
                return await self._execute_query_planning(
                    query, kb_id, rag_service, llm, top_k
                )

            elif agentic_mode == AgenticRAGMode.SELF_RAG:
                return await self._execute_self_rag(
                    query, kb_id, rag_service, llm, top_k, max_attempts
                )

            elif agentic_mode == AgenticRAGMode.MULTI_HOP:
                return await self._execute_multi_hop(
                    query, kb_id, rag_service, llm, top_k, max_hops
                )

            else:
                # Standard mode
                return await self._execute_standard(query, kb_id, rag_service, top_k)

        except Exception as e:
            logger.exception(f"Agentic KB query failed: {e}")
            return {"error": str(e), "results": []}

    async def _get_llm(self):
        """Get LLM for agentic patterns."""
        try:
            from airbeeps.llm.service import get_default_llm

            return await get_default_llm()
        except Exception as e:
            logger.warning(f"Failed to get LLM for agentic RAG: {e}")
            return None

    async def _execute_standard(
        self,
        query: str,
        kb_id: uuid.UUID,
        rag_service: Any,
        top_k: int,
    ) -> dict[str, Any]:
        """Standard retrieval mode."""
        results = await rag_service.relevance_search(
            query=query,
            knowledge_base_id=kb_id,
            k=top_k,
            use_hybrid=True,
            use_rerank=True,
        )

        return {
            "mode": "standard",
            "query": query,
            "results": self._format_results(results),
            "total": len(results),
        }

    async def _execute_query_planning(
        self,
        query: str,
        kb_id: uuid.UUID,
        rag_service: Any,
        llm: Any,
        top_k: int,
    ) -> dict[str, Any]:
        """Query planning mode with decomposition."""
        from airbeeps.rag.query_planner import QueryPlanner

        planner = QueryPlanner(llm=llm)

        plan_result = await planner.execute_plan(
            query=query,
            kb_id=kb_id,
            retrieval_func=rag_service.relevance_search,
            top_k=top_k,
        )

        # Collect all results
        all_results = []
        for sr in plan_result.sub_results:
            if sr.success:
                all_results.extend(sr.results)

        # Deduplicate and sort
        seen_ids = set()
        unique_results = []
        for r in all_results:
            if r.node_id not in seen_ids:
                seen_ids.add(r.node_id)
                unique_results.append(r)
        unique_results.sort(key=lambda x: x.score, reverse=True)

        return {
            "mode": "query_planning",
            "original_query": query,
            "was_decomposed": plan_result.was_decomposed,
            "sub_queries": plan_result.sub_queries,
            "synthesized_answer": plan_result.synthesized_answer,
            "results": self._format_results(unique_results[:top_k]),
            "total": len(unique_results),
        }

    async def _execute_self_rag(
        self,
        query: str,
        kb_id: uuid.UUID,
        rag_service: Any,
        llm: Any,
        top_k: int,
        max_attempts: int,
    ) -> dict[str, Any]:
        """Self-RAG mode with critique and retry."""
        from airbeeps.rag.self_rag import SelfRAG

        self_rag = SelfRAG(
            llm=llm,
            max_attempts=max_attempts,
            min_confidence=50,
            generate_answer=True,
        )

        result = await self_rag.retrieve_with_self_critique(
            query=query,
            kb_id=kb_id,
            retrieval_func=rag_service.relevance_search,
            top_k=top_k,
        )

        return {
            "mode": "self_rag",
            "original_query": query,
            "final_query": result.final_query,
            "attempts": result.attempts,
            "judgement": {
                "is_relevant": result.judgement.is_relevant
                if result.judgement
                else None,
                "is_sufficient": result.judgement.is_sufficient
                if result.judgement
                else None,
                "confidence": result.judgement.confidence if result.judgement else None,
                "reasoning": result.judgement.reasoning if result.judgement else None,
            }
            if result.judgement
            else None,
            "generated_answer": result.generated_answer,
            "results": self._format_results(result.results),
            "total": len(result.results),
            "success": result.success,
        }

    async def _execute_multi_hop(
        self,
        query: str,
        kb_id: uuid.UUID,
        rag_service: Any,
        llm: Any,
        top_k: int,
        max_hops: int,
    ) -> dict[str, Any]:
        """Multi-hop retrieval mode."""
        from airbeeps.rag.multi_hop import MultiHopRetriever

        retriever = MultiHopRetriever(
            llm=llm,
            max_hops=max_hops,
            results_per_hop=top_k,
            synthesize_results=True,
        )

        result = await retriever.retrieve_multi_hop(
            query=query,
            kb_id=kb_id,
            retrieval_func=rag_service.relevance_search,
            top_k=top_k,
        )

        return {
            "mode": "multi_hop",
            "original_query": query,
            "total_hops": result.total_hops,
            "hops": [
                {
                    "hop_number": h.hop_number,
                    "query": h.query,
                    "num_results": h.num_results,
                }
                for h in result.hops
            ],
            "synthesized_answer": result.synthesized_answer,
            "results": self._format_results(result.all_results),
            "total": len(result.all_results),
            "success": result.success,
        }

    def _format_results(self, results: list[Any]) -> list[dict[str, Any]]:
        """Format retrieval results for output."""
        formatted = []
        for r in results:
            if hasattr(r, "content"):
                formatted.append(
                    {
                        "content": r.content,
                        "score": r.score if hasattr(r, "score") else 0.0,
                        "title": r.title if hasattr(r, "title") else None,
                        "document_id": r.document_id
                        if hasattr(r, "document_id")
                        else None,
                        "chunk_id": r.chunk_id if hasattr(r, "chunk_id") else None,
                        "metadata": r.metadata if hasattr(r, "metadata") else {},
                    }
                )
            elif isinstance(r, dict):
                formatted.append(r)
        return formatted
