"""
Query Planner for Agentic RAG.

LLM-based decomposition of complex queries into sub-queries
that can be executed in parallel and synthesized.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from llama_index.core.llms import LLM

logger = logging.getLogger(__name__)


# Prompt templates
QUERY_DECOMPOSITION_PROMPT = """You are a query planning assistant. Your task is to break down complex queries into simpler sub-queries that can be answered independently.

Given a complex question, decompose it into 2-5 simpler sub-questions that:
1. Can be answered independently
2. Together provide all information needed to answer the original question
3. Are specific and focused

Original query: {query}

Output each sub-query on a separate line. Do not number them or add prefixes.
If the query is already simple and doesn't need decomposition, output just the original query.

Sub-queries:
"""

SYNTHESIS_PROMPT = """You are a research synthesis assistant. Given a complex question and answers to related sub-questions, synthesize a comprehensive answer.

Original question: {query}

Sub-questions and their answers:
{sub_results}

Based on the information gathered, provide a comprehensive answer to the original question.
If some sub-questions couldn't be answered, acknowledge gaps in the information.

Synthesized answer:
"""

SHOULD_DECOMPOSE_PROMPT = """Analyze whether this query needs to be decomposed into sub-queries.

Query: {query}

A query should be decomposed if it:
- Compares multiple entities
- Asks about multiple aspects
- Requires information from different topics
- Is a complex multi-part question

