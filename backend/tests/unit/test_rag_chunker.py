"""
Unit tests for RAG chunker functionality.
"""

from airbeeps.chat.prompt_builder import PromptBuilder
from airbeeps.chat.token_utils import get_default_token_counter
from airbeeps.rag.chunker import DocumentChunker


def test_chunker_respects_token_cap():
    chunker = DocumentChunker()
    text = "hello " * 300  # simple tokenizable text

    chunks = chunker.chunk_document(
        text,
        chunk_size=50,
        chunk_overlap=10,
        max_tokens_per_chunk=50,
    )

    assert chunks, "chunker should return at least one chunk"
    assert all(c.token_count <= 50 for c in chunks), "all chunks must honor token cap"


def test_chunker_truncates_long_chunk():
    chunker = DocumentChunker()
    long_text = "abc " * 150

    chunks = chunker.chunk_document(
        long_text,
        chunk_size=30,
        chunk_overlap=5,
        max_tokens_per_chunk=30,
    )
    assert chunks
    assert all(c.token_count <= 30 for c in chunks)


def test_truncate_to_tokens_helper_limits_tokens():
    text = "world " * 200
    truncated = PromptBuilder._truncate_to_tokens(text, 40)
    token_counter = get_default_token_counter()
    assert token_counter.count_text_tokens(truncated) <= 40
