import logging
import math
import re
import uuid
from io import BytesIO
from typing import Any

import pandas as pd
from langchain_core.documents import Document as VectorDocument
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.files.service import FileService

from .chunker import DocumentChunker
from .cleaners import apply_cleaners
from .content_extractor import DocumentContentExtractor
from .embeddings import EmbeddingService
from .engine import get_engine, get_engine_for_kb
from .models import Document, DocumentChunk, KnowledgeBase
from .vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class RAGService:
    """RAG Core Service"""

    def __init__(self, session: AsyncSession, file_service: FileService | None = None):
        self.session = session
        self.embedding_service = EmbeddingService()
        self.chunker = DocumentChunker()
        # Default engine for backward compatibility; KB-specific methods use get_engine_for_kb
        self.vector_store = ChromaVectorStore()
        self._default_engine = get_engine()

        # If file service is not provided, create a new instance
        if file_service:
            self.file_service = file_service
        else:
            self.file_service = FileService(session)

        self.content_extractor = DocumentContentExtractor(self.file_service)

    def _get_engine_for_kb(self, kb: "KnowledgeBase"):
        """Get the appropriate RAG engine for a knowledge base."""
        return get_engine_for_kb(kb.embedding_config)

    async def _cleanup_vectors(
        self, collection_name: str, chunk_ids: list[str]
    ) -> None:
        """Best-effort cleanup of vectors when failures happen."""
        try:
            if chunk_ids:
                await self.vector_store.delete_documents(collection_name, chunk_ids)
        except Exception as exc:
            logger.warning(
                "Failed to cleanup vectors for collection %s: %s",
                collection_name,
                exc,
            )

    def _tokenize(self, text: str) -> list[str]:
        return [t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if t]

    def _bm25_rank(
        self, query: str, corpus: dict[str, str], k1: float = 1.5, b: float = 0.75
    ) -> list[tuple[str, float]]:
        """
        Minimal BM25 over an in-memory corpus (chunk_id -> text).
        """
        tokens = self._tokenize(query)
        if not tokens or not corpus:
            return []

        df: dict[str, int] = {}
        doc_tokens: dict[str, list[str]] = {}
        doc_lens: dict[str, int] = {}
        for doc_id, text in corpus.items():
            toks = self._tokenize(text)
            doc_tokens[doc_id] = toks
            doc_lens[doc_id] = len(toks) or 1
            seen = set()
            for t in toks:
                if t in seen:
                    continue
                df[t] = df.get(t, 0) + 1
                seen.add(t)

        N = len(corpus)
        avgdl = sum(doc_lens.values()) / float(N or 1)

        def idf(term: str) -> float:
            n_qi = df.get(term, 0)
            return math.log((N - n_qi + 0.5) / (n_qi + 0.5) + 1)

        scores: dict[str, float] = {}
        for term in tokens:
            if term not in df:
                continue
            term_idf = idf(term)
            for doc_id, toks in doc_tokens.items():
                freq = toks.count(term)
                denom = freq + k1 * (1 - b + b * (doc_lens[doc_id] / avgdl))
                score = term_idf * (freq * (k1 + 1)) / denom
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    async def _rerank_with_embeddings(
        self,
        query: str,
        docs: list[VectorDocument],
        embedder,
        top_k: int,
    ) -> list[VectorDocument]:
        """
        Lightweight rerank using embedding cosine similarity (approximation for cross-encoder).
        """
        if not docs:
            return docs
        top_k = min(top_k, len(docs))
        try:
            q_emb = embedder.embed_query(query)
            contents = [d.page_content for d in docs[:top_k]]
            d_embs = embedder.embed_documents(contents)

            def cosine(a, b):
                import numpy as np

                a = np.array(a)
                b = np.array(b)
                denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
                return float(np.dot(a, b) / denom)

            scored = []
            for doc, emb in zip(docs[:top_k], d_embs, strict=False):
                score = cosine(q_emb, emb)
                meta = doc.metadata or {}
                meta["rerank_score"] = score
                doc.metadata = meta
                scored.append((doc, score))

            scored.sort(key=lambda p: p[1], reverse=True)
            return [d for d, _ in scored] + docs[top_k:]
        except Exception as exc:
            logger.warning("Rerank failed; returning original order: %s", exc)
            return docs

    def _generate_alt_queries(self, query: str, max_count: int = 3) -> list[str]:
        """
        Deterministic, low-risk alternative queries (no LLM dependency).
        """
        alts = [query.strip()]
        simplified = re.sub(r"[^\w\s]", " ", query).strip()
        if simplified and simplified.lower() != query.lower():
            alts.append(simplified)
        parts = re.split(r"[.?!;]", query)
        for p in parts:
            p = p.strip()
            if 20 <= len(p) <= 160 and p.lower() not in (a.lower() for a in alts):
                alts.append(p)
        seen = set()
        uniq = []
        for q in alts:
            key = q.lower()
            if key in seen or not q:
                continue
            seen.add(key)
            uniq.append(q)
            if len(uniq) >= max_count:
                break
        return uniq

    def _infer_file_type(
        self, filename: str | None, file_path: str | None
    ) -> str | None:
        """Infer file type from filename or path"""
        if not filename and not file_path:
            return None

        # Prefer filename, then file_path
        target_name = filename or file_path
        if not target_name:
            return None

        # Extract file extension
        from pathlib import Path

        ext = Path(target_name).suffix.lower()

        # Extension to file type mapping
        ext_mapping = {
            ".txt": "txt",
            ".md": "md",
            ".markdown": "md",
            ".pdf": "pdf",
            ".doc": "doc",
            ".docx": "docx",
            ".xls": "xls",
            ".xlsx": "xlsx",
            ".ppt": "ppt",
            ".pptx": "pptx",
            ".csv": "csv",
            ".json": "json",
            ".xml": "xml",
            ".html": "html",
            ".htm": "html",
            ".rtf": "rtf",
            ".odt": "odt",
            ".ods": "ods",
            ".odp": "odp",
        }

        return ext_mapping.get(ext)

    async def create_knowledge_base(
        self,
        name: str,
        description: str | None,
        embedding_model_id: str | None,
        chunk_size: int | None,
        chunk_overlap: int | None,
        owner_id: uuid.UUID,
    ) -> KnowledgeBase:
        """Create knowledge base"""
        logger.info(f"Creating knowledge base '{name}' for owner {owner_id}")
        logger.debug(
            f"KB params: embedding_model_id={embedding_model_id}, chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
        )
        try:
            # Check if name already exists
            existing_kb = await self.session.execute(
                select(KnowledgeBase).where(
                    and_(
                        KnowledgeBase.name == name,
                        KnowledgeBase.owner_id == owner_id,
                        KnowledgeBase.status == "ACTIVE",
                    )
                )
            )
            if existing_kb.scalar_one_or_none():
                logger.warning(
                    f"Knowledge base with name '{name}' already exists for owner {owner_id}"
                )
                raise ValueError(f"Knowledge base with name '{name}' already exists")

            kb_data = {
                "name": name,
                "description": description,
                "owner_id": owner_id,
                "embedding_model_id": embedding_model_id,
                "chunk_size": chunk_size or 1000,
                "chunk_overlap": chunk_overlap or 200,
            }

            kb = KnowledgeBase(**kb_data)

            self.session.add(kb)
            await self.session.commit()
            await self.session.refresh(kb)

            logger.info(f"Successfully created knowledge base: {kb.name} (ID: {kb.id})")
            return kb

        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to create knowledge base '{name}': {e}", exc_info=True
            )
            raise

    async def get_knowledge_bases(
        self, owner_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[KnowledgeBase]:
        """Get user's knowledge base list"""
        logger.debug(
            f"Retrieving knowledge bases for owner {owner_id}, skip={skip}, limit={limit}"
        )
        result = await self.session.execute(
            select(KnowledgeBase)
            .where(
                and_(
                    KnowledgeBase.owner_id == owner_id, KnowledgeBase.status == "ACTIVE"
                )
            )
            .offset(skip)
            .limit(limit)
            .order_by(KnowledgeBase.created_at.desc())
        )
        kbs = result.scalars().all()
        logger.debug(f"Retrieved {len(kbs)} knowledge bases for owner {owner_id}")
        return kbs

    async def get_knowledge_base(
        self, kb_id: uuid.UUID, owner_id: uuid.UUID | None = None
    ) -> KnowledgeBase | None:
        """Get specific knowledge base"""
        if owner_id is not None:
            # Query with permission check
            result = await self.session.execute(
                select(KnowledgeBase).where(
                    and_(
                        KnowledgeBase.id == kb_id,
                        KnowledgeBase.owner_id == owner_id,
                        KnowledgeBase.status == "ACTIVE",
                    )
                )
            )
        else:
            # Query without permission check
            result = await self.session.execute(
                select(KnowledgeBase).where(
                    and_(KnowledgeBase.id == kb_id, KnowledgeBase.status == "ACTIVE")
                )
            )
        return result.scalar_one_or_none()

    async def mark_kb_reindexed(self, kb_id: uuid.UUID) -> KnowledgeBase:
        """Mark a knowledge base as reindexed (clears reindex_required)."""
        result = await self.session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()
        if not kb:
            raise ValueError("Knowledge base not found")
        kb.reindex_required = False
        await self.session.commit()
        await self.session.refresh(kb)
        return kb

    async def delete_vector_collection(self, kb_id: uuid.UUID) -> None:
        """Remove all vectors for a knowledge base from Chroma."""
        collection_name = f"kb_{kb_id}"
        await self.vector_store.delete_collection(collection_name)

    async def reindex_knowledge_base(
        self,
        kb_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
        clean_data: bool = False,
    ) -> dict[str, Any]:
        """
        Rebuild all chunks and vectors for a knowledge base using current
        chunk_size/chunk_overlap and embedding model.
        """
        logger.info("Starting reindex for KB %s (owner=%s)", kb_id, owner_id)

        kb_query = (
            select(KnowledgeBase)
            .options(
                selectinload(KnowledgeBase.documents).selectinload(Document.chunks)
            )
            .where(KnowledgeBase.id == kb_id)
        )
        if owner_id:
            kb_query = kb_query.where(KnowledgeBase.owner_id == owner_id)

        result = await self.session.execute(kb_query)
        kb = result.scalar_one_or_none()
        if not kb or kb.status != "ACTIVE":
            raise ValueError("Knowledge base not found or inactive")

        if not kb.embedding_model_id:
            raise ValueError("Knowledge base embedding model is not configured")

        embedder = await self.embedding_service.get_embedder(str(kb.embedding_model_id))
        model_info = await self.embedding_service._get_model_by_id(
            str(kb.embedding_model_id)
        )
        embedding_meta = {
            "embedding_model_id": str(kb.embedding_model_id),
            "embedding_model_name": getattr(model_info, "name", None),
            "embedding_model_display_name": getattr(model_info, "display_name", None),
        }

        total_chunks = 0
        total_docs = 0
        collection_name = f"kb_{kb_id}"

        for document in kb.documents:
            if document.status != "ACTIVE":
                continue

            total_docs += 1

            # Delete existing vectors for this document
            chunk_ids = [str(chunk.id) for chunk in document.chunks]
            if chunk_ids:
                await self.vector_store.delete_documents(collection_name, chunk_ids)
            # Remove chunk records
            for chunk in list(document.chunks):
                self.session.delete(chunk)

            # Rebuild chunks
            chunk_records: list[DocumentChunk] = []
            vector_documents: list[VectorDocument] = []

            if document.file_path and document.file_type in {"xls", "xlsx", "csv"}:
                (
                    chunk_records,
                    vector_documents,
                ) = await self._rebuild_excel_document_chunks(
                    document=document,
                    kb=kb,
                    embedder_meta=embedding_meta,
                    clean_data=clean_data,
                )
            else:
                (
                    chunk_records,
                    vector_documents,
                ) = await self._rebuild_generic_document_chunks(
                    document=document,
                    kb=kb,
                    embedder_meta=embedding_meta,
                )

            # Persist new chunks
            for chunk_record in chunk_records:
                self.session.add(chunk_record)
            await self.session.flush()

            # Refresh vector documents with assigned chunk IDs
            updated_vectors: list[VectorDocument] = []
            for i in range(len(chunk_records)):
                new_meta = dict(vector_documents[i].metadata)
                new_meta["chunk_id"] = str(chunk_records[i].id)
                updated_vectors.append(
                    VectorDocument(
                        id=str(chunk_records[i].id),
                        page_content=chunk_records[i].content,
                        metadata=new_meta,
                    )
                )

            try:
                engine = self._get_engine_for_kb(kb)
                await engine.index_documents(
                    collection_name=collection_name,
                    documents=updated_vectors,
                    embedding_function=embedder,
                )
                document.status = "ACTIVE"
                await self.session.commit()
            except Exception as exc:
                chunk_ids = [str(c.id) for c in chunk_records]
                await self._cleanup_vectors(collection_name, chunk_ids)
                await self.session.rollback()
                try:
                    kb_ref = await self.get_knowledge_base(kb_id)
                    if kb_ref:
                        kb_ref.reindex_required = True
                        await self.session.commit()
                except Exception as flag_exc:
                    logger.warning(
                        "Failed to persist reindex_required flag after reindex failure: %s",
                        flag_exc,
                    )
                logger.error(
                    "Reindex failed for document %s in KB %s: %s",
                    document.id,
                    kb_id,
                    exc,
                    exc_info=True,
                )
                kb.reindex_required = True
                raise

            total_chunks += len(chunk_records)

        kb.reindex_required = False
        await self.session.commit()
        logger.info(
            "Reindex complete for KB %s: docs=%s chunks=%s",
            kb_id,
            total_docs,
            total_chunks,
        )
        return {
            "knowledge_base_id": str(kb_id),
            "documents_reindexed": total_docs,
            "chunks_indexed": total_chunks,
        }

    async def _rebuild_generic_document_chunks(
        self,
        document: Document,
        kb: KnowledgeBase,
        embedder_meta: dict[str, Any],
    ) -> tuple[list[DocumentChunk], list[VectorDocument]]:
        """Rebuild chunks/vector docs for non-Excel documents from stored content."""
        base_metadata = {
            "document_id": str(document.id),
            "title": document.title,
            "file_path": document.file_path,
            "file_type": document.file_type,
            "source_url": document.source_url,
            "status": "ACTIVE",
            **(document.doc_metadata or {}),
            **embedder_meta,
        }

        chunks = self.chunker.chunk_document(
            document.content,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            max_tokens_per_chunk=kb.chunk_size,
            metadata=base_metadata,
        )

        chunk_records: list[DocumentChunk] = []
        vector_documents: list[VectorDocument] = []
        for i, chunk in enumerate(chunks):
            chunk_record = DocumentChunk(
                content=chunk.content,
                chunk_index=i,
                token_count=chunk.token_count,
                document_id=document.id,
                chunk_metadata=chunk.metadata,
            )
            chunk_records.append(chunk_record)
            vector_documents.append(
                VectorDocument(
                    id="pending",
                    page_content=chunk.content,
                    metadata={
                        "chunk_id": "pending",
                        "document_id": str(document.id),
                        "chunk_index": i,
                        "knowledge_base_id": str(kb.id),
                        "title": document.title,
                        **chunk.metadata,
                    },
                )
            )

        return chunk_records, vector_documents

    async def _rebuild_excel_document_chunks(
        self,
        document: Document,
        kb: KnowledgeBase,
        embedder_meta: dict[str, Any],
        clean_data: bool = False,
    ) -> tuple[list[DocumentChunk], list[VectorDocument]]:
        """Rebuild chunks/vector docs for Excel/CSV documents from storage."""
        if not document.file_path:
            raise ValueError("Excel/CSV document missing file_path for reindex")

        file_bytes, _ = await self.content_extractor._download_file_from_storage(
            document.file_path
        )
        if isinstance(file_bytes, BytesIO):
            file_bytes.seek(0)
        else:
            file_bytes = BytesIO(file_bytes)

        sheets = pd.read_excel(file_bytes, sheet_name=None)
        if not sheets:
            raise ValueError("No sheets found in Excel/CSV file during reindex")

        sheet_name = next(iter(sheets.keys()))
        df = sheets[sheet_name].dropna(axis=1, how="all")

        def _clean_value(val: Any) -> str | None:
            if pd.isna(val):
                return None
            if isinstance(val, float) and val.is_integer():
                val = str(int(val))
            else:
                val = str(val)
            cleaned = apply_cleaners(val, enabled=clean_data)
            return cleaned if cleaned else None

        def _build_row_text(row: pd.Series) -> str:
            parts: list[str] = []
            for col in df.columns:
                val = _clean_value(row.get(col))
                if val is None or val == "":
                    continue
                parts.append(f"{col}: {val}")
            return "\n".join(parts)

        chunk_records: list[DocumentChunk] = []
        vector_documents: list[VectorDocument] = []

        for idx, row in df.iterrows():
            row_text = apply_cleaners(_build_row_text(row), enabled=clean_data)
            if not row_text.strip():
                continue

            row_number = int(idx) + 2
            chunk_meta: dict[str, Any] = {
                "sheet": sheet_name,
                "row_number": row_number,
                "file_path": document.file_path,
                "file_type": document.file_type,
                "display_name": document.title,
                "source_type": "file",
                "original_filename": document.doc_metadata.get("original_filename")
                if document.doc_metadata
                else None,
                "document_id": str(document.id),
                "title": document.title,
                "status": "ACTIVE",
                **embedder_meta,
                **(document.doc_metadata or {}),
            }

            chunk_content = row_text
            if self.chunker._count_tokens(chunk_content) > kb.chunk_size:
                chunk_content = self.chunker._truncate_to_token_limit(
                    chunk_content, kb.chunk_size
                )

            chunk_record = DocumentChunk(
                content=chunk_content,
                chunk_index=len(chunk_records),
                token_count=self.chunker._count_tokens(chunk_content),
                document_id=document.id,
                chunk_metadata=chunk_meta,
            )
            chunk_records.append(chunk_record)
            vector_documents.append(
                VectorDocument(
                    id="pending",
                    page_content=chunk_content,
                    metadata={
                        "chunk_id": "pending",
                        "document_id": str(document.id),
                        "chunk_index": chunk_record.chunk_index,
                        "knowledge_base_id": str(kb.id),
                        **chunk_meta,
                    },
                )
            )

        if not chunk_records:
            raise ValueError("No usable rows found in Excel/CSV file during reindex")

        return chunk_records, vector_documents

    async def add_document_from_file(
        self,
        file_path: str,
        knowledge_base_id: uuid.UUID,
        owner_id: uuid.UUID,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
        dedup_strategy: str = "replace",
        clean_data: bool = False,
    ) -> tuple[Document, str, uuid.UUID | None]:
        """Add document to knowledge base from file path with dedup handling."""
        logger.info(
            f"Adding document from file '{filename or file_path}' to KB {knowledge_base_id}, dedup_strategy={dedup_strategy}"
        )
        try:
            dedup_status = "created"
            replaced_document_id: uuid.UUID | None = None

            if dedup_strategy not in {"replace", "skip", "version"}:
                logger.warning(
                    f"Invalid dedup_strategy '{dedup_strategy}', defaulting to 'replace'"
                )
                dedup_strategy = "replace"

            # Verify knowledge base exists and belongs to user
            kb = await self.get_knowledge_base(knowledge_base_id, owner_id)
            if not kb:
                logger.error(
                    f"Knowledge base {knowledge_base_id} not found or access denied for owner {owner_id}"
                )
                raise ValueError("Knowledge base not found or access denied")

            # Find corresponding file record from database to get original filename as title
            file_record = await self.file_service.get_file_by_path(file_path)
            if file_record:
                title = file_record.filename
                original_filename = file_record.filename
                file_hash = file_record.file_hash
                logger.debug(
                    f"Found file record: {original_filename}, hash={file_hash}"
                )
            else:
                # If file record not found, use passed filename or extract from path
                title = filename or file_path.split("/")[-1]
                original_filename = filename
                file_hash = None
                logger.debug(f"No file record found, using filename: {title}")

            # Deduplicate by file hash (identical content)
            existing_doc = None
            if file_hash:
                existing_doc = await self._get_active_document_by_hash(
                    knowledge_base_id=knowledge_base_id,
                    file_hash=file_hash,
                )
                if existing_doc and dedup_strategy == "skip":
                    logger.info(
                        f"Skipping ingest for {file_path} (duplicate hash={file_hash}) in KB {knowledge_base_id}"
                    )
                    return existing_doc, "skipped", None
                if existing_doc and dedup_strategy == "replace":
                    replaced_document_id = existing_doc.id
                    logger.info(
                        f"Replacing existing document {existing_doc.id} with same hash"
                    )
                    await self.delete_document(existing_doc.id, owner_id)
                    dedup_status = "replaced"
                if existing_doc and dedup_strategy == "version":
                    dedup_status = "versioned"
                    title = await self._next_versioned_title(title, knowledge_base_id)
                    logger.debug(f"Creating versioned document with title: {title}")

            # If content differs but filename matches, follow strategy
            if not existing_doc:
                same_title_doc = await self._get_active_document_by_title(
                    knowledge_base_id=knowledge_base_id,
                    title=title,
                )
                if same_title_doc and dedup_strategy == "replace":
                    replaced_document_id = same_title_doc.id
                    logger.info(
                        f"Replacing existing document {same_title_doc.id} with same title"
                    )
                    await self.delete_document(same_title_doc.id, owner_id)
                    dedup_status = "replaced"
                elif same_title_doc and dedup_strategy == "version":
                    dedup_status = "versioned"
                    title = await self._next_versioned_title(title, knowledge_base_id)
                    logger.debug(f"Creating versioned document with title: {title}")

            # Infer file type
            file_type = self._infer_file_type(original_filename, file_path)
            logger.debug(f"Inferred file type: {file_type}")

            # For Excel/CSV sources, ingest row-wise for better citations
            if file_type in {"xls", "xlsx", "csv"}:
                logger.info(f"Processing Excel/CSV file: {title}")
                document = await self._add_excel_document(
                    file_path=file_path,
                    original_filename=original_filename or title,
                    title=title,
                    knowledge_base_id=knowledge_base_id,
                    owner_id=owner_id,
                    metadata=metadata or {},
                    file_type=file_type,
                    file_hash=file_hash,
                    clean_data=clean_data,
                )
                logger.info(
                    f"Added Excel/CSV document '{title}' from file '{file_path}' to knowledge base {knowledge_base_id}"
                )
                return document, dedup_status, replaced_document_id

            # Extract content from file path using content extractor (default path)
            logger.debug(f"Extracting content from file: {file_path}")
            _, content = await self.content_extractor.extract_from_file_path(
                file_path, original_filename
            )
            logger.debug(f"Extracted {len(content)} characters from file")

            # Merge metadata
            combined_metadata = {
                "source_type": "file",
                "original_filename": original_filename,
                **(metadata or {}),
            }

            # Call existing add document method
            document = await self.add_document(
                title=title,
                content=content,
                knowledge_base_id=knowledge_base_id,
                owner_id=owner_id,
                file_path=file_path,
                file_type=file_type,
                metadata=combined_metadata,
                status="ACTIVE",  # ensure visible in listings
                file_hash=file_hash,
            )

            logger.info(
                f"Added document '{title}' (ID: {document.id}) from file '{file_path}' to knowledge base {knowledge_base_id}"
            )
            return document, dedup_status, replaced_document_id

        except Exception as e:
            logger.error(
                f"Failed to add document from file {file_path} to KB {knowledge_base_id}: {e}",
                exc_info=True,
            )
            raise

    async def _get_active_document_by_hash(
        self, knowledge_base_id: uuid.UUID, file_hash: str
    ) -> Document | None:
        """Fetch an active document in a KB by file hash."""
        result = await self.session.execute(
            select(Document).where(
                and_(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.file_hash == file_hash,
                    Document.status == "ACTIVE",
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_active_document_by_title(
        self, knowledge_base_id: uuid.UUID, title: str
    ) -> Document | None:
        """Fetch an active document in a KB by exact title."""
        result = await self.session.execute(
            select(Document).where(
                and_(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.title == title,
                    Document.status == "ACTIVE",
                )
            )
        )
        return result.scalar_one_or_none()

    async def _next_versioned_title(
        self, base_title: str, knowledge_base_id: uuid.UUID
    ) -> str:
        """
        Build the next versioned title by appending (vN).
        """
        result = await self.session.execute(
            select(Document.title).where(
                and_(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.status == "ACTIVE",
                )
            )
        )
        existing_titles = set(result.scalars().all())

        # If base already has a version suffix, strip it for counting
        version = 2
        while True:
            candidate = f"{base_title} (v{version})"
            if candidate not in existing_titles:
                return candidate
            version += 1

    async def add_document(
        self,
        title: str,
        content: str,
        knowledge_base_id: uuid.UUID,
        owner_id: uuid.UUID,
        source_url: str | None = None,
        file_path: str | None = None,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "ACTIVE",
        file_hash: str | None = None,
    ) -> Document:
        """Add document to knowledge base"""
        logger.info(f"Adding document '{title}' to KB {knowledge_base_id}")
        logger.debug(
            f"Document: file_type={file_type}, content_length={len(content)}, file_hash={file_hash}"
        )
        try:
            # Verify knowledge base exists and belongs to user
            kb = await self.get_knowledge_base(knowledge_base_id, owner_id)
            if not kb:
                logger.error(
                    f"Knowledge base {knowledge_base_id} not found or access denied for owner {owner_id}"
                )
                raise ValueError("Knowledge base not found or access denied")

            # If file_type not provided, try to infer from file path
            if not file_type and (file_path or source_url):
                file_type = self._infer_file_type(None, file_path or source_url)
                logger.debug(f"Inferred file type: {file_type}")

            # Create document record
            document = Document(
                title=title,
                content=content,
                knowledge_base_id=knowledge_base_id,
                owner_id=owner_id,
                source_url=source_url,
                file_path=file_path,
                file_type=file_type,
                doc_metadata=metadata or {},
                status="INDEXING",
                file_hash=file_hash,
            )

            self.session.add(document)
            await self.session.commit()
            await self.session.refresh(document)
            logger.debug(f"Created document record with ID: {document.id}")

            # Prevent ingest if KB needs reindex
            if getattr(kb, "reindex_required", False):
                raise ValueError(
                    "Knowledge base embedding model changed; reindex required before ingest"
                )

            # Chunk document
            model_info = await self.embedding_service._get_model_by_id(
                str(kb.embedding_model_id)
            )
            embedding_meta = {
                "embedding_model_id": str(kb.embedding_model_id),
                "embedding_model_name": getattr(model_info, "name", None),
                "embedding_model_display_name": getattr(
                    model_info, "display_name", None
                ),
            }
            chunks = self.chunker.chunk_document(
                content,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                max_tokens_per_chunk=kb.chunk_size,
                metadata={
                    "document_id": str(document.id),
                    "title": title,
                    "file_path": file_path,
                    "file_type": file_type,
                    "source_url": source_url,
                    "status": status,
                    **embedding_meta,
                    **(metadata or {}),
                },
            )

            logger.info(
                f"Split document into {len(chunks)} chunks (chunk_size={kb.chunk_size}, overlap={kb.chunk_overlap})"
            )

            if not kb.embedding_model_id:
                logger.error(
                    f"Knowledge base {knowledge_base_id} has no embedding model configured"
                )
                raise ValueError("Knowledge base embedding model is not configured")

            logger.debug(f"Getting embedder for model: {kb.embedding_model_id}")
            embedder = await self.embedding_service.get_embedder(
                model_id=str(kb.embedding_model_id)
            )

            chunk_records: list[DocumentChunk] = []
            vector_documents: list[VectorDocument] = []

            collection_name = f"kb_{knowledge_base_id}"
            try:
                # Save document chunks to database
                for i, chunk in enumerate(chunks):
                    chunk_record = DocumentChunk(
                        content=chunk.content,
                        chunk_index=i,
                        token_count=chunk.token_count,
                        document_id=document.id,
                        chunk_metadata=chunk.metadata,
                    )
                    chunk_records.append(chunk_record)
                    self.session.add(chunk_record)

                await self.session.flush()
                logger.debug(f"Saved {len(chunk_records)} chunk records to database")

                for chunk_record in chunk_records:
                    vector_documents.append(
                        VectorDocument(
                            id=str(chunk_record.id),
                            page_content=chunk_record.content,
                            metadata={
                                "chunk_id": str(chunk_record.id),
                                "document_id": str(document.id),
                                "chunk_index": chunk_record.chunk_index,
                                "knowledge_base_id": str(knowledge_base_id),
                                "title": title,
                                **chunk_record.chunk_metadata,
                            },
                        )
                    )

                logger.debug(
                    f"Adding {len(vector_documents)} documents to vector store collection: {collection_name}"
                )
                engine = self._get_engine_for_kb(kb)
                await engine.index_documents(
                    collection_name=collection_name,
                    documents=vector_documents,
                    embedding_function=embedder,
                )
                # Mark indexing success
                document.status = "ACTIVE"
                await self.session.commit()
                logger.info(
                    f"Successfully added document '{title}' (ID: {document.id}) with {len(chunks)} chunks to KB {knowledge_base_id}"
                )
                return document
            except Exception as e:
                await self.session.rollback()
                chunk_ids = [doc.id for doc in vector_documents]
                await self._cleanup_vectors(collection_name, chunk_ids)
                try:
                    doc_ref = await self.session.get(Document, document.id)
                    if doc_ref:
                        doc_ref.status = "FAILED"
                        await self.session.commit()
                except Exception as status_exc:
                    logger.warning(
                        "Failed to persist FAILED status for document %s: %s",
                        document.id,
                        status_exc,
                    )
                logger.error(
                    f"Failed to add document '{title}' to KB {knowledge_base_id}: {e}",
                    exc_info=True,
                )
                raise

        except Exception as e:
            await self.session.rollback()
            logger.error(
                f"Failed to add document '{title}' to KB {knowledge_base_id}: {e}",
                exc_info=True,
            )
            raise

    async def _add_excel_document(
        self,
        file_path: str,
        original_filename: str,
        title: str,
        knowledge_base_id: uuid.UUID,
        owner_id: uuid.UUID,
        metadata: dict[str, Any],
        file_type: str,
        file_hash: str | None,
        clean_data: bool = False,
        profile_id: uuid.UUID | None = None,
    ) -> Document:
        """Ingest an Excel/CSV file row-wise to preserve per-row citations.

        Uses TabularProfileEngine for profile-driven metadata extraction
        and row text rendering if a profile is specified or a KB default exists.
        """
        logger.info(
            f"Ingesting Excel/CSV file '{title}' row-wise for KB {knowledge_base_id}"
        )

        # Verify knowledge base exists and belongs to user
        kb = await self.get_knowledge_base(knowledge_base_id, owner_id)
        if not kb:
            logger.error(
                f"Knowledge base {knowledge_base_id} not found or access denied"
            )
            raise ValueError("Knowledge base not found or access denied")
        if getattr(kb, "reindex_required", False):
            raise ValueError(
                "Knowledge base embedding model changed; reindex required before ingest"
            )
        if not kb.embedding_model_id:
            logger.error(
                f"Knowledge base {knowledge_base_id} has no embedding model configured"
            )
            raise ValueError("Knowledge base embedding model is not configured")

        # Load profile configuration
        from .models import IngestionProfile
        from .tabular_profile import get_profile_engine

        profile_config = None
        if profile_id:
            # Use specified profile
            profile = await self.session.get(IngestionProfile, profile_id)
            if profile and profile.status == "ACTIVE":
                profile_config = profile.config
                logger.debug(f"Using specified profile: {profile.name}")

        if not profile_config:
            # Try to find KB default profile
            result = await self.session.execute(
                select(IngestionProfile).where(
                    and_(
                        IngestionProfile.knowledge_base_id == knowledge_base_id,
                        IngestionProfile.is_default,
                        IngestionProfile.status == "ACTIVE",
                    )
                )
            )
            default_profile = result.scalar_one_or_none()
            if default_profile:
                profile_config = default_profile.config
                logger.debug(f"Using KB default profile: {default_profile.name}")

        if not profile_config:
            # Fall back to global builtin default profile (if any)
            result = await self.session.execute(
                select(IngestionProfile).where(
                    and_(
                        IngestionProfile.knowledge_base_id.is_(None),
                        IngestionProfile.is_builtin,
                        IngestionProfile.is_default,
                        IngestionProfile.status == "ACTIVE",
                    )
                )
            )
            builtin_defaults = result.scalars().all()
            for p in builtin_defaults:
                if not p.file_types or file_type in (p.file_types or []):
                    profile_config = p.config
                    logger.debug(f"Using builtin default profile: {p.name}")
                    break

        # Initialize profile engine (uses default profile if config is None)
        profile_engine = get_profile_engine(profile_config)

        # Download the file bytes from storage
        logger.debug(f"Downloading file from storage: {file_path}")
        file_bytes, _ = await self.content_extractor._download_file_from_storage(
            file_path
        )
        if isinstance(file_bytes, BytesIO):
            file_bytes.seek(0)
        else:
            file_bytes = BytesIO(file_bytes)

        # Read all sheets; use the first by default
        logger.debug("Reading Excel sheets")
        if file_type == "csv":
            file_bytes.seek(0)
            df = pd.read_csv(file_bytes)
            sheet_name = "Sheet1"
        else:
            sheets = pd.read_excel(file_bytes, sheet_name=None)
            if not sheets:
                logger.error(f"No sheets found in Excel file {file_path}")
                raise ValueError("No sheets found in Excel file")
            # Prefer first sheet
            sheet_name = next(iter(sheets.keys()))
            df = sheets[sheet_name]

        logger.debug(
            f"Using sheet '{sheet_name}' with {len(df)} rows, {len(df.columns)} columns"
        )

        # Drop completely empty columns
        df = df.dropna(axis=1, how="all")
        logger.debug(f"After dropping empty columns: {len(df.columns)} columns")

        # Process dataframe using profile engine
        row_chunks = profile_engine.process_dataframe(
            df=df,
            sheet_name=sheet_name,
            file_path=file_path,
            file_type=file_type,
            original_filename=original_filename,
            title=title,
            clean_data=clean_data,
        )

        if not row_chunks:
            logger.error(f"No usable rows found in Excel/CSV file {file_path}")
            raise ValueError("No usable rows found in Excel/CSV file")

        logger.info(f"Extracted {len(row_chunks)} usable rows from Excel file")

        # Create a document record to own the chunks
        document = Document(
            title=title,
            content=f"Excel source: {title}",
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
            file_path=file_path,
            file_type=file_type,
            doc_metadata=metadata or {},
            status="INDEXING",  # transition to ACTIVE after vector write
            file_hash=file_hash,
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        logger.debug(f"Created document record with ID: {document.id}")

        logger.debug(f"Getting embedder for model: {kb.embedding_model_id}")
        embedder = await self.embedding_service.get_embedder(
            model_id=str(kb.embedding_model_id)
        )
        model_info = await self.embedding_service._get_model_by_id(
            str(kb.embedding_model_id)
        )
        embedding_meta = {
            "embedding_model_id": str(kb.embedding_model_id),
            "embedding_model_name": getattr(model_info, "name", None),
            "embedding_model_display_name": getattr(model_info, "display_name", None),
        }

        chunk_records: list[DocumentChunk] = []
        vector_documents: list[VectorDocument] = []
        collection_name = f"kb_{knowledge_base_id}"

        try:
            for i, row_chunk in enumerate(row_chunks):
                chunk_content = row_chunk["content"]
                max_tokens = kb.chunk_size
                if self.chunker._count_tokens(chunk_content) > max_tokens:
                    chunk_content = self.chunker._truncate_to_token_limit(
                        chunk_content, max_tokens
                    )
                chunk_meta = {
                    **row_chunk["metadata"],
                    "document_id": str(document.id),
                    "title": title,
                    "status": "ACTIVE",
                    **embedding_meta,
                }
                chunk_record = DocumentChunk(
                    content=chunk_content,
                    chunk_index=i,
                    token_count=self.chunker._count_tokens(chunk_content),
                    document_id=document.id,
                    chunk_metadata=chunk_meta,
                )
                chunk_records.append(chunk_record)
                self.session.add(chunk_record)

            await self.session.flush()
            logger.debug(f"Saved {len(chunk_records)} row chunks to database")

            for chunk_record in chunk_records:
                vector_documents.append(
                    VectorDocument(
                        id=str(chunk_record.id),
                        page_content=chunk_record.content,
                        metadata={
                            "chunk_id": str(chunk_record.id),
                            "document_id": str(document.id),
                            "chunk_index": chunk_record.chunk_index,
                            "knowledge_base_id": str(knowledge_base_id),
                            **chunk_record.chunk_metadata,
                        },
                    )
                )

            logger.debug(f"Adding {len(vector_documents)} row chunks to vector store")
            engine = self._get_engine_for_kb(kb)
            await engine.index_documents(
                collection_name=collection_name,
                documents=vector_documents,
                embedding_function=embedder,
            )
            document.status = "ACTIVE"
            await self.session.commit()
            logger.info(
                f"Added {len(row_chunks)} row chunks from Excel '{title}' into knowledge base {knowledge_base_id}"
            )
            return document
        except Exception as e:
            await self.session.rollback()
            chunk_ids = [doc.id for doc in vector_documents]
            await self._cleanup_vectors(collection_name, chunk_ids)
            try:
                doc_ref = await self.session.get(Document, document.id)
                if doc_ref:
                    doc_ref.status = "FAILED"
                    await self.session.commit()
            except Exception as status_exc:
                logger.warning(
                    "Failed to persist FAILED status for Excel/CSV document %s: %s",
                    document.id,
                    status_exc,
                )
            logger.error(
                "Failed to add Excel/CSV document '%s' to KB %s: %s",
                title,
                knowledge_base_id,
                e,
                exc_info=True,
            )
            raise

    async def get_documents(
        self,
        knowledge_base_id: uuid.UUID,
        owner_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """Get document list in knowledge base"""
        # Verify knowledge base access permission
        kb = await self.get_knowledge_base(knowledge_base_id, owner_id)
        if not kb:
            raise ValueError("Knowledge base not found or access denied")

        result = await self.session.execute(
            select(Document)
            .where(
                and_(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.status == "ACTIVE",
                )
            )
            .offset(skip)
            .limit(limit)
            .order_by(Document.created_at.desc())
        )
        return result.scalars().all()

    async def get_document_chunks(
        self,
        document_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DocumentChunk]:
        """Get document chunk list"""
        logger.debug(
            f"Retrieving chunks for document {document_id}, owner_id={owner_id}"
        )
        try:
            # Get document info first, verify permission
            query = select(Document).where(Document.id == document_id)
            if owner_id is not None:
                query = query.where(
                    and_(Document.owner_id == owner_id, Document.status == "ACTIVE")
                )
            else:
                query = query.where(Document.status == "ACTIVE")

            document_result = await self.session.execute(query)
            document = document_result.scalar_one_or_none()

            if not document:
                logger.warning(f"Document {document_id} not found or access denied")
                raise ValueError("Document not found or access denied")

            # Query document chunks
            chunk_result = await self.session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .offset(skip)
                .limit(limit)
                .order_by(DocumentChunk.chunk_index.asc())
            )
            chunks = chunk_result.scalars().all()
            logger.debug(f"Retrieved {len(chunks)} chunks for document {document_id}")
            return chunks

        except Exception as e:
            logger.error(
                f"Failed to get document chunks for {document_id}: {e}", exc_info=True
            )
            raise

    async def delete_document(
        self, document_id: uuid.UUID, owner_id: uuid.UUID | None = None
    ) -> bool:
        """Delete document"""
        logger.info(f"Deleting document {document_id}, owner_id={owner_id}")
        try:
            # Get document
            result = await self.session.execute(
                select(Document)
                .options(selectinload(Document.chunks))
                .where(and_(Document.id == document_id, Document.status == "ACTIVE"))
            )
            document = result.scalar_one_or_none()

            if not document:
                logger.warning(f"Document {document_id} not found for deletion")
                return False

            # If owner_id is provided, enforce ownership
            if owner_id is not None and document.owner_id != owner_id:
                logger.warning(
                    f"Document {document_id} deletion denied - owner mismatch"
                )
                return False

            # Delete from vector database
            collection_name = f"kb_{document.knowledge_base_id}"
            chunk_ids = [str(chunk.id) for chunk in document.chunks]

            if chunk_ids:
                logger.debug(
                    f"Deleting {len(chunk_ids)} chunks from vector store collection {collection_name}"
                )
                await self.vector_store.delete_documents(collection_name, chunk_ids)

            # Mark as deleted (soft delete)
            document.status = "DELETED"

            await self.session.commit()
            logger.info(
                f"Successfully deleted document {document_id} with {len(chunk_ids)} chunks"
            )
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete document {document_id}: {e}", exc_info=True)
            raise

    async def relevance_search(
        self,
        query: str,
        knowledge_base_id: uuid.UUID,
        k: int = 5,
        fetch_k: int | None = None,
        score_threshold: float | None = None,
        search_type: str = "similarity",
        filters: dict[str, Any] | None = None,
        mmr_lambda: float = 0.5,
        multi_query: bool = False,
        multi_query_count: int = 3,
        rerank_top_k: int | None = None,
        rerank_model_id: uuid.UUID | None = None,
        hybrid_enabled: bool = False,
        hybrid_corpus_limit: int = 1000,
    ) -> list[VectorDocument]:
        """RAG query with score/threshold support."""
        logger.debug(f"Query: {query[:100]}...")  # Log first 100 chars
        try:
            kb = await self.get_knowledge_base(knowledge_base_id)
            if not kb:
                logger.error(
                    f"Knowledge base {knowledge_base_id} not found for relevance search"
                )
                raise ValueError("Knowledge base not found or access denied")
            if getattr(kb, "reindex_required", False):
                logger.error(
                    "Knowledge base %s requires reindex before retrieval",
                    knowledge_base_id,
                )
                raise ValueError("Knowledge base needs reindexing for retrieval")

            effective_fetch_k = fetch_k or max(k * 3, k)
            logger.info(
                "Performing relevance search in KB %s, k=%s, fetch_k=%s, threshold=%s, search_type=%s",
                knowledge_base_id,
                k,
                effective_fetch_k,
                score_threshold,
                search_type,
            )

            collection_name = f"kb_{knowledge_base_id}"

            if not kb.embedding_model_id:
                logger.error(
                    f"Knowledge base {knowledge_base_id} has no embedding model configured"
                )
                raise ValueError("Knowledge base embedding model is not configured")

            embedding_model_id = str(kb.embedding_model_id)
            logger.debug(f"Using embedding model: {embedding_model_id}")

            embedder = await self.embedding_service.get_embedder(embedding_model_id)

            where_filter: dict[str, Any] = {
                "knowledge_base_id": str(knowledge_base_id),
            }
            if filters:
                where_filter.update(filters)

            # Collect dense results (multi-query optional)
            queries = (
                self._generate_alt_queries(query, max_count=multi_query_count)
                if multi_query
                else [query]
            )

            merged: dict[str, VectorDocument] = {}

            # Get appropriate engine for this KB
            engine = self._get_engine_for_kb(kb)

            async def _add_results(q: str) -> None:
                # Use engine interface for retrieval (respects KB's engine_type)
                results = await engine.retrieve(
                    collection_name=collection_name,
                    query=q,
                    embedding_function=embedder,
                    top_k=k,
                    similarity_threshold=score_threshold or 0.0,
                    filter_metadata=where_filter,
                    search_type=search_type,
                    fetch_k=effective_fetch_k,
                    mmr_lambda=mmr_lambda,
                )
                for result in results:
                    metadata = result.metadata or {}
                    metadata["score"] = result.score
                    metadata["similarity"] = result.score
                    metadata.setdefault("retrieval_sources", []).append("dense")
                    doc = VectorDocument(
                        page_content=result.content,
                        metadata=metadata,
                    )
                    chunk_id = (
                        result.id or metadata.get("chunk_id") or metadata.get("id")
                    )
                    merged[str(chunk_id)] = doc

            for q in queries:
                await _add_results(q)

            # Hybrid lexical retrieval (optional)
            if hybrid_enabled:
                corpus: dict[str, str] = {}
                chunk_meta_map: dict[str, dict[str, Any]] = {}
                chunk_query = (
                    select(
                        DocumentChunk.id,
                        DocumentChunk.content,
                        DocumentChunk.chunk_metadata,
                    )
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        Document.knowledge_base_id == knowledge_base_id,
                        Document.status == "ACTIVE",
                    )
                    .limit(hybrid_corpus_limit)
                )
                chunk_result = await self.session.execute(chunk_query)
                for cid, content_val, meta in chunk_result.all():
                    cid_str = str(cid)
                    corpus[cid_str] = content_val or ""
                    chunk_meta_map[cid_str] = meta or {}

                bm25_hits = self._bm25_rank(query, corpus)
                for cid_str, bm25_score in bm25_hits[:effective_fetch_k]:
                    meta = chunk_meta_map.get(cid_str, {})
                    doc = VectorDocument(
                        id=cid_str,
                        page_content=corpus.get(cid_str, ""),
                        metadata={
                            "chunk_id": cid_str,
                            "knowledge_base_id": str(knowledge_base_id),
                            "bm25_score": bm25_score,
                            **meta,
                        },
                    )
                    doc.metadata.setdefault("retrieval_sources", []).append("bm25")
                    merged[cid_str] = doc

            docs: list[VectorDocument] = list(merged.values())

            # Optional rerank
            if rerank_top_k:
                rerank_embedder = embedder
                if rerank_model_id:
                    try:
                        rerank_embedder = await self.embedding_service.get_embedder(
                            model_id=str(rerank_model_id)
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to load rerank model %s, falling back to embedding model: %s",
                            rerank_model_id,
                            exc,
                        )
                docs = await self._rerank_with_embeddings(
                    query=query, docs=docs, embedder=rerank_embedder, top_k=rerank_top_k
                )

            # Sort by rerank_score, then dense score, then bm25
            def _score_key(d: VectorDocument):
                meta = d.metadata or {}
                if "rerank_score" in meta:
                    return meta["rerank_score"]
                if "score" in meta:
                    return meta["score"]
                if "bm25_score" in meta:
                    return meta["bm25_score"]
                return 0

            docs.sort(key=_score_key, reverse=True)

            if len(docs) > k:
                docs = docs[:k]

            logger.info(
                "Relevance search returned %s documents for KB %s",
                len(docs),
                knowledge_base_id,
            )
            logger.debug(
                "Retrieval stats kb=%s requested_k=%s fetch_k=%s threshold=%s search_type=%s returned=%s",
                knowledge_base_id,
                k,
                effective_fetch_k,
                score_threshold,
                search_type,
                len(docs),
            )
            if not docs:
                logger.warning(
                    "Relevance search returned no documents (kb=%s, query_len=%s)",
                    knowledge_base_id,
                    len(query),
                )
            return docs

        except Exception as e:
            logger.error(
                f"Failed to perform RAG query on KB {knowledge_base_id}: {e}",
                exc_info=True,
            )
            raise
