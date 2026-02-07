"""
Document Processor for LlamaIndex.

Provides SOTA document processing with:
- Semantic chunking (splits by meaning, not fixed size)
- Hierarchical chunking (parent-child-leaf structure)
- Sentence-based fallback splitting
- Code block preservation
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.node_parser import (
    HierarchicalNodeParser,
    SentenceSplitter,
)
from llama_index.core.schema import (
    BaseNode,
    Document,
    NodeRelationship,
    TextNode,
)

from airbeeps.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProcessedChunk:
    """Represents a processed document chunk."""

    content: str
    token_count: int
    metadata: dict[str, Any]
    node_id: str | None = None
    parent_id: str | None = None
    chunk_index: int = 0


class DocumentProcessor:
    """
    SOTA Document Processor using LlamaIndex.

    Supports:
    - Semantic chunking: Splits based on embedding similarity
    - Hierarchical chunking: Creates parent-child chunk relationships
    - Sentence-based chunking: Fallback for when semantic isn't needed
    """

    def __init__(
        self,
        embed_model: BaseEmbedding | None = None,
        chunk_sizes: list[int] | None = None,
        breakpoint_threshold: int | None = None,
        buffer_size: int | None = None,
    ):
        """
        Initialize the document processor.

        Args:
            embed_model: LlamaIndex embedding model for semantic chunking
            chunk_sizes: Sizes for hierarchical chunks [parent, child, leaf]
            breakpoint_threshold: Percentile threshold for semantic splits
            buffer_size: Sentence buffer for context in semantic chunking
        """
        self.embed_model = embed_model
        self.chunk_sizes = chunk_sizes or settings.RAG_HIERARCHICAL_CHUNK_SIZES
        self.breakpoint_threshold = (
            breakpoint_threshold or settings.RAG_SEMANTIC_BREAKPOINT_THRESHOLD
        )
        self.buffer_size = buffer_size or settings.RAG_SEMANTIC_BUFFER_SIZE

        # Initialize parsers
        self._init_parsers()

    def _init_parsers(self) -> None:
        """Initialize the node parsers."""
        # Hierarchical parser for parent-child relationships
        self.hierarchical_parser = HierarchicalNodeParser.from_defaults(
            chunk_sizes=self.chunk_sizes,
        )

        # Sentence splitter as fallback
        self.sentence_splitter = SentenceSplitter(
            chunk_size=self.chunk_sizes[-1] if self.chunk_sizes else 512,
            chunk_overlap=50,
        )

        # Semantic splitter (initialized lazily when embed_model is available)
        self._semantic_splitter = None

    def _get_semantic_splitter(self):
        """Get or create semantic splitter."""
        if self._semantic_splitter is None and self.embed_model is not None:
            try:
                from llama_index.core.node_parser import SemanticSplitterNodeParser

                self._semantic_splitter = SemanticSplitterNodeParser(
                    buffer_size=self.buffer_size,
                    breakpoint_percentile_threshold=self.breakpoint_threshold,
                    embed_model=self.embed_model,
                )
            except ImportError:
                logger.warning(
                    "SemanticSplitterNodeParser not available, falling back to sentence splitter"
                )
        return self._semantic_splitter

    def process_text(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        use_semantic: bool | None = None,
        use_hierarchical: bool | None = None,
        strategy: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[BaseNode]:
        """
        Process text content into LlamaIndex nodes.

        Args:
            content: Text content to process
            metadata: Metadata to attach to nodes
            use_semantic: Use semantic chunking (defaults to settings)
            use_hierarchical: Use hierarchical chunking (defaults to settings)
            strategy: Override chunking strategy: auto|semantic|hierarchical|sentence
            chunk_size: Override chunk size
            chunk_overlap: Override chunk overlap

        Returns:
            List of LlamaIndex nodes
        """
        if not content or not content.strip():
            return []

        # Handle strategy override
        if strategy and strategy != "auto":
            use_semantic = strategy == "semantic"
            use_hierarchical = strategy == "hierarchical"
        else:
            use_semantic = (
                use_semantic
                if use_semantic is not None
                else settings.RAG_ENABLE_SEMANTIC_CHUNKING
            )
            use_hierarchical = (
                use_hierarchical
                if use_hierarchical is not None
                else settings.RAG_ENABLE_HIERARCHICAL
            )

        metadata = metadata or {}

        # Create a LlamaIndex Document
        document = Document(
            text=content,
            metadata=metadata,
        )

        # Process based on configuration
        if use_hierarchical:
            return self._process_hierarchical([document], chunk_size=chunk_size)
        elif use_semantic and self.embed_model is not None:
            return self._process_semantic([document])
        else:
            return self._process_sentence(
                [document], chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

    def process_documents(
        self,
        documents: list[Document],
        use_semantic: bool | None = None,
        use_hierarchical: bool | None = None,
    ) -> list[BaseNode]:
        """
        Process multiple LlamaIndex documents into nodes.

        Args:
            documents: List of LlamaIndex Document objects
            use_semantic: Use semantic chunking
            use_hierarchical: Use hierarchical chunking

        Returns:
            List of LlamaIndex nodes
        """
        if not documents:
            return []

        use_semantic = (
            use_semantic
            if use_semantic is not None
            else settings.RAG_ENABLE_SEMANTIC_CHUNKING
        )
        use_hierarchical = (
            use_hierarchical
            if use_hierarchical is not None
            else settings.RAG_ENABLE_HIERARCHICAL
        )

        if use_hierarchical:
            return self._process_hierarchical(documents)
        elif use_semantic and self.embed_model is not None:
            return self._process_semantic(documents)
        else:
            return self._process_sentence(documents)

    def _process_hierarchical(
        self,
        documents: list[Document],
        chunk_size: int | None = None,
    ) -> list[BaseNode]:
        """Process documents with hierarchical chunking."""
        logger.debug(f"Processing {len(documents)} documents with hierarchical parser")

        try:
            # Use custom chunk sizes if provided
            if chunk_size:
                # Create a temporary parser with custom sizes
                # For hierarchical, we scale the levels proportionally
                custom_sizes = [chunk_size * 4, chunk_size * 2, chunk_size]
                custom_parser = HierarchicalNodeParser.from_defaults(
                    chunk_sizes=custom_sizes,
                )
                nodes = custom_parser.get_nodes_from_documents(documents)
            else:
                nodes = self.hierarchical_parser.get_nodes_from_documents(documents)

            logger.info(
                f"Hierarchical processing produced {len(nodes)} nodes from {len(documents)} documents"
            )
            return nodes
        except Exception as e:
            logger.warning(
                f"Hierarchical parsing failed, falling back to sentence: {e}"
            )
            return self._process_sentence(documents, chunk_size=chunk_size)

    def _process_semantic(self, documents: list[Document]) -> list[BaseNode]:
        """Process documents with semantic chunking."""
        logger.debug(f"Processing {len(documents)} documents with semantic splitter")

        semantic_splitter = self._get_semantic_splitter()
        if semantic_splitter is None:
            logger.warning("Semantic splitter not available, falling back to sentence")
            return self._process_sentence(documents)

        try:
            nodes = semantic_splitter.get_nodes_from_documents(documents)
            logger.info(
                f"Semantic processing produced {len(nodes)} nodes from {len(documents)} documents"
            )
            return nodes
        except Exception as e:
            logger.warning(f"Semantic parsing failed, falling back to sentence: {e}")
            return self._process_sentence(documents)

    def _process_sentence(
        self,
        documents: list[Document],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[BaseNode]:
        """Process documents with sentence-based chunking."""
        logger.debug(f"Processing {len(documents)} documents with sentence splitter")

        # Use custom splitter if overrides provided
        if chunk_size or chunk_overlap:
            effective_size = chunk_size or (
                self.chunk_sizes[-1] if self.chunk_sizes else 512
            )
            effective_overlap = chunk_overlap if chunk_overlap is not None else 50
            custom_splitter = SentenceSplitter(
                chunk_size=effective_size,
                chunk_overlap=effective_overlap,
            )
            nodes = custom_splitter.get_nodes_from_documents(documents)
        else:
            nodes = self.sentence_splitter.get_nodes_from_documents(documents)

        logger.info(
            f"Sentence processing produced {len(nodes)} nodes from {len(documents)} documents"
        )
        return nodes

    def process_with_code_preservation(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[BaseNode]:
        """
        Process content while preserving code blocks as atomic units.

        Args:
            content: Text content with potential code blocks
            metadata: Metadata to attach to nodes

        Returns:
            List of nodes with code blocks preserved
        """
        metadata = metadata or {}
        segments = self._split_code_blocks(content)

        all_nodes: list[BaseNode] = []

        for seg_type, seg_text, seg_meta in segments:
            combined_meta = {**metadata, **seg_meta}

            if seg_type == "code":
                # Code blocks become single nodes
                node = TextNode(
                    text=seg_text,
                    metadata=combined_meta,
                )
                all_nodes.append(node)
            else:
                # Text segments get chunked normally
                doc = Document(text=seg_text, metadata=combined_meta)
                nodes = self._process_sentence([doc])
                all_nodes.extend(nodes)

        return all_nodes

    def _split_code_blocks(self, text: str) -> list[tuple[str, str, dict[str, Any]]]:
        """
        Split text into segments of ("code" | "text", content, metadata).

        Preserves fenced code blocks as atomic units.
        """
        segments: list[tuple[str, str, dict[str, Any]]] = []
        pattern = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
        last_idx = 0

        for match in pattern.finditer(text):
            start, end = match.span()
            if start > last_idx:
                pre_text = text[last_idx:start]
                if pre_text.strip():
                    segments.append(("text", pre_text, {}))

            lang = (match.group("lang") or "").strip()
            body = match.group("body") or ""
            code_with_fences = f"```{lang}\n{body}```"
            segments.append(
                (
                    "code",
                    code_with_fences,
                    {"code_language": lang if lang else "plain"},
                )
            )
            last_idx = end

        if last_idx < len(text):
            tail = text[last_idx:]
            if tail.strip():
                segments.append(("text", tail, {}))

        if not segments:
            segments.append(("text", text, {}))

        return segments

    def nodes_to_chunks(self, nodes: list[BaseNode]) -> list[ProcessedChunk]:
        """
        Convert LlamaIndex nodes to ProcessedChunk objects.

        Useful for compatibility with existing code that expects chunks.
        """
        chunks: list[ProcessedChunk] = []

        for i, node in enumerate(nodes):
            content = node.get_content()

            # Get parent ID if exists
            parent_id = None
            if NodeRelationship.PARENT in node.relationships:
                parent_info = node.relationships[NodeRelationship.PARENT]
                parent_id = (
                    parent_info.node_id
                    if hasattr(parent_info, "node_id")
                    else str(parent_info)
                )

            chunk = ProcessedChunk(
                content=content,
                token_count=len(content.split()),  # Simple word count
                metadata=node.metadata or {},
                node_id=node.node_id,
                parent_id=parent_id,
                chunk_index=i,
            )
            chunks.append(chunk)

        return chunks


def get_document_processor(
    embed_model: BaseEmbedding | None = None,
) -> DocumentProcessor:
    """
    Get a configured document processor.

    Args:
        embed_model: Optional embedding model for semantic chunking

    Returns:
        Configured DocumentProcessor instance
    """
    return DocumentProcessor(embed_model=embed_model)