Respond with only "YES" or "NO".
"""


@dataclass
class SubQueryResult:
    """Result from a sub-query execution."""

    sub_query: str
    results: list[Any] = field(default_factory=list)
    error: str | None = None
    success: bool = True


@dataclass
class QueryPlanResult:
    """Result from query planning and execution."""

    original_query: str
    sub_queries: list[str]
    sub_results: list[SubQueryResult]
    synthesized_answer: str | None = None
    was_decomposed: bool = False
    total_results: int = 0


class QueryPlanner:
    """
    Plans and executes complex queries by decomposing them into sub-queries.

    This enables "agentic" RAG where the system can:
    - Decompose complex questions into simpler parts
    - Execute sub-queries in parallel
    - Synthesize results into a coherent answer
    """

    def __init__(
        self,
        llm: LLM | None = None,
        max_sub_queries: int = 5,
        auto_detect_decomposition: bool = True,
    ):
        """
        Initialize the query planner.

        Args:
            llm: LlamaIndex LLM for query decomposition
            max_sub_queries: Maximum number of sub-queries to generate
            auto_detect_decomposition: Auto-detect if decomposition is needed
        """
        self.llm = llm
        self.max_sub_queries = max_sub_queries
        self.auto_detect = auto_detect_decomposition

    async def should_decompose(self, query: str) -> bool:
        """
        Determine if a query should be decomposed.

        Uses LLM to detect complex queries, falls back to heuristics.
        """
        # Quick heuristic checks first
        if len(query.split()) < 5:
            return False

        # Check for comparison keywords
        comparison_keywords = [
            "compare",
            "difference",
            "vs",
            "versus",
            "between",
            "both",
            "either",
        ]
        if any(kw in query.lower() for kw in comparison_keywords):
            return True

        # Check for multi-part indicators
        if " and " in query.lower() and "?" in query:
            return True

        # Use LLM for sophisticated detection
        if self.llm and self.auto_detect:
            try:
                prompt = SHOULD_DECOMPOSE_PROMPT.format(query=query)
                response = await self.llm.acomplete(prompt)
                return "yes" in response.text.lower()
            except Exception as e:
                logger.warning(f"LLM decomposition check failed: {e}")

        return False

    async def decompose_query(self, query: str) -> list[str]:
        """
        Decompose a complex query into sub-queries.

        Args:
            query: Complex query to decompose

        Returns:
            List of sub-queries
        """
        if not self.llm:
            logger.warning("No LLM available for query decomposition")
            return [query]

        try:
            prompt = QUERY_DECOMPOSITION_PROMPT.format(query=query)
            response = await self.llm.acomplete(prompt)

            # Parse response lines
            lines = [line.strip() for line in response.text.strip().split("\n")]
            sub_queries = [
                line
                for line in lines
                if line and len(line) > 10 and not line.startswith("-")
            ]

            # Clean up numbering if present
            cleaned = []
            for sq in sub_queries:
                # Remove numbering patterns like "1.", "1)", "a.", etc.
                cleaned_sq = re.sub(r"^[\d]+[.)]\s*", "", sq)
                cleaned_sq = re.sub(r"^[a-z][.)]\s*", "", cleaned_sq)
                if cleaned_sq:
                    cleaned.append(cleaned_sq)

            # Limit to max_sub_queries
            if cleaned:
                return cleaned[: self.max_sub_queries]

            return [query]

        except Exception as e:
            logger.warning(f"Query decomposition failed: {e}")
            return [query]

    async def plan_query(self, query: str) -> tuple[list[str], bool]:
        """
        Plan query execution.

        Returns:
            Tuple of (sub_queries, was_decomposed)
        """
        # Check if decomposition is needed
        needs_decomposition = await self.should_decompose(query)

        if needs_decomposition:
            sub_queries = await self.decompose_query(query)
            # If we got more than one sub-query, decomposition was used
            was_decomposed = len(sub_queries) > 1
            return sub_queries, was_decomposed

        return [query], False

    async def execute_plan(
        self,
        query: str,
        kb_id: UUID,
        retrieval_func: Any,
        top_k: int = 5,
    ) -> QueryPlanResult:
        """
        Execute a query plan: decompose, retrieve, synthesize.

        Args:
            query: Original query
            kb_id: Knowledge base ID
            retrieval_func: Async function to call for retrieval
            top_k: Results per sub-query

        Returns:
            QueryPlanResult with sub-queries and synthesized answer
        """
        # Plan the query
        sub_queries, was_decomposed = await self.plan_query(query)

        logger.info(
            f"Query plan: {len(sub_queries)} sub-queries, decomposed={was_decomposed}"
        )

        # Execute sub-queries in parallel
        async def execute_sub_query(sq: str) -> SubQueryResult:
            try:
                results = await retrieval_func(
                    query=sq,
                    knowledge_base_id=kb_id,
                    k=top_k,
                )
                return SubQueryResult(sub_query=sq, results=results, success=True)
            except Exception as e:
                logger.warning(f"Sub-query failed: {sq[:50]}... - {e}")
                return SubQueryResult(
                    sub_query=sq, error=str(e), success=False, results=[]
                )

        sub_results = await asyncio.gather(
            *[execute_sub_query(sq) for sq in sub_queries]
        )

        # Count total results
        total_results = sum(len(sr.results) for sr in sub_results)

        # Synthesize if we decomposed
        synthesized_answer = None
        if was_decomposed and self.llm and total_results > 0:
            synthesized_answer = await self._synthesize_results(
                query, list(sub_results)
            )

        return QueryPlanResult(
            original_query=query,
            sub_queries=sub_queries,
            sub_results=list(sub_results),
            synthesized_answer=synthesized_answer,
            was_decomposed=was_decomposed,
            total_results=total_results,
        )

    async def _synthesize_results(
        self, query: str, sub_results: list[SubQueryResult]
    ) -> str | None:
        """Synthesize sub-query results into a coherent answer."""
        if not self.llm:
            return None

        try:
            # Format sub-results for the prompt
            sub_results_text = []
            for sr in sub_results:
                if sr.success and sr.results:
                    # Get content from results
                    contents = []
                    for r in sr.results[:3]:  # Limit to top 3 per sub-query
                        if hasattr(r, "content"):
                            contents.append(r.content[:500])
                        elif isinstance(r, dict) and "content" in r:
                            contents.append(r["content"][:500])
                        elif isinstance(r, str):
                            contents.append(r[:500])

                    answer = "\n".join(contents) if contents else "No results found"
                    sub_results_text.append(f"Q: {sr.sub_query}\nA: {answer}")
                else:
                    sub_results_text.append(
                        f"Q: {sr.sub_query}\nA: Could not retrieve information"
                    )

            prompt = SYNTHESIS_PROMPT.format(
                query=query, sub_results="\n\n".join(sub_results_text)
            )

            response = await self.llm.acomplete(prompt)
            return response.text.strip()

        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            return None


async def get_query_planner(llm: LLM | None = None) -> QueryPlanner:
    """
    Get a configured query planner.

    Args:
        llm: Optional LLM for decomposition

    Returns:
        Configured QueryPlanner
    """
    return QueryPlanner(llm=llm)
