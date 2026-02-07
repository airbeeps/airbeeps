"""
Self-RAG Pattern Implementation.

After retrieval, LLM judges the quality of results and can:
- Retry with rephrased query
- Request more context
- Flag low-confidence answers
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from llama_index.core.llms import LLM

logger = logging.getLogger(__name__)


# Prompt templates
RELEVANCE_JUDGEMENT_PROMPT = """You are a relevance judge. Given a query and retrieved documents, determine if the documents are relevant and sufficient to answer the query.

Query: {query}

Retrieved Documents:
{documents}

Evaluate the relevance:
1. Are the documents relevant to the query? (YES/NO)
2. Is there enough information to answer the query? (YES/PARTIAL/NO)
3. Confidence score (0-100)

Respond in this exact format:
RELEVANT: YES or NO
SUFFICIENT: YES or PARTIAL or NO
CONFIDENCE: number between 0-100
REASONING: brief explanation
"""

QUERY_REPHRASE_PROMPT = """The following query did not return relevant results. Rephrase it to improve retrieval.

Original query: {query}

Previous attempt feedback: {feedback}

Generate a rephrased query that:
- Uses different keywords
- Is more specific or more general as needed
- Focuses on the core information need

Rephrased query (just the query, no explanation):
"""

ANSWER_GENERATION_PROMPT = """Based on the retrieved context, generate an answer to the query.
If the context is insufficient, acknowledge limitations.

Query: {query}

Context:
{context}

Generate a helpful, accurate answer based only on the provided context.
If the context doesn't contain the answer, say so clearly.

