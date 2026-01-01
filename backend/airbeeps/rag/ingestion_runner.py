"""
Ingestion Runner: executes ingestion jobs and emits progress events.

This module runs the actual ingestion pipeline (parsing, chunking, embedding,
upserting) and updates job status/events in the database for SSE streaming.
"""

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.files.service import FileService

from .models import (
    Document,
    DocumentChunk,
    IngestionJob,
    IngestionJobEvent,
    IngestionProfile,
    KnowledgeBase,
)

logger = logging.getLogger(__name__)


# Stage weights for progress calculation (must sum to 100)
STAGE_WEIGHTS = {
    "PARSING": 15,
    "CHUNKING": 20,
    "EMBEDDING": 55,
    "UPSERTING": 10,
}


class IngestionRunner:
    """
    Runs an ingestion job through all stages, emitting events.

    The runner:
    1. Loads the job from DB
    2. Executes stages: parse → chunk → embed → upsert
    3. Updates job status and emits events at each step
    4. Handles errors and cancellation gracefully
    """

    def __init__(
        self,
        job_id: uuid.UUID,
        cancel_check: Callable[[], bool] | None = None,
    ):
        """
        Args:
            job_id: The IngestionJob ID to execute
            cancel_check: Optional callable returning True if cancel requested
        """
        self.job_id = job_id
        self._cancel_check = cancel_check or (lambda: False)
        self._event_seq = 0  # Will be initialized from DB in run()

    async def _init_event_seq(self, session: AsyncSession) -> None:
        """Initialize event sequence from max existing seq in DB."""

        result = await session.execute(
            select(func.max(IngestionJobEvent.seq)).where(
                IngestionJobEvent.job_id == self.job_id
            )
        )
        max_seq = result.scalar()
        self._event_seq = max_seq or 0
        logger.debug(
            f"Initialized event seq to {self._event_seq} for job {self.job_id}"
        )

    async def run(self) -> None:
        """Execute the full ingestion pipeline."""
        from airbeeps.database import get_async_session_context

        async with get_async_session_context() as session:
            try:
                # Initialize event seq from DB to ensure durability across restarts
                await self._init_event_seq(session)
                await self._execute(session)
            except Exception as e:
                logger.error(f"Ingestion job {self.job_id} failed: {e}", exc_info=True)
                # Try to mark as failed
                try:
                    await self._mark_failed(session, str(e))
                except Exception:
                    logger.exception("Failed to mark job as FAILED")

    async def _execute(self, session: AsyncSession) -> None:
        """Main execution logic."""
        # Load the job
        job = await session.get(IngestionJob, self.job_id)
        if not job:
            raise ValueError(f"IngestionJob {self.job_id} not found")

        if job.status != "PENDING":
            logger.warning(
                f"Job {self.job_id} status is {job.status}, expected PENDING"
            )
            return

        # Mark as running
        job.status = "RUNNING"
        job.stage = "PARSING"
        job.progress = 0
        await session.commit()

        await self._emit_event(
            session,
            "job_started",
            {
                "job_id": str(self.job_id),
                "file_path": job.file_path,
                "original_filename": job.original_filename,
            },
        )

        # Check for cancellation at each stage
        if await self._check_cancel(session, job):
            return

        # Load KB
        kb = await session.get(KnowledgeBase, job.knowledge_base_id)
        if not kb or kb.status != "ACTIVE":
            raise ValueError("Knowledge base not found or inactive")

        if kb.reindex_required:
            raise ValueError("Knowledge base requires reindex before ingestion")

        if not kb.embedding_model_id:
            raise ValueError("Knowledge base has no embedding model configured")

        # Get job config
        config = job.job_config or {}
        clean_data = config.get("clean_data", False)
        profile_id = config.get("profile_id")
        dedup_strategy = config.get("dedup_strategy", "replace")

        # Load ingestion limits from system config
        from airbeeps.system_config.service import ConfigService

        config_service = ConfigService()
        limits = await config_service.get_config_value(
            session, "rag_ingestion_limits", {}
        )

        max_pdf_pages = limits.get("max_pdf_pages", 500)
        max_sheet_rows = limits.get("max_sheet_rows", 50000)
        max_chunks = limits.get("max_chunks_per_document", 10000)

        # Handle deduplication based on file_hash
        existing_doc = None
        replaced_doc_id = None

        if job.file_hash:
            # Find existing document with same hash in this KB
            result = await session.execute(
                select(Document).where(
                    and_(
                        Document.knowledge_base_id == job.knowledge_base_id,
                        Document.file_hash == job.file_hash,
                        Document.status == "ACTIVE",
                    )
                )
            )
            existing_doc = result.scalar_one_or_none()

        if existing_doc:
            if dedup_strategy == "skip":
                # Skip ingestion - document already exists
                job.status = "SUCCEEDED"
                job.stage = None
                job.progress = 100
                job.document_id = existing_doc.id
                await session.commit()

                await self._emit_event(
                    session,
                    "completed",
                    {
                        "job_id": str(self.job_id),
                        "document_id": str(existing_doc.id),
                        "dedup_status": "skipped",
                        "message": "Document already exists with same content",
                    },
                )
                logger.info(f"Job {self.job_id} skipped - duplicate file hash")
                return

            if dedup_strategy == "replace":
                # Delete existing document and its chunks
                replaced_doc_id = existing_doc.id
                existing_doc.status = "DELETED"
                await session.commit()

                # Best-effort: delete existing vectors for the replaced document
                try:
                    from .engine import get_engine_for_kb

                    result = await session.execute(
                        select(DocumentChunk.id).where(
                            DocumentChunk.document_id == replaced_doc_id
                        )
                    )
                    chunk_ids = [str(cid) for (cid,) in result.all()]
                    if chunk_ids:
                        engine = get_engine_for_kb(kb.embedding_config)
                        collection_name = f"kb_{job.knowledge_base_id}"
                        await engine.delete_documents(
                            collection_name=collection_name,
                            document_ids=chunk_ids,
                        )
                        await self._emit_event(
                            session,
                            "log",
                            {
                                "message": f"Deleted {len(chunk_ids)} vectors for replaced document {replaced_doc_id}",
                            },
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to cleanup vectors for replaced document {replaced_doc_id}: {e}",
                        exc_info=True,
                    )

                await self._emit_event(
                    session,
                    "log",
                    {
                        "message": f"Replacing existing document {replaced_doc_id}",
                    },
                )
                logger.info(f"Job {self.job_id} replacing document {replaced_doc_id}")

            # "version" strategy - just create new document (no deletion)

        # Stage 1: PARSING - extract content
        await self._update_stage(session, job, "PARSING", 0)

        file_service = FileService(session)
        from .content_extractor import DocumentContentExtractor

        content_extractor = DocumentContentExtractor(file_service)

        file_type = job.file_type or self._infer_file_type(
            job.original_filename, job.file_path
        )

        if file_type in {"xls", "xlsx", "csv"}:
            # Tabular ingestion
            parsed_data = await self._parse_tabular(
                session,
                job,
                file_service,
                file_type,
                profile_id,
                clean_data,
                max_rows=max_sheet_rows,
            )
        elif file_type == "pdf":
            # PDF with page-level tracking
            parsed_data = await self._parse_pdf(
                session, job, content_extractor, max_pdf_pages=max_pdf_pages
            )
        else:
            # Generic file ingestion (TXT, MD, DOCX, etc.)
            parsed_data = await self._parse_generic(
                session, job, content_extractor, max_pdf_pages=max_pdf_pages
            )

        if await self._check_cancel(session, job):
            return

        # Stage 2: CHUNKING
        await self._update_stage(session, job, "CHUNKING", STAGE_WEIGHTS["PARSING"])

        from .chunker import DocumentChunker

        chunker = DocumentChunker()

        if file_type in {"xls", "xlsx", "csv"}:
            chunks_data = await self._chunk_tabular(
                session, job, kb, parsed_data, clean_data
            )
        elif file_type == "pdf" and parsed_data.get("pages"):
            # PDF with page tracking
            chunks_data = await self._chunk_pdf(session, job, kb, chunker, parsed_data)
        else:
            chunks_data = await self._chunk_generic(
                session, job, kb, chunker, parsed_data
            )

        # Enforce max chunks limit
        original_chunk_count = len(chunks_data)
        if original_chunk_count > max_chunks:
            chunks_data = chunks_data[:max_chunks]
            await self._emit_event(
                session,
                "warning",
                {
                    "message": f"Truncated from {original_chunk_count} to {max_chunks} chunks (limit)",
                },
            )
            logger.warning(
                f"Job {self.job_id}: Truncated {original_chunk_count} chunks to {max_chunks}"
            )

        job.total_items = len(chunks_data)
        job.processed_items = 0
        await session.commit()

        await self._emit_event(
            session,
            "progress",
            {
                "stage": "CHUNKING",
                "total_chunks": len(chunks_data),
            },
        )

        if await self._check_cancel(session, job):
            return

        # Stage 3: EMBEDDING
        await self._update_stage(
            session,
            job,
            "EMBEDDING",
            STAGE_WEIGHTS["PARSING"] + STAGE_WEIGHTS["CHUNKING"],
        )

        from .embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        embedder = await embedding_service.get_embedder(str(kb.embedding_model_id))

        model_info = await embedding_service._get_model_by_id(
            str(kb.embedding_model_id)
        )
        embedding_meta = {
            "embedding_model_id": str(kb.embedding_model_id),
            "embedding_model_name": getattr(model_info, "name", None),
            "embedding_model_display_name": getattr(model_info, "display_name", None),
        }

        # Create document record
        document = Document(
            title=parsed_data.get("title", job.original_filename),
            content=parsed_data.get("content", f"Ingested: {job.original_filename}"),
            knowledge_base_id=job.knowledge_base_id,
            owner_id=job.owner_id,
            file_path=job.file_path,
            file_type=file_type,
            doc_metadata=parsed_data.get("metadata", {}),
            status="INDEXING",
            file_hash=job.file_hash,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)

        job.document_id = document.id
        await session.commit()

        # Create chunk records with periodic cancel checks and progress updates
        chunk_records = []
        CANCEL_CHECK_INTERVAL = 50  # Check cancel every N chunks
        PROGRESS_UPDATE_INTERVAL = 20  # Update progress every N chunks

        total_chunks = len(chunks_data)
        embedding_base = STAGE_WEIGHTS["PARSING"] + STAGE_WEIGHTS["CHUNKING"]
        embedding_weight = STAGE_WEIGHTS["EMBEDDING"]

        for i, chunk_data in enumerate(chunks_data):
            # Periodic cancel check during chunk creation
            if i > 0 and i % CANCEL_CHECK_INTERVAL == 0:
                if await self._check_cancel(session, job):
                    document.status = "FAILED"
                    await session.commit()
                    return

            # Periodic progress update
            if i > 0 and i % PROGRESS_UPDATE_INTERVAL == 0:
                progress_pct = embedding_base + int(
                    (i / total_chunks) * embedding_weight * 0.5
                )
                job.progress = progress_pct
                job.processed_items = i
                await session.commit()

                await self._emit_event(
                    session,
                    "progress",
                    {
                        "stage": "EMBEDDING",
                        "progress": progress_pct,
                        "processed_items": i,
                        "total_items": total_chunks,
                    },
                )

            chunk_meta = {
                **chunk_data.get("metadata", {}),
                "document_id": str(document.id),
                "title": document.title,
                "status": "ACTIVE",
                **embedding_meta,
            }
            chunk_record = DocumentChunk(
                content=chunk_data["content"],
                chunk_index=i,
                token_count=chunk_data.get("token_count"),
                document_id=document.id,
                chunk_metadata=chunk_meta,
            )
            chunk_records.append(chunk_record)
            session.add(chunk_record)

        await session.flush()

        if await self._check_cancel(session, job):
            # Cleanup document
            document.status = "FAILED"
            await session.commit()
            return

        # Stage 4: UPSERTING to vector store
        await self._update_stage(
            session,
            job,
            "UPSERTING",
            STAGE_WEIGHTS["PARSING"]
            + STAGE_WEIGHTS["CHUNKING"]
            + STAGE_WEIGHTS["EMBEDDING"],
        )

        from langchain_core.documents import Document as VectorDocument

        from .engine import get_engine_for_kb

        # Get the appropriate engine for this KB (respects engine_type config)
        engine = get_engine_for_kb(kb.embedding_config)
        collection_name = f"kb_{job.knowledge_base_id}"

        # Build vector documents with periodic cancel checks and progress updates
        vector_documents = []
        upsert_base = embedding_base + int(
            embedding_weight * 0.5
        )  # 50% of embedding for building
        upsert_weight = STAGE_WEIGHTS["UPSERTING"]

        for i, chunk_record in enumerate(chunk_records):
            # Periodic cancel check during vector doc creation
            if i > 0 and i % CANCEL_CHECK_INTERVAL == 0:
                if await self._check_cancel(session, job):
                    document.status = "FAILED"
                    await session.commit()
                    return

            # Periodic progress update during upsert preparation
            if i > 0 and i % PROGRESS_UPDATE_INTERVAL == 0:
                progress_pct = upsert_base + int(
                    (i / total_chunks) * upsert_weight * 0.5
                )
                job.progress = progress_pct
                job.processed_items = i
                await session.commit()

                await self._emit_event(
                    session,
                    "progress",
                    {
                        "stage": "UPSERTING",
                        "progress": progress_pct,
                        "processed_items": i,
                        "total_items": total_chunks,
                    },
                )

            vector_documents.append(
                VectorDocument(
                    id=str(chunk_record.id),
                    page_content=chunk_record.content,
                    metadata={
                        "chunk_id": str(chunk_record.id),
                        "document_id": str(document.id),
                        "chunk_index": chunk_record.chunk_index,
                        "knowledge_base_id": str(job.knowledge_base_id),
                        **chunk_record.chunk_metadata,
                    },
                )
            )

        # Emit event before vector store operation (this is where embedding happens)
        job.progress = upsert_base + int(upsert_weight * 0.5)
        await session.commit()
        await self._emit_event(
            session,
            "progress",
            {
                "stage": "UPSERTING",
                "progress": job.progress,
                "message": "Embedding and upserting to vector store...",
                "processed_items": len(chunk_records),
                "total_items": total_chunks,
            },
        )

        await engine.index_documents(
            collection_name=collection_name,
            documents=vector_documents,
            embedding_function=embedder,
        )

        # Mark success
        document.status = "ACTIVE"
        job.status = "SUCCEEDED"
        job.stage = None
        job.progress = 100
        job.chunks_created = len(chunk_records)
        job.processed_items = len(chunk_records)
        await session.commit()

        await self._emit_event(
            session,
            "completed",
            {
                "job_id": str(self.job_id),
                "document_id": str(document.id),
                "chunks_created": len(chunk_records),
            },
        )

        logger.info(
            f"Ingestion job {self.job_id} completed: document={document.id}, chunks={len(chunk_records)}"
        )

    async def _parse_tabular(
        self,
        session: AsyncSession,
        job: IngestionJob,
        file_service: FileService,
        file_type: str,
        profile_id: str | None,
        clean_data: bool,
        max_rows: int = 50000,
    ) -> dict[str, Any]:
        """Parse CSV/XLSX file and return row data."""
        from io import BytesIO

        import pandas as pd

        # Download file
        from airbeeps.files.storage import storage_service

        file_bytes, _ = await storage_service.download_file(job.file_path)
        if isinstance(file_bytes, BytesIO):
            file_bytes.seek(0)
        else:
            file_bytes = BytesIO(file_bytes)

        # Read Excel/CSV
        if file_type == "csv":
            df = pd.read_csv(file_bytes)
            sheet_name = "Sheet1"
        else:
            sheets = pd.read_excel(file_bytes, sheet_name=None)
            if not sheets:
                raise ValueError("No sheets found in Excel file")
            sheet_name = next(iter(sheets.keys()))
            df = sheets[sheet_name]

        # Drop empty columns
        df = df.dropna(axis=1, how="all")

        # Enforce row limit
        original_row_count = len(df)
        if original_row_count > max_rows:
            df = df.head(max_rows)
            await self._emit_event(
                session,
                "warning",
                {
                    "message": f"Truncated from {original_row_count} to {max_rows} rows (limit)",
                },
            )
            logger.warning(
                f"Job {self.job_id}: Truncated {original_row_count} rows to {max_rows}"
            )

        await self._emit_event(
            session,
            "log",
            {
                "message": f"Parsed {len(df)} rows from {sheet_name}",
            },
        )

        # Resolve profile config (explicit -> KB default -> builtin default)
        profile_config, profile_name = await self._resolve_profile_config(
            session=session,
            knowledge_base_id=job.knowledge_base_id,
            profile_id=profile_id,
            file_type=file_type,
        )
        if profile_name:
            await self._emit_event(
                session,
                "log",
                {
                    "message": f"Using ingestion profile: {profile_name}",
                },
            )

        return {
            "title": job.original_filename,
            "content": f"Excel source: {job.original_filename}",
            "metadata": {
                "source_type": "file",
                "original_filename": job.original_filename,
                "sheet": sheet_name,
            },
            "dataframe": df,
            "sheet_name": sheet_name,
            "profile_config": profile_config,
        }

    async def _parse_generic(
        self,
        session: AsyncSession,
        job: IngestionJob,
        content_extractor,
        max_pdf_pages: int = 500,
    ) -> dict[str, Any]:
        """Parse generic file (TXT, MD, DOCX, etc.) and return content."""
        # Pass max_pdf_pages to content extractor for PDF truncation
        _, content = await content_extractor.extract_from_file_path(
            job.file_path, job.original_filename, max_pdf_pages=max_pdf_pages
        )

        await self._emit_event(
            session,
            "log",
            {
                "message": f"Extracted {len(content)} characters",
            },
        )

        return {
            "title": job.original_filename,
            "content": content,
            "metadata": {
                "source_type": "file",
                "original_filename": job.original_filename,
            },
        }

    async def _parse_pdf(
        self,
        session: AsyncSession,
        job: IngestionJob,
        content_extractor,
        max_pdf_pages: int = 500,
    ) -> dict[str, Any]:
        """Parse PDF file with page-level tracking."""
        try:
            # Use page-level PDF extraction
            title, content, pages = await content_extractor.extract_pdf_with_pages(
                job.file_path, job.original_filename, max_pages=max_pdf_pages
            )

            await self._emit_event(
                session,
                "log",
                {
                    "message": f"Extracted {len(pages)} pages, {len(content)} characters",
                },
            )

            return {
                "title": title or job.original_filename,
                "content": content,
                "pages": pages,  # List of {"page": int, "text": str}
                "metadata": {
                    "source_type": "file",
                    "original_filename": job.original_filename,
                    "total_pages": len(pages),
                },
            }
        except Exception as e:
            logger.warning(f"PDF page extraction failed, falling back to generic: {e}")
            # Fallback to generic extraction without page tracking
            return await self._parse_generic(
                session, job, content_extractor, max_pdf_pages
            )

    async def _chunk_tabular(
        self,
        session: AsyncSession,
        job: IngestionJob,
        kb: KnowledgeBase,
        parsed_data: dict[str, Any],
        clean_data: bool,
    ) -> list[dict[str, Any]]:
        """Create chunks from tabular data using TabularProfileEngine."""
        from .tabular_profile import get_profile_engine

        df = parsed_data["dataframe"]
        sheet_name = parsed_data["sheet_name"]
        profile_config = parsed_data.get("profile_config")

        # Use TabularProfileEngine for profile-driven processing
        profile_engine = get_profile_engine(profile_config)

        row_chunks = profile_engine.process_dataframe(
            df=df,
            sheet_name=sheet_name,
            file_path=job.file_path,
            file_type=job.file_type or "unknown",
            original_filename=job.original_filename,
            title=job.original_filename,
            clean_data=clean_data,
        )

        # Add token counts and apply truncation if needed
        from .chunker import DocumentChunker

        chunker = DocumentChunker()

        chunks = []
        for row_chunk in row_chunks:
            row_text = row_chunk["content"]
            row_meta = row_chunk["metadata"]

            token_count = chunker._count_tokens(row_text)

            # Truncate if needed
            if token_count > kb.chunk_size:
                row_text = chunker._truncate_to_token_limit(row_text, kb.chunk_size)
                token_count = kb.chunk_size

            chunks.append(
                {
                    "content": row_text,
                    "metadata": row_meta,
                    "token_count": token_count,
                }
            )

        return chunks

    async def _resolve_profile_config(
        self,
        session: AsyncSession,
        knowledge_base_id: uuid.UUID,
        profile_id: str | None,
        file_type: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """
        Resolve the ingestion profile config to use for a tabular file.

        Priority:
        1) Explicit profile_id (if valid and ACTIVE)
        2) KB-specific default profile (is_default=True)
        3) Global builtin default profile (is_builtin=True and is_default=True)
        4) None (engine uses its internal default)
        """
        # 1) Explicit
        if profile_id:
            try:
                pid = uuid.UUID(str(profile_id))
                profile = await session.get(IngestionProfile, pid)
                if profile and profile.status == "ACTIVE":
                    return profile.config, profile.name
            except Exception:
                logger.warning(f"Invalid profile_id on job {self.job_id}: {profile_id}")

        # 2) KB default
        try:
            result = await session.execute(
                select(IngestionProfile).where(
                    and_(
                        IngestionProfile.knowledge_base_id == knowledge_base_id,
                        IngestionProfile.is_default,
                        IngestionProfile.status == "ACTIVE",
                    )
                )
            )
            kb_default = result.scalar_one_or_none()
            if kb_default:
                return kb_default.config, kb_default.name
        except Exception as e:
            logger.warning(f"Failed to load KB default profile: {e}")

        # 3) Builtin default (select in Python to avoid JSON contains portability issues)
        try:
            result = await session.execute(
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
                    return p.config, p.name
        except Exception as e:
            logger.warning(f"Failed to load builtin default profile: {e}")

        return None, None

    async def _chunk_generic(
        self,
        session: AsyncSession,
        job: IngestionJob,
        kb: KnowledgeBase,
        chunker,
        parsed_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Create chunks from generic text content."""
        content = parsed_data["content"]
        title = parsed_data["title"]
        base_metadata = parsed_data.get("metadata", {})

        raw_chunks = chunker.chunk_document(
            content,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            max_tokens_per_chunk=kb.chunk_size,
            metadata={
                "title": title,
                "file_path": job.file_path,
                "file_type": job.file_type,
                **base_metadata,
            },
        )

        return [
            {
                "content": chunk.content,
                "metadata": chunk.metadata,
                "token_count": chunk.token_count,
            }
            for chunk in raw_chunks
        ]

    async def _chunk_pdf(
        self,
        session: AsyncSession,
        job: IngestionJob,
        kb: KnowledgeBase,
        chunker,
        parsed_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Create chunks from PDF with page number tracking."""
        pages = parsed_data.get("pages", [])
        title = parsed_data["title"]
        base_metadata = parsed_data.get("metadata", {})
        all_chunks = []

        for page_data in pages:
            page_number = page_data["page"]
            page_text = page_data["text"]

            if not page_text.strip():
                continue

            # Chunk this page's content
            page_chunks = chunker.chunk_document(
                page_text,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                max_tokens_per_chunk=kb.chunk_size,
                metadata={
                    "title": title,
                    "file_path": job.file_path,
                    "file_type": job.file_type,
                    "page_number": page_number,  # Track the source page
                    **base_metadata,
                },
            )

            for chunk in page_chunks:
                all_chunks.append(
                    {
                        "content": chunk.content,
                        "metadata": chunk.metadata,
                        "token_count": chunk.token_count,
                    }
                )

        logger.info(
            f"Created {len(all_chunks)} chunks from {len(pages)} PDF pages for {job.original_filename}"
        )
        return all_chunks

    async def _update_stage(
        self,
        session: AsyncSession,
        job: IngestionJob,
        stage: str,
        base_progress: int,
    ) -> None:
        """Update job stage and emit event."""
        job.stage = stage
        job.progress = base_progress
        await session.commit()

        await self._emit_event(
            session,
            "stage_change",
            {
                "stage": stage,
                "progress": base_progress,
            },
        )

    async def _emit_event(
        self,
        session: AsyncSession,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Append an event to the job event log."""
        self._event_seq += 1
        event = IngestionJobEvent(
            job_id=self.job_id,
            seq=self._event_seq,
            event_type=event_type,
            payload=payload,
        )
        session.add(event)
        await session.commit()

        logger.debug(f"Job {self.job_id} event: {event_type} - {payload}")

    async def _check_cancel(self, session: AsyncSession, job: IngestionJob) -> bool:
        """Check if cancellation was requested and handle it.

        Returns True if job was cancelled, False otherwise.
        Caller should return immediately if True is returned.
        """
        # Refresh to see cancel_requested written by another request/session
        try:
            await session.refresh(job)
        except Exception:
            # If refresh fails, fall back to in-process cancel check only
            pass

        cancel_requested = False
        try:
            cancel_requested = bool((job.job_config or {}).get("cancel_requested"))
        except Exception:
            cancel_requested = False

        if not (self._cancel_check() or cancel_requested):
            return False

        # Mark as cancelled directly (don't spawn separate task)
        await self._mark_cancelled(session, job)
        return True

    async def _mark_cancelled(self, session: AsyncSession, job: IngestionJob) -> None:
        """Mark job as cancelled."""
        # Best-effort cleanup: if we already created a document/chunks, remove vectors and soft-delete the document
        try:
            if job.document_id:
                document = await session.get(Document, job.document_id)
                if document:
                    document.status = "DELETED"

                # Delete vectors for this document's chunks (so canceled ingest doesn't pollute retrieval)
                result = await session.execute(
                    select(DocumentChunk.id).where(
                        DocumentChunk.document_id == job.document_id
                    )
                )
                chunk_ids = [str(cid) for (cid,) in result.all()]
                if chunk_ids:
                    from .engine import get_engine_for_kb

                    kb = await session.get(KnowledgeBase, job.knowledge_base_id)
                    engine = get_engine_for_kb(kb.embedding_config if kb else None)
                    collection_name = f"kb_{job.knowledge_base_id}"
                    await engine.delete_documents(
                        collection_name=collection_name,
                        document_ids=chunk_ids,
                    )
        except Exception as e:
            logger.warning(
                f"Cancel cleanup failed for job {self.job_id}: {e}", exc_info=True
            )

        job.status = "CANCELED"
        job.stage = None
        await session.commit()

        await self._emit_event(
            session,
            "canceled",
            {
                "job_id": str(self.job_id),
            },
        )

        logger.info(f"Ingestion job {self.job_id} was cancelled")

    async def _mark_failed(self, session: AsyncSession, error: str) -> None:
        """Mark job as failed with error message."""
        job = await session.get(IngestionJob, self.job_id)
        if job:
            job.status = "FAILED"
            job.stage = None
            job.error_message = error[:2000] if error else "Unknown error"
            await session.commit()

            await self._emit_event(
                session,
                "error",
                {
                    "job_id": str(self.job_id),
                    "error": error[:500] if error else "Unknown error",
                },
            )

    def _infer_file_type(self, filename: str | None, file_path: str) -> str:
        """Infer file type from filename or path."""
        name = filename or file_path
        if not name:
            return "unknown"

        name_lower = name.lower()
        if name_lower.endswith(".pdf"):
            return "pdf"
        if name_lower.endswith(".xlsx"):
            return "xlsx"
        if name_lower.endswith(".xls"):
            return "xls"
        if name_lower.endswith(".csv"):
            return "csv"
        if name_lower.endswith(".docx"):
            return "docx"
        if name_lower.endswith(".doc"):
            return "doc"
        if name_lower.endswith(".txt"):
            return "txt"
        if name_lower.endswith(".md"):
            return "md"
        return "unknown"
