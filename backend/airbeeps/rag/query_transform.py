"""
Query Transformation Module for SOTA RAG.

Provides query enhancement techniques:
- HyDE (Hypothetical Document Embeddings)
- Multi-Query expansion
- Step-Back prompting
"""

import logging
import re
from enum import Enum
from typing import Any

from llama_index.core.llms import LLM

from airbeeps.config import settings

logger = logging.getLogger(__name__)


class QueryTransformType(str, Enum):
    """Supported query transformation types."""

    NONE = "none"
    HYDE = "hyde"
    MULTI_QUERY = "multi_query"
    STEP_BACK = "step_back"


# Prompt templates for query transformations
MULTI_QUERY_PROMPT = """You are an AI assistant helping to generate alternative search queries.
Given the original query, generate {num_queries} different versions that capture the same intent
but use different words or phrasings. This helps improve search recall.

Original query: {query}

Generate {num_queries} alternative queries, one per line. Do not number them or add prefixes.
"""

HYDE_PROMPT = """You are an AI assistant. Given the following question, write a hypothetical
passage that would answer this question. The passage should be informative and detailed,
as if it came from a knowledge base or documentation.

Question: {query}

Hypothetical answer passage:
"""

STEP_BACK_PROMPT = """You are an AI assistant helping to reformulate queries for better search.
Given a specific question, generate a more general "step-back" question that addresses the
broader concept or principle behind the original question.

Original question: {query}

Step-back question (more general):
"""


class QueryTransformer:
    """
    Transforms queries for improved retrieval.

    Supports multiple transformation strategies that can improve
    retrieval quality by expanding or reformulating queries.
    """

    def __init__(
        self,
        llm: LLM | None = None,
        transform_type: QueryTransformType | str | None = None,
    ):
        """
        Initialize the query transformer.

        Args:
            llm: LlamaIndex LLM for LLM-based transformations
            transform_type: Default transformation type
        """
        self.llm = llm
        self.transform_type = (
            QueryTransformType(transform_type)
            if transform_type
            else QueryTransformType(settings.RAG_QUERY_TRANSFORM_TYPE)
        )

    async def transform(
        self,
        query: str,
        transform_type: QueryTransformType | str | None = None,
        num_queries: int = 3,
        include_original: bool = True,
    ) -> list[str]:
        """
        Transform a query into one or more search queries.

        Args:
            query: Original query
            transform_type: Override default transformation type
            num_queries: Number of queries for multi-query
            include_original: Include original query in results

        Returns:
            List of transformed queries
        """
        if transform_type:
            t_type = QueryTransformType(transform_type)
        else:
            t_type = self.transform_type

        if t_type == QueryTransformType.NONE:
            return [query]

        if t_type == QueryTransformType.HYDE:
            return await self._hyde_transform(query, include_original)

        if t_type == QueryTransformType.MULTI_QUERY:
            return await self._multi_query_transform(
                query, num_queries, include_original
            )

        if t_type == QueryTransformType.STEP_BACK:
            return await self._step_back_transform(query, include_original)

        return [query]

    async def _hyde_transform(
        self,
        query: str,
        include_original: bool = True,
    ) -> list[str]:
        """
        HyDE transformation: Generate a hypothetical document.

        Instead of searching with the query, we search with a
        hypothetical answer that should be similar to actual documents.
        """
        if self.llm is None:
            logger.warning("HyDE requires LLM, falling back to original query")
            return [query]

        try:
            prompt = HYDE_PROMPT.format(query=query)
            response = await self.llm.acomplete(prompt)
            hypothetical_doc = response.text.strip()

            if not hypothetical_doc:
                return [query]

            queries = [hypothetical_doc]
            if include_original:
                queries.append(query)

            logger.debug(f"HyDE generated hypothetical document for: {query[:50]}...")
            return queries

        except Exception as e:
            logger.warning(f"HyDE transformation failed: {e}")
            return [query]

    async def _multi_query_transform(
        self,
        query: str,
        num_queries: int = 3,
        include_original: bool = True,
    ) -> list[str]:
        """
        Multi-query transformation: Generate alternative queries.

        This helps capture different phrasings of the same intent.
        """
        # Try LLM-based generation first
        if self.llm is not None:
            try:
                return await self._llm_multi_query(query, num_queries, include_original)
            except Exception as e:
                logger.warning(f"LLM multi-query failed, using deterministic: {e}")

        # Fallback to deterministic generation
        return self._deterministic_multi_query(query, num_queries, include_original)

    async def _llm_multi_query(
        self,
        query: str,
        num_queries: int,
        include_original: bool,
    ) -> list[str]:
        """Generate alternative queries using LLM."""
        prompt = MULTI_QUERY_PROMPT.format(query=query, num_queries=num_queries)
        response = await self.llm.acomplete(prompt)

        # Parse response lines
        lines = [line.strip() for line in response.text.strip().split("\n")]
        queries = [line for line in lines if line and len(line) > 5]

        # Limit to requested number
        queries = queries[:num_queries]

        if include_original and query not in queries:
            queries.insert(0, query)

        return queries if queries else [query]

    def _deterministic_multi_query(
        self,
        query: str,
        max_count: int = 3,
        include_original: bool = True,
    ) -> list[str]:
        """
        Generate alternative queries deterministically (no LLM).

        Uses simple text manipulations for low-risk alternatives.
        """
        alts: list[str] = []

        if include_original:
            alts.append(query.strip())

        # Remove punctuation variant
        simplified = re.sub(r"[^\w\s]", " ", query).strip()
        simplified = re.sub(r"\s+", " ", simplified)
        if simplified and simplified.lower() != query.lower():
            alts.append(simplified)

        # Split on sentence boundaries and use parts
        parts = re.split(r"[.?!;]", query)
        for p in parts:
            p = p.strip()
            if 20 <= len(p) <= 160 and p.lower() not in (a.lower() for a in alts):
                alts.append(p)
                if len(alts) >= max_count:
                    break

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for q in alts:
            key = q.lower()
            if key in seen or not q:
                continue
            seen.add(key)
            unique.append(q)
            if len(unique) >= max_count:
                break

        return unique if unique else [query]

    async def _step_back_transform(
        self,
        query: str,
        include_original: bool = True,
    ) -> list[str]:
        """
        Step-back transformation: Generate a more general query.

        This helps when the original query is too specific.
        """
        if self.llm is None:
            logger.warning("Step-back requires LLM, falling back to original query")
            return [query]

        try:
            prompt = STEP_BACK_PROMPT.format(query=query)
            response = await self.llm.acomplete(prompt)
            step_back_query = response.text.strip()

            if not step_back_query:
                return [query]

            queries = [step_back_query]
            if include_original:
                queries.append(query)

            logger.debug(f"Step-back generated: {step_back_query[:50]}...")
            return queries

        except Exception as e:
            logger.warning(f"Step-back transformation failed: {e}")
            return [query]


def get_query_transformer(
    llm: LLM | None = None,
    transform_type: QueryTransformType | str | None = None,
) -> QueryTransformer:
    """
    Get a configured query transformer.

    Args:
        llm: Optional LLM for advanced transformations
        transform_type: Transformation type

    Returns:
        Configured QueryTransformer
    """
    return QueryTransformer(llm=llm, transform_type=transform_type)
