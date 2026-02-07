"""
RAG Evaluator Module.

Provides evaluation metrics for RAG quality using RAGAS.
Supports:
- Faithfulness: Is the answer faithful to the retrieved context?
- Answer Relevancy: Is the answer relevant to the question?
- Context Recall: Were all relevant pieces of information retrieved?
- Context Precision: How precise is the retrieved context?
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from airbeeps.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of RAG evaluation."""

    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_recall: float | None = None
    context_precision: float | None = None

    # Aggregate score
    overall_score: float | None = None

    # Details
    num_samples: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "faithfulness": self.faithfulness,
            "answer_relevancy": self.answer_relevancy,
            "context_recall": self.context_recall,
            "context_precision": self.context_precision,
            "overall_score": self.overall_score,
            "num_samples": self.num_samples,
            "errors": self.errors,
            "metadata": self.metadata,
        }


@dataclass
class EvaluationSample:
    """A single evaluation sample."""

    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None


class RAGEvaluator:
    """
    RAG Evaluator using RAGAS metrics.

    Evaluates the quality of RAG responses across multiple dimensions.
    """

    def __init__(self, llm: Any | None = None, embeddings: Any | None = None):
        """
        Initialize the evaluator.

        Args:
            llm: LLM for evaluation (uses default if not provided)
            embeddings: Embedding model for semantic similarity
        """
        self.llm = llm
        self.embeddings = embeddings
        self._ragas_available = self._check_ragas()

    def _check_ragas(self) -> bool:
        """Check if RAGAS is available."""
        try:
            import ragas

            return True
        except ImportError:
            logger.warning("RAGAS not installed. Install with: pip install ragas")
            return False

    async def evaluate(
        self,
        samples: list[EvaluationSample],
        metrics: list[str] | None = None,
    ) -> EvaluationResult:
        """
        Evaluate RAG performance on a set of samples.

        Args:
            samples: List of evaluation samples
            metrics: Metrics to compute (default: all)

        Returns:
            EvaluationResult with computed metrics
        """
        if not samples:
            return EvaluationResult(errors=["No samples provided"])

        if not self._ragas_available:
            return await self._fallback_evaluation(samples)

        try:
            return await self._ragas_evaluation(samples, metrics)
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}", exc_info=True)
            return EvaluationResult(
                errors=[f"Evaluation failed: {str(e)}"],
                num_samples=len(samples),
            )

    async def _ragas_evaluation(
        self,
        samples: list[EvaluationSample],
        metrics: list[str] | None,
    ) -> EvaluationResult:
        """Run evaluation using RAGAS."""
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        # Build dataset
        data = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        }

        for sample in samples:
            data["question"].append(sample.question)
            data["answer"].append(sample.answer)
            data["contexts"].append(sample.contexts)
            data["ground_truth"].append(sample.ground_truth or "")

        dataset = Dataset.from_dict(data)

        # Select metrics
        available_metrics = {
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_recall": context_recall,
            "context_precision": context_precision,
        }

        if metrics:
            selected_metrics = [
                available_metrics[m] for m in metrics if m in available_metrics
            ]
        else:
            # Default: use metrics that don't require ground truth if not available
            has_ground_truth = any(s.ground_truth for s in samples)
            if has_ground_truth:
                selected_metrics = [
                    faithfulness,
                    answer_relevancy,
                    context_recall,
                    context_precision,
                ]
            else:
                selected_metrics = [faithfulness, answer_relevancy]

        # Run evaluation
        result = evaluate(dataset, metrics=selected_metrics)

        # Extract scores
        scores = result.to_pandas().mean().to_dict()

        eval_result = EvaluationResult(
            faithfulness=scores.get("faithfulness"),
            answer_relevancy=scores.get("answer_relevancy"),
            context_recall=scores.get("context_recall"),
            context_precision=scores.get("context_precision"),
            num_samples=len(samples),
        )

        # Compute overall score
        valid_scores = [
            s
            for s in [
                eval_result.faithfulness,
                eval_result.answer_relevancy,
                eval_result.context_recall,
                eval_result.context_precision,
            ]
            if s is not None
        ]
        if valid_scores:
            eval_result.overall_score = sum(valid_scores) / len(valid_scores)

        return eval_result

    async def _fallback_evaluation(
        self,
        samples: list[EvaluationSample],
    ) -> EvaluationResult:
        """
        Simple fallback evaluation when RAGAS is not available.

        Uses basic heuristics instead of LLM-based evaluation.
        """
        logger.info("Using fallback evaluation (RAGAS not available)")

        # Simple heuristics
        total_context_coverage = 0.0
        total_answer_length_ratio = 0.0

        for sample in samples:
            # Context coverage: how much of the answer words appear in context
            answer_words = set(sample.answer.lower().split())
            context_text = " ".join(sample.contexts).lower()
            context_words = set(context_text.split())

            if answer_words:
                coverage = len(answer_words & context_words) / len(answer_words)
                total_context_coverage += coverage

            # Answer relevance proxy: answer length relative to question
            q_len = len(sample.question.split())
            a_len = len(sample.answer.split())
            if q_len > 0:
                ratio = min(a_len / q_len, 5.0) / 5.0  # Cap at 5x question length
                total_answer_length_ratio += ratio

        n = len(samples)
        avg_coverage = total_context_coverage / n if n > 0 else 0
        avg_ratio = total_answer_length_ratio / n if n > 0 else 0

        return EvaluationResult(
            faithfulness=avg_coverage,  # Proxy for faithfulness
            answer_relevancy=avg_ratio,  # Proxy for relevancy
            overall_score=(avg_coverage + avg_ratio) / 2,
            num_samples=n,
            metadata={"evaluation_type": "fallback_heuristic"},
        )

    async def evaluate_single(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> EvaluationResult:
        """
        Evaluate a single RAG response.

        Args:
            question: The user's question
            answer: The generated answer
            contexts: Retrieved context passages
            ground_truth: Optional ground truth answer

        Returns:
            EvaluationResult
        """
        sample = EvaluationSample(
            question=question,
            answer=answer,
            contexts=contexts,
            ground_truth=ground_truth,
        )
        return await self.evaluate([sample])


def get_evaluator(
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> RAGEvaluator:
    """Get a configured RAG evaluator."""
    return RAGEvaluator(llm=llm, embeddings=embeddings)