Answer:
"""


@dataclass
class RelevanceJudgement:
    """Result of relevance judgement."""

    is_relevant: bool
    is_sufficient: str  # "YES", "PARTIAL", "NO"
    confidence: int  # 0-100
    reasoning: str = ""


@dataclass
class SelfRAGResult:
    """Result from Self-RAG retrieval."""

    query: str
    final_query: str  # May be different if rephrased
    results: list[Any] = field(default_factory=list)
    judgement: RelevanceJudgement | None = None
    attempts: int = 1
    generated_answer: str | None = None
    success: bool = True
    error: str | None = None


class SelfRAG:
    """
    Self-RAG: Retrieval with self-critique and adaptive retry.

    After initial retrieval, the LLM judges whether results are:
    - Relevant to the query
    - Sufficient to answer
    - High confidence

    If not, the system can:
    - Rephrase the query
    - Retry retrieval
    - Generate answer with caveats
    """

    def __init__(
        self,
        llm: LLM | None = None,
        max_attempts: int = 3,
        min_confidence: int = 50,
        generate_answer: bool = False,
    ):
        """
        Initialize Self-RAG.

        Args:
            llm: LlamaIndex LLM for judgement and rephrasing
            max_attempts: Maximum retrieval attempts
            min_confidence: Minimum confidence score to accept
            generate_answer: Whether to generate final answer
        """
        self.llm = llm
        self.max_attempts = max_attempts
        self.min_confidence = min_confidence
        self.generate_answer = generate_answer

    async def judge_relevance(
        self, query: str, results: list[Any]
    ) -> RelevanceJudgement:
        """
        Judge the relevance of retrieved results.

        Args:
            query: Original query
            results: Retrieved documents

        Returns:
            RelevanceJudgement with scores and reasoning
        """
        if not self.llm:
            # Without LLM, assume results are relevant if we have any
            return RelevanceJudgement(
                is_relevant=len(results) > 0,
                is_sufficient="YES" if len(results) >= 3 else "PARTIAL",
                confidence=70 if results else 0,
                reasoning="No LLM available for judgement",
            )

        try:
            # Format documents for prompt
            doc_texts = []
            for i, r in enumerate(results[:5], 1):  # Limit to 5 for prompt
                if hasattr(r, "content"):
                    doc_texts.append(f"[{i}] {r.content[:300]}...")
                elif isinstance(r, dict) and "content" in r:
                    doc_texts.append(f"[{i}] {r['content'][:300]}...")
                elif isinstance(r, str):
                    doc_texts.append(f"[{i}] {r[:300]}...")

            documents_text = "\n\n".join(doc_texts) if doc_texts else "No documents"

            prompt = RELEVANCE_JUDGEMENT_PROMPT.format(
                query=query, documents=documents_text
            )
            response = await self.llm.acomplete(prompt)
            text = response.text.upper()

            # Parse response
            is_relevant = "RELEVANT: YES" in text or "RELEVANT:YES" in text
            is_sufficient = "PARTIAL"
            if "SUFFICIENT: YES" in text or "SUFFICIENT:YES" in text:
                is_sufficient = "YES"
            elif "SUFFICIENT: NO" in text or "SUFFICIENT:NO" in text:
                is_sufficient = "NO"

            # Extract confidence
            confidence = 50
            import re

            conf_match = re.search(r"CONFIDENCE:\s*(\d+)", text)
            if conf_match:
                confidence = min(100, max(0, int(conf_match.group(1))))

            # Extract reasoning
            reasoning = ""
            reason_match = re.search(r"REASONING:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
            if reason_match:
                reasoning = reason_match.group(1).strip()

            return RelevanceJudgement(
                is_relevant=is_relevant,
                is_sufficient=is_sufficient,
                confidence=confidence,
                reasoning=reasoning,
            )

        except Exception as e:
            logger.warning(f"Relevance judgement failed: {e}")
            return RelevanceJudgement(
                is_relevant=len(results) > 0,
                is_sufficient="PARTIAL",
                confidence=50,
                reasoning=f"Judgement error: {e}",
            )

    async def rephrase_query(self, query: str, feedback: str = "") -> str:
        """
        Rephrase a query to improve retrieval.

        Args:
            query: Original query
            feedback: Feedback from previous attempt

        Returns:
            Rephrased query
        """
        if not self.llm:
            # Without LLM, make simple modifications
            # Try removing stop words or adding context
            return query

        try:
            prompt = QUERY_REPHRASE_PROMPT.format(
                query=query, feedback=feedback or "Results were not relevant"
            )
            response = await self.llm.acomplete(prompt)
            rephrased = response.text.strip()

            # Clean up the response
            if rephrased.startswith('"') and rephrased.endswith('"'):
                rephrased = rephrased[1:-1]

            return rephrased if rephrased else query

        except Exception as e:
            logger.warning(f"Query rephrase failed: {e}")
            return query

    async def generate_answer_from_context(self, query: str, results: list[Any]) -> str:
        """
        Generate an answer from retrieved context.

        Args:
            query: Original query
            results: Retrieved documents

        Returns:
            Generated answer
        """
        if not self.llm:
            # Without LLM, just concatenate results
            contents = []
            for r in results[:3]:
                if hasattr(r, "content"):
                    contents.append(r.content)
                elif isinstance(r, dict) and "content" in r:
                    contents.append(r["content"])
            return "\n\n".join(contents) if contents else "No information found"

        try:
            # Format context
            context_parts = []
            for r in results[:5]:
                if hasattr(r, "content"):
                    context_parts.append(r.content)
                elif isinstance(r, dict) and "content" in r:
                    context_parts.append(r["content"])
                elif isinstance(r, str):
                    context_parts.append(r)

            context = "\n\n---\n\n".join(context_parts) if context_parts else "None"

            prompt = ANSWER_GENERATION_PROMPT.format(query=query, context=context)
            response = await self.llm.acomplete(prompt)
            return response.text.strip()

        except Exception as e:
            logger.warning(f"Answer generation failed: {e}")
            return "Could not generate answer"

    async def retrieve_with_self_critique(
        self,
        query: str,
        kb_id: UUID,
        retrieval_func: Any,
        top_k: int = 5,
    ) -> SelfRAGResult:
        """
        Retrieve with self-critique and adaptive retry.

        Args:
            query: Search query
            kb_id: Knowledge base ID
            retrieval_func: Async function for retrieval
            top_k: Number of results

        Returns:
            SelfRAGResult with results and judgement
        """
        current_query = query
        last_feedback = ""

        for attempt in range(self.max_attempts):
            try:
                # Retrieve
                results = await retrieval_func(
                    query=current_query,
                    knowledge_base_id=kb_id,
                    k=top_k,
                )

                # Judge relevance
                judgement = await self.judge_relevance(current_query, results)

                logger.info(
                    f"Self-RAG attempt {attempt + 1}: "
                    f"relevant={judgement.is_relevant}, "
                    f"sufficient={judgement.is_sufficient}, "
                    f"confidence={judgement.confidence}"
                )

                # Check if we should accept results
                if (
                    judgement.is_relevant
                    and judgement.confidence >= self.min_confidence
                ):
                    # Generate answer if requested
                    generated_answer = None
                    if self.generate_answer and results:
                        generated_answer = await self.generate_answer_from_context(
                            query, results
                        )

                    return SelfRAGResult(
                        query=query,
                        final_query=current_query,
                        results=results,
                        judgement=judgement,
                        attempts=attempt + 1,
                        generated_answer=generated_answer,
                        success=True,
                    )

                # If not the last attempt, rephrase and retry
                if attempt < self.max_attempts - 1:
                    last_feedback = judgement.reasoning
                    current_query = await self.rephrase_query(query, last_feedback)
                    logger.debug(f"Rephrased query: {current_query}")

            except Exception as e:
                logger.warning(f"Self-RAG attempt {attempt + 1} failed: {e}")
                if attempt == self.max_attempts - 1:
                    return SelfRAGResult(
                        query=query,
                        final_query=current_query,
                        results=[],
                        attempts=attempt + 1,
                        success=False,
                        error=str(e),
                    )

        # Return best attempt results even if confidence is low
        return SelfRAGResult(
            query=query,
            final_query=current_query,
            results=results,
            judgement=judgement,
            attempts=self.max_attempts,
            success=len(results) > 0,
        )


async def get_self_rag(
    llm: LLM | None = None,
    max_attempts: int = 3,
    min_confidence: int = 50,
) -> SelfRAG:
    """
    Get a configured Self-RAG instance.

    Args:
        llm: Optional LLM for judgement
        max_attempts: Maximum retrieval attempts
        min_confidence: Minimum confidence threshold

    Returns:
        Configured SelfRAG
    """
    return SelfRAG(
        llm=llm,
        max_attempts=max_attempts,
        min_confidence=min_confidence,
    )
