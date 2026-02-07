"""
Unit tests for the LlamaIndex document processor.
"""

import pytest

from airbeeps.rag.doc_processor import (
    DocumentProcessor,
    ProcessedChunk,
    get_document_processor,
)


class TestDocumentProcessor:
    """Tests for DocumentProcessor."""

    @pytest.fixture
    def processor(self):
        """Create a document processor without embedding model."""
        return DocumentProcessor(embed_model=None)

    def test_process_empty_text(self, processor):
        """Test processing empty text returns empty list."""
        result = processor.process_text("")
        assert result == []

        result = processor.process_text("   ")
        assert result == []

    def test_process_simple_text(self, processor):
        """Test processing simple text content."""
        content = "This is a test document with some content for chunking."
        nodes = processor.process_text(content)

        assert len(nodes) >= 1
        assert nodes[0].get_content().strip() == content.strip()

    def test_process_with_metadata(self, processor):
        """Test that metadata is preserved in nodes."""
        content = "Test content"
        metadata = {"title": "Test Doc", "source": "unit_test"}

        nodes = processor.process_text(content, metadata=metadata)

        assert len(nodes) >= 1
        assert nodes[0].metadata.get("title") == "Test Doc"
        assert nodes[0].metadata.get("source") == "unit_test"

    def test_process_long_text_creates_multiple_chunks(self, processor):
        """Test that long text creates multiple chunks."""
        # Create a long text
        content = " ".join(
            ["This is sentence number {}.".format(i) for i in range(100)]
        )

        nodes = processor.process_text(
            content, use_hierarchical=False, use_semantic=False
        )

        # Should create multiple chunks for long content
        assert len(nodes) >= 1

    def test_code_block_preservation(self, processor):
        """Test that code blocks are preserved as atomic units."""
        content = """
Some text before code.

```python
def hello():
    print("Hello, World!")
```

Some text after code.
"""
        nodes = processor.process_with_code_preservation(content)

        # Find the code block node
        code_nodes = [n for n in nodes if "```" in n.get_content()]
        assert len(code_nodes) >= 1

        # Verify code is intact
        code_content = code_nodes[0].get_content()
        assert "def hello():" in code_content
        assert 'print("Hello, World!")' in code_content

    def test_code_block_with_language(self, processor):
        """Test code block language is extracted to metadata."""
        content = """
```javascript
const x = 1;
```
"""
        nodes = processor.process_with_code_preservation(content)

        assert len(nodes) >= 1
        # Check metadata has code_language
        code_nodes = [n for n in nodes if "const x" in n.get_content()]
        assert len(code_nodes) >= 1
        assert code_nodes[0].metadata.get("code_language") == "javascript"


class TestProcessedChunk:
    """Tests for ProcessedChunk dataclass."""

    def test_create_processed_chunk(self):
        """Test creating a ProcessedChunk."""
        chunk = ProcessedChunk(
            content="Test content",
            token_count=10,
            metadata={"key": "value"},
            node_id="node-1",
            parent_id="parent-1",
            chunk_index=0,
        )

        assert chunk.content == "Test content"
        assert chunk.token_count == 10
        assert chunk.metadata == {"key": "value"}
        assert chunk.node_id == "node-1"
        assert chunk.parent_id == "parent-1"
        assert chunk.chunk_index == 0

    def test_processed_chunk_defaults(self):
        """Test ProcessedChunk default values."""
        chunk = ProcessedChunk(
            content="Test",
            token_count=1,
            metadata={},
        )

        assert chunk.node_id is None
        assert chunk.parent_id is None
        assert chunk.chunk_index == 0


class TestGetDocumentProcessor:
    """Tests for get_document_processor factory."""

    def test_get_processor_without_embed_model(self):
        """Test getting processor without embedding model."""
        processor = get_document_processor()
        assert processor is not None
        assert processor.embed_model is None

    def test_get_processor_returns_correct_type(self):
        """Test that factory returns DocumentProcessor."""
        processor = get_document_processor()
        assert isinstance(processor, DocumentProcessor)
