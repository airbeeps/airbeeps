"""
Multi-Hop Retrieval for Complex Queries.

Chains multiple retrieval steps, using results from each step
to inform the next query. Useful for complex reasoning tasks.
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from llama_index.core.llms import LLM

logger = logging.getLogger(__name__)


# Prompt templates
NEEDS_MORE_INFO_PROMPT = """Given the original question and the information retrieved so far, determine if we need to retrieve more information.

Original question: {query}

Information retrieved:
{retrieved_info}

Do we have enough information to fully answer the original question?
Consider:
- Are there unanswered aspects of the question?
- Do we need more specific details?
- Are there related topics we should explore?

Respond with:
NEED_MORE: YES or NO
REASON: brief explanation
FOLLOW_UP: if YES, the specific follow-up query to search for
"""

GENERATE_FOLLOW_UP_PROMPT = """Based on the original question and retrieved information, generate a follow-up query to find missing information.

Original question: {query}

Retrieved so far:
{retrieved_info}

Generate a focused follow-up query that:
- Addresses gaps in the current information
- Builds on what we already know
- Helps complete the answer

Follow-up query (just the query):
"""

SYNTHESIZE_HOPS_PROMPT = """Synthesize information from multiple retrieval steps into a coherent answer.

Original question: {query}

Retrieved information from {num_hops} searches:

{all_results}

Provide a comprehensive answer that:
- Integrates information from all searches
- Addresses the original question completely
- Notes any remaining gaps

