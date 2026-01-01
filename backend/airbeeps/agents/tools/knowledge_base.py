"""
Knowledge base query tool
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .base import AgentTool, AgentToolConfig
from .registry import tool_registry


@tool_registry.register
class KnowledgeBaseTool(AgentTool):
    """Tool for querying knowledge base"""

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

    async def execute(self, query: str, top_k: int = 5) -> Any:
        """Execute knowledge base query"""
        try:
            if not self.session:
                return "Error: Database session not available"

            if not self.knowledge_base_ids:
                return "Error: No knowledge base configured"

            # Import here to avoid circular dependency
            from airbeeps.rag.service import RAGService

            rag_service = RAGService(self.session)

            # Query each knowledge base
            all_results = []
            for kb_id_str in self.knowledge_base_ids:
                try:
                    kb_id = uuid.UUID(kb_id_str)
                    results = await rag_service.relevance_search(
                        query=query, knowledge_base_id=kb_id, k=top_k
                    )
                    all_results.extend(results)
                except Exception:
                    continue

            if not all_results:
                return "No relevant information found in knowledge base."

            # Format results
            formatted_results = []
            for i, doc in enumerate(all_results[:top_k], 1):
                content = doc.page_content if hasattr(doc, "page_content") else str(doc)
                meta = doc.metadata or {}
                ref_parts = []
                if meta.get("title"):
                    ref_parts.append(f"title={meta.get('title')}")
                if meta.get("file_path"):
                    ref_parts.append(f"file={meta.get('file_path')}")
                if meta.get("row_number"):
                    ref_parts.append(f"row={meta.get('row_number')}")
                if meta.get("sheet"):
                    ref_parts.append(f"sheet={meta.get('sheet')}")
                if meta.get("source_url"):
                    ref_parts.append(f"url={meta.get('source_url')}")
                ref_suffix = f" [{' | '.join(ref_parts)}]" if ref_parts else ""
                formatted_results.append(f"[{i}] {content}\n{ref_suffix}".strip())

            return (
                "Knowledge base references (use the bracketed numbers for citations):\n"
                + "\n\n".join(formatted_results)
            )

        except Exception as e:
            return f"Error querying knowledge base: {e!s}"
