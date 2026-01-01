import re
from dataclasses import dataclass
from typing import Any

import tiktoken
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


@dataclass
class DocumentChunk:
    """Document chunk data class"""

    content: str
    token_count: int
    metadata: dict[str, Any]


class DocumentChunker:
    """Document chunker"""

    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding_name = encoding_name
        # Prepare encoder in advance to avoid repeated creation
        self._encoding = tiktoken.get_encoding(encoding_name)

    def chunk_document(
        self,
        content: str,
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        max_tokens_per_chunk: int | None = None,
        truncate_long: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> list[DocumentChunk]:
        """Chunk document"""
        if not content:
            return []

        base_metadata = metadata.copy() if metadata else {}

        chunks: list[DocumentChunk] = []

        # Split into code and text segments to preserve code fences as atomic units
        segments = self._split_code_blocks(content)

        Hsplitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "H1"),
                ("##", "H2"),
                ("###", "H3"),
                ("####", "H4"),
                ("#####", "H5"),
                ("######", "H6"),
            ]
        )

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=self._count_tokens,
        )

        for seg_type, seg_text, seg_meta in segments:
            if seg_type == "code":
                max_allowed = max_tokens_per_chunk or chunk_size
                code_content = (
                    self._truncate_to_token_limit(seg_text, max_allowed)
                    if truncate_long
                    else seg_text
                )
                token_count = self._count_tokens(code_content)
                chunk_metadata = {**base_metadata, **seg_meta}
                chunks.append(
                    DocumentChunk(
                        content=code_content,
                        token_count=token_count,
                        metadata=chunk_metadata,
                    )
                )
                continue

            # text segment: apply markdown-aware splitting
            markdown_documents = Hsplitter.split_text(seg_text)
            split_documents = text_splitter.split_documents(markdown_documents)
            for doc in split_documents:
                raw_content = doc.page_content.strip()
                if not raw_content:
                    continue

                max_allowed = max_tokens_per_chunk or chunk_size
                chunk_content = (
                    self._truncate_to_token_limit(raw_content, max_allowed)
                    if truncate_long
                    else raw_content
                )

                chunk_metadata = {**doc.metadata, **base_metadata, **seg_meta}

                token_count = self._count_tokens(chunk_content)
                chunks.append(
                    DocumentChunk(
                        content=chunk_content,
                        token_count=token_count,
                        metadata=chunk_metadata,
                    )
                )

        if not chunks:
            return [
                DocumentChunk(
                    content=self._truncate_to_token_limit(
                        content, max_tokens_per_chunk or chunk_size
                    )
                    if truncate_long
                    else content,
                    token_count=self._count_tokens(
                        self._truncate_to_token_limit(
                            content, max_tokens_per_chunk or chunk_size
                        )
                        if truncate_long
                        else content
                    ),
                    metadata=base_metadata,
                )
            ]

        return chunks

    def _count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken"""
        return len(self._encoding.encode(text))

    def _truncate_to_token_limit(self, text: str, max_tokens: int) -> str:
        tokens = self._encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._encoding.decode(tokens[:max_tokens])

    def _split_code_blocks(self, text: str) -> list[tuple[str, str, dict[str, Any]]]:
        """
        Split text into segments of ("code" | "text", content, metadata).
        Preserves fenced code blocks as atomic units with language metadata.
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
            # Preserve code fences for proper LLM rendering
            code_with_fences = f"```{lang}\n{body}```"
            segments.append(
                (
                    "code",
                    code_with_fences,
                    {"code_language": lang} if lang else {"code_language": "plain"},
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
