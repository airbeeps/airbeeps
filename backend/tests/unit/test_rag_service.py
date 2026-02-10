"""
Unit tests for the LlamaIndex-based RAG service.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from airbeeps.rag.service import RAGService, RetrievalResult


class TestRetrievalResult:
    """Tests for RetrievalResult dataclass."""

    def test_create_retrieval_result(self):
        """Test creating a RetrievalResult."""
        result = RetrievalResult(
            content="Test content",
            score=0.95,
            metadata={"key": "value"},
            node_id="node-1",
            document_id="doc-1",
            chunk_id="chunk-1",
            title="Test Document",
        )

        assert result.content == "Test content"
        assert result.score == 0.95
        assert result.metadata == {"key": "value"}
        assert result.node_id == "node-1"
        assert result.document_id == "doc-1"
        assert result.chunk_id == "chunk-1"
        assert result.title == "Test Document"

    def test_retrieval_result_defaults(self):
        """Test RetrievalResult default values."""
        result = RetrievalResult(content="Test", score=0.5)

        assert result.metadata == {}
        assert result.node_id is None
        assert result.document_id is None
        assert result.chunk_id is None
        assert result.title is None
        assert result.retrieval_sources == []


class TestRAGServiceFileTypeInference:
    """Tests for file type inference."""

    @pytest.fixture
    def rag_service(self):
        """Create a RAG service with mocked session."""
        mock_session = MagicMock()
        return RAGService(session=mock_session)

    def test_infer_pdf_type(self, rag_service):
        """Test PDF file type inference."""
        assert rag_service._infer_file_type("document.pdf", None) == "pdf"
        assert rag_service._infer_file_type(None, "/path/to/file.PDF") == "pdf"

    def test_infer_excel_types(self, rag_service):
        """Test Excel file type inference."""
        assert rag_service._infer_file_type("data.xlsx", None) == "xlsx"
        assert rag_service._infer_file_type("data.xls", None) == "xls"
        assert rag_service._infer_file_type("data.csv", None) == "csv"

    def test_infer_text_types(self, rag_service):
        """Test text file type inference."""
        assert rag_service._infer_file_type("readme.txt", None) == "txt"
        assert rag_service._infer_file_type("readme.md", None) == "md"
        assert rag_service._infer_file_type("doc.docx", None) == "docx"

    def test_infer_unknown_type(self, rag_service):
        """Test unknown file type returns None."""
        assert rag_service._infer_file_type("file.xyz", None) is None
        assert rag_service._infer_file_type(None, None) is None


class TestRAGServiceRowToText:
    """Tests for tabular row to text conversion."""

    @pytest.fixture
    def rag_service(self):
        """Create a RAG service with mocked session."""
        mock_session = MagicMock()
        return RAGService(session=mock_session)

    def test_row_to_text_basic(self, rag_service):
        """Test basic row to text conversion."""
        import pandas as pd

        row = pd.Series({"Name": "John", "Age": 30, "City": "NYC"})
        columns = pd.Index(["Name", "Age", "City"])

        result = rag_service._row_to_text(row, columns, clean_data=False)

        assert "Name: John" in result
        assert "Age: 30" in result
        assert "City: NYC" in result

    def test_row_to_text_with_nan(self, rag_service):
        """Test row to text with NaN values."""
        import pandas as pd

        row = pd.Series({"Name": "John", "Age": float("nan"), "City": "NYC"})
        columns = pd.Index(["Name", "Age", "City"])

        result = rag_service._row_to_text(row, columns, clean_data=False)

        assert "Name: John" in result
        assert "Age" not in result  # NaN should be skipped
        assert "City: NYC" in result

    def test_row_to_text_integer_float(self, rag_service):
        """Test that integer floats are converted to int strings."""
        import pandas as pd

        row = pd.Series({"Count": 5.0, "Price": 19.99})
        columns = pd.Index(["Count", "Price"])

        result = rag_service._row_to_text(row, columns, clean_data=False)

        assert "Count: 5" in result  # 5.0 -> "5"
        assert "Price: 19.99" in result


class TestRAGServiceIntegration:
    """Integration tests for RAG service (requires mocking)."""

    @pytest.fixture
    def mock_kb(self):
        """Create a mock knowledge base."""
        kb = MagicMock()
        kb.id = uuid.uuid4()
        kb.name = "Test KB"
        kb.status = "ACTIVE"
        kb.embedding_model_id = uuid.uuid4()
        kb.vector_store_type = "qdrant"
        kb.chunk_size = 512
        kb.chunk_overlap = 50
        return kb

    @pytest.mark.asyncio
    async def test_get_knowledge_base_not_found(self):
        """Test getting non-existent knowledge base."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        service = RAGService(session=mock_session)
        result = await service.get_knowledge_base(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_relevance_search_kb_not_found(self):
        """Test relevance search with non-existent KB."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        service = RAGService(session=mock_session)

        with pytest.raises(ValueError, match="Knowledge base not found"):
            await service.relevance_search(
                query="test query",
                knowledge_base_id=uuid.uuid4(),
            )
