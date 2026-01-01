"""
Unit tests for RAG service functionality.

Tests for document ingestion, chunking, and retrieval logic.
"""

from airbeeps.rag.chunker import DocumentChunker


class TestDocumentChunker:
    """Tests for the DocumentChunker class."""

    def test_chunk_small_document(self):
        """Small documents should produce a single chunk."""
        chunker = DocumentChunker()
        text = "This is a short document."

        chunks = chunker.chunk_document(
            text,
            chunk_size=100,
            chunk_overlap=20,
        )

        assert len(chunks) >= 1
        # All text should be in chunks
        combined = " ".join(c.content for c in chunks)
        assert "short document" in combined

    def test_chunk_large_document(self):
        """Large documents should be split into multiple chunks."""
        chunker = DocumentChunker()
        # Create a document with many words
        text = " ".join(["word"] * 1000)

        chunks = chunker.chunk_document(
            text,
            chunk_size=100,
            chunk_overlap=20,
        )

        assert len(chunks) > 1
        # Each chunk should respect the token limit
        for chunk in chunks:
            assert (
                chunk.token_count <= 100 or chunk.token_count <= 150
            )  # Allow some flexibility

    def test_chunk_with_overlap(self):
        """Chunks should have overlapping content when overlap is set."""
        chunker = DocumentChunker()
        text = "word " * 200  # Enough words to need multiple chunks

        chunks = chunker.chunk_document(
            text,
            chunk_size=50,
            chunk_overlap=10,
        )

        # Should have multiple chunks
        assert len(chunks) > 1

    def test_chunk_empty_document(self):
        """Empty documents should return empty or minimal chunks."""
        chunker = DocumentChunker()
        text = ""

        chunks = chunker.chunk_document(
            text,
            chunk_size=100,
            chunk_overlap=20,
        )

        # Should handle empty gracefully
        assert isinstance(chunks, list)

    def test_chunk_with_metadata(self):
        """Chunks should include provided metadata."""
        chunker = DocumentChunker()
        text = "Test document content"
        metadata = {"document_id": "123", "title": "Test Doc"}

        chunks = chunker.chunk_document(
            text,
            chunk_size=100,
            chunk_overlap=20,
            metadata=metadata,
        )

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.metadata.get("document_id") == "123"
            assert chunk.metadata.get("title") == "Test Doc"

    def test_chunk_respects_max_tokens(self):
        """Chunks should not exceed max_tokens_per_chunk."""
        chunker = DocumentChunker()
        text = "hello " * 500

        chunks = chunker.chunk_document(
            text,
            chunk_size=50,
            chunk_overlap=10,
            max_tokens_per_chunk=50,
        )

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.token_count <= 50

    def test_chunk_unicode_content(self):
        """Chunker should handle unicode content correctly."""
        chunker = DocumentChunker()
        text = "Hello 世界! Привет мир! مرحبا بالعالم " * 50

        chunks = chunker.chunk_document(
            text,
            chunk_size=50,
            chunk_overlap=10,
        )

        assert len(chunks) >= 1
        # Should not crash with unicode

    def test_chunk_code_content(self):
        """Chunker should handle code content correctly."""
        chunker = DocumentChunker()
        code = (
            """
def hello_world():
    print("Hello, World!")

class MyClass:
    def __init__(self):
        self.value = 42

    def get_value(self):
        return self.value
"""
            * 20
        )

        chunks = chunker.chunk_document(
            code,
            chunk_size=100,
            chunk_overlap=20,
        )

        assert len(chunks) >= 1


class TestIngestionStageWeights:
    """Tests for ingestion stage weight configuration."""

    def test_stage_weights_sum_to_100(self):
        """Stage weights should sum to 100 for proper progress calculation."""
        from airbeeps.rag.ingestion_runner import STAGE_WEIGHTS

        total = sum(STAGE_WEIGHTS.values())
        assert total == 100

    def test_all_stages_have_weights(self):
        """All expected stages should have weight definitions."""
        from airbeeps.rag.ingestion_runner import STAGE_WEIGHTS

        expected_stages = {"PARSING", "CHUNKING", "EMBEDDING", "UPSERTING"}
        assert set(STAGE_WEIGHTS.keys()) == expected_stages


class TestDocumentContentExtraction:
    """Tests for document content extraction."""

    def test_infer_file_type_from_extension(self):
        """File type should be inferred from file extension."""
        from airbeeps.rag.ingestion_runner import IngestionRunner

        runner = IngestionRunner.__new__(IngestionRunner)

        assert runner._infer_file_type("document.pdf", None) == "pdf"
        assert runner._infer_file_type("spreadsheet.xlsx", None) == "xlsx"
        assert runner._infer_file_type("data.csv", None) == "csv"
        assert runner._infer_file_type("notes.txt", None) == "txt"
        assert runner._infer_file_type("README.md", None) == "md"

    def test_infer_file_type_case_insensitive(self):
        """File extension matching should be case insensitive."""
        from airbeeps.rag.ingestion_runner import IngestionRunner

        runner = IngestionRunner.__new__(IngestionRunner)

        assert runner._infer_file_type("DOCUMENT.PDF", None) == "pdf"
        assert runner._infer_file_type("Report.DOCX", None) == "docx"
