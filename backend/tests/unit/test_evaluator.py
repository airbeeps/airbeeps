"""
Unit tests for the RAG evaluator module.
"""

import pytest

from airbeeps.rag.evaluator import (
    EvaluationResult,
    EvaluationSample,
    RAGEvaluator,
    get_evaluator,
)


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_create_result(self):
        """Test creating an evaluation result."""
        result = EvaluationResult(
            faithfulness=0.85,
            answer_relevancy=0.90,
            context_recall=0.75,
            context_precision=0.80,
            overall_score=0.825,
            num_samples=10,
        )

        assert result.faithfulness == 0.85
        assert result.answer_relevancy == 0.90
        assert result.context_recall == 0.75
        assert result.context_precision == 0.80
        assert result.overall_score == 0.825
        assert result.num_samples == 10

    def test_result_defaults(self):
        """Test default values."""
        result = EvaluationResult()

        assert result.faithfulness is None
        assert result.answer_relevancy is None
        assert result.overall_score is None
        assert result.num_samples == 0
        assert result.errors == []
        assert result.metadata == {}

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = EvaluationResult(
            faithfulness=0.85,
            num_samples=5,
        )

        d = result.to_dict()

        assert d["faithfulness"] == 0.85
        assert d["num_samples"] == 5
        assert "errors" in d
        assert "metadata" in d


class TestEvaluationSample:
    """Tests for EvaluationSample dataclass."""

    def test_create_sample(self):
        """Test creating an evaluation sample."""
        sample = EvaluationSample(
            question="What is Python?",
            answer="Python is a programming language.",
            contexts=["Python is a high-level programming language."],
            ground_truth="Python is an interpreted programming language.",
        )

        assert sample.question == "What is Python?"
        assert sample.answer == "Python is a programming language."
        assert len(sample.contexts) == 1
        assert sample.ground_truth == "Python is an interpreted programming language."

    def test_sample_without_ground_truth(self):
        """Test sample without ground truth."""
        sample = EvaluationSample(
            question="Question",
            answer="Answer",
            contexts=["Context"],
        )

        assert sample.ground_truth is None


class TestRAGEvaluator:
    """Tests for RAGEvaluator."""

    @pytest.fixture
    def evaluator(self):
        """Create an evaluator."""
        return RAGEvaluator()

    @pytest.mark.asyncio
    async def test_evaluate_empty_samples(self, evaluator):
        """Test evaluating empty sample list."""
        result = await evaluator.evaluate([])

        assert result.num_samples == 0
        assert "No samples provided" in result.errors

    @pytest.mark.asyncio
    async def test_fallback_evaluation(self, evaluator):
        """Test fallback evaluation when RAGAS not available."""
        samples = [
            EvaluationSample(
                question="What is machine learning?",
                answer="Machine learning is a subset of AI.",
                contexts=["Machine learning uses algorithms to learn from data."],
            )
        ]

        result = await evaluator._fallback_evaluation(samples)

        assert result.num_samples == 1
        assert result.faithfulness is not None
        assert result.answer_relevancy is not None

    @pytest.mark.asyncio
    async def test_evaluate_single(self, evaluator):
        """Test evaluating a single sample."""
        result = await evaluator.evaluate_single(
            question="What is AI?",
            answer="AI stands for Artificial Intelligence.",
            contexts=[
                "Artificial Intelligence (AI) is the simulation of human intelligence."
            ],
        )

        assert result.num_samples == 1


class TestFallbackEvaluation:
    """Tests for fallback evaluation logic."""

    @pytest.fixture
    def evaluator(self):
        """Create an evaluator."""
        return RAGEvaluator()

    @pytest.mark.asyncio
    async def test_context_coverage_calculation(self, evaluator):
        """Test context coverage is calculated correctly."""
        # High coverage: answer words appear in context
        samples = [
            EvaluationSample(
                question="What is Python?",
                answer="Python is a programming language",
                contexts=[
                    "Python is a high-level programming language created by Guido"
                ],
            )
        ]

        result = await evaluator._fallback_evaluation(samples)

        # Most answer words should appear in context
        assert result.faithfulness > 0.5

    @pytest.mark.asyncio
    async def test_low_coverage(self, evaluator):
        """Test low coverage when answer doesn't match context."""
        samples = [
            EvaluationSample(
                question="What is the weather?",
                answer="It is sunny and warm today with clear skies",
                contexts=["The database schema includes users and posts tables"],
            )
        ]

        result = await evaluator._fallback_evaluation(samples)

        # Low overlap between answer and context
        assert result.faithfulness < 0.5


class TestGetEvaluator:
    """Tests for get_evaluator factory."""

    def test_creates_evaluator(self):
        """Test factory creates evaluator."""
        evaluator = get_evaluator()
        assert isinstance(evaluator, RAGEvaluator)