Synthesized answer:
"""


@dataclass
class HopResult:
    """Result from a single hop."""

    hop_number: int
    query: str
    results: list[Any] = field(default_factory=list)
    num_results: int = 0


@dataclass
class MultiHopResult:
    """Result from multi-hop retrieval."""

    original_query: str
    hops: list[HopResult] = field(default_factory=list)
    all_results: list[Any] = field(default_factory=list)
    synthesized_answer: str | None = None
    total_hops: int = 0
    success: bool = True


class MultiHopRetriever:
    """
    Multi-hop retrieval for complex queries.

    Chains multiple retrievals where each step can:
    - Use results from previous steps
    - Generate follow-up queries based on gaps
    - Build comprehensive context across hops
    """

    def __init__(
        self,
        llm: LLM | None = None,
        max_hops: int = 3,
        results_per_hop: int = 3,
        synthesize_results: bool = True,
    ):
        """
        Initialize multi-hop retriever.

        Args:
            llm: LlamaIndex LLM for follow-up generation
            max_hops: Maximum number of retrieval hops
            results_per_hop: Results to keep per hop
            synthesize_results: Whether to synthesize final answer
        """
        self.llm = llm
        self.max_hops = max_hops
        self.results_per_hop = results_per_hop
        self.synthesize_results = synthesize_results

    async def needs_more_info(
        self, query: str, retrieved_info: str
    ) -> tuple[bool, str | None]:
        """
        Determine if we need more information.

        Args:
            query: Original query
            retrieved_info: Information retrieved so far

        Returns:
            Tuple of (needs_more, follow_up_query)
        """
        if not self.llm:
            # Without LLM, use simple heuristics
            return False, None

        try:
            prompt = NEEDS_MORE_INFO_PROMPT.format(
                query=query, retrieved_info=retrieved_info
            )
            response = await self.llm.acomplete(prompt)
            text = response.text.upper()

            needs_more = "NEED_MORE: YES" in text or "NEED_MORE:YES" in text

            # Extract follow-up query
            follow_up = None
            if needs_more:
                import re

                match = re.search(
                    r"FOLLOW_UP:\s*(.+?)(?:\n|$)", response.text, re.IGNORECASE
                )
                if match:
                    follow_up = match.group(1).strip()

            return needs_more, follow_up

        except Exception as e:
            logger.warning(f"Needs more info check failed: {e}")
            return False, None

    async def generate_follow_up(
        self, query: str, retrieved_info: str, hop_number: int
    ) -> str | None:
        """
        Generate a follow-up query based on current results.

        Args:
            query: Original query
            retrieved_info: Information retrieved so far
            hop_number: Current hop number

        Returns:
            Follow-up query or None
        """
        if not self.llm:
            return None

        try:
            prompt = GENERATE_FOLLOW_UP_PROMPT.format(
                query=query, retrieved_info=retrieved_info
            )
            response = await self.llm.acomplete(prompt)
            follow_up = response.text.strip()

            # Clean up
            if follow_up.startswith('"') and follow_up.endswith('"'):
                follow_up = follow_up[1:-1]

            return follow_up if follow_up else None

        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
            return None

    def _format_results_for_context(self, results: list[Any]) -> str:
        """Format results for context in prompts."""
        parts = []
        for i, r in enumerate(results, 1):
            content = ""
            if hasattr(r, "content"):
                content = r.content
            elif isinstance(r, dict) and "content" in r:
                content = r["content"]
            elif isinstance(r, str):
                content = r

            if content:
                # Truncate for prompt efficiency
                parts.append(f"[{i}] {content[:400]}...")

        return "\n\n".join(parts) if parts else "No results"

    async def synthesize_all_results(
        self, query: str, hops: list[HopResult]
    ) -> str | None:
        """
        Synthesize results from all hops into a final answer.

        Args:
            query: Original query
            hops: All hop results

        Returns:
            Synthesized answer
        """
        if not self.llm:
            return None

        try:
            # Format all results by hop
            all_results_text = []
            for hop in hops:
                hop_text = f"Search {hop.hop_number}: '{hop.query}'\n"
                hop_text += self._format_results_for_context(hop.results)
                all_results_text.append(hop_text)

            prompt = SYNTHESIZE_HOPS_PROMPT.format(
                query=query,
                num_hops=len(hops),
                all_results="\n\n---\n\n".join(all_results_text),
            )
            response = await self.llm.acomplete(prompt)
            return response.text.strip()

        except Exception as e:
            logger.warning(f"Multi-hop synthesis failed: {e}")
            return None

    async def retrieve_multi_hop(
        self,
        query: str,
        kb_id: UUID,
        retrieval_func: Any,
        top_k: int = 5,
    ) -> MultiHopResult:
        """
        Perform multi-hop retrieval.

        Args:
            query: Original query
            kb_id: Knowledge base ID
            retrieval_func: Async function for retrieval
            top_k: Results per hop

        Returns:
            MultiHopResult with all hops and synthesized answer
        """
        hops: list[HopResult] = []
        all_results: list[Any] = []
        current_query = query
        seen_node_ids: set[str] = set()

        for hop_num in range(1, self.max_hops + 1):
            logger.info(f"Multi-hop {hop_num}/{self.max_hops}: {current_query[:50]}...")

            try:
                # Retrieve for current query
                results = await retrieval_func(
                    query=current_query,
                    knowledge_base_id=kb_id,
                    k=top_k,
                )

                # Deduplicate results
                unique_results = []
                for r in results:
                    node_id = None
                    if hasattr(r, "node_id"):
                        node_id = r.node_id
                    elif isinstance(r, dict) and "node_id" in r:
                        node_id = r["node_id"]

                    if node_id and node_id in seen_node_ids:
                        continue

                    if node_id:
                        seen_node_ids.add(node_id)

                    unique_results.append(r)

                hop_result = HopResult(
                    hop_number=hop_num,
                    query=current_query,
                    results=unique_results[: self.results_per_hop],
                    num_results=len(unique_results),
                )
                hops.append(hop_result)
                all_results.extend(unique_results[: self.results_per_hop])

                # Check if we need more information
                if hop_num < self.max_hops:
                    retrieved_info = self._format_results_for_context(all_results)
                    needs_more, follow_up = await self.needs_more_info(
                        query, retrieved_info
                    )

                    if not needs_more:
                        logger.info(f"Multi-hop complete after {hop_num} hops")
                        break

                    # Generate follow-up query
                    if follow_up:
                        current_query = follow_up
                    else:
                        follow_up = await self.generate_follow_up(
                            query, retrieved_info, hop_num
                        )
                        if follow_up:
                            current_query = follow_up
                        else:
                            break

            except Exception as e:
                logger.warning(f"Multi-hop {hop_num} failed: {e}")
                break

        # Synthesize final answer
        synthesized_answer = None
        if self.synthesize_results and hops:
            synthesized_answer = await self.synthesize_all_results(query, hops)

        return MultiHopResult(
            original_query=query,
            hops=hops,
            all_results=all_results,
            synthesized_answer=synthesized_answer,
            total_hops=len(hops),
            success=len(all_results) > 0,
        )


async def get_multi_hop_retriever(
    llm: LLM | None = None,
    max_hops: int = 3,
) -> MultiHopRetriever:
    """
    Get a configured multi-hop retriever.

    Args:
        llm: Optional LLM for follow-up generation
        max_hops: Maximum retrieval hops

    Returns:
        Configured MultiHopRetriever
    """
    return MultiHopRetriever(llm=llm, max_hops=max_hops)
