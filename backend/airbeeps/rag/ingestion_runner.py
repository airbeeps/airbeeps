"""
Ingestion Runner: executes ingestion jobs and emits progress events.

This module runs the actual ingestion pipeline using LlamaIndex:
- Parsing (extract content from files)
- Chunking (semantic/hierarchical with LlamaIndex node parsers)
- Embedding (LlamaIndex embedding models)
- Upserting (to configured vector store via index manager)

Updates job status/events in the database for SSE streaming.
"""

import logging
import uuid
from collections.abc import Callable
from io import BytesIO
from typing import Any

import pandas as pd
from llama_index.core.schema import TextNode
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.config import settings
from airbeeps.files.service import FileService

from .cleaners import apply_cleaners
from .doc_processor import DocumentProcessor, get_document_processor
from .embeddings import get_embedding_service
from .index_manager import get_index_manager
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
    Runs an ingestion job through all stages using LlamaIndex.

    The runner:
    1. Loads the job from DB
    2. Executes stages: parse -> chunk -> embed -> upsert
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
        self._event_seq = 0

        # LlamaIndex components
        self.embedding_service = get_embedding_service()
        self.index_manager = get_index_manager()

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
                await self._init_event_seq(session)
                await self._execute(session)
            except Exception as e:
                logger.error(f"Ingestion job {self.job_id} failed: {e}", exc_info=True)
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
        preprocessing = config.get("preprocessing", {}) or {}

        # Load ingestion limits
        from airbeeps.system_config.service import ConfigService

        config_service = ConfigService()
        limits = await config_service.get_config_value(
            session, "rag_ingestion_limits", {}
        )

        max_pdf_pages = limits.get("max_pdf_pages", 500)
        max_sheet_rows = limits.get("max_sheet_rows", 50000)
        max_chunks = limits.get("max_chunks_per_document", 10000)

        # Handle deduplication
        existing_doc = None
        replaced_doc_id = None

        if job.file_hash:
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
                replaced_doc_id = existing_doc.id
                existing_doc.status = "DELETED"
                await session.commit()

                # Delete existing vectors
                try:
                    result = await session.execute(
                        select(DocumentChunk.id).where(
                            DocumentChunk.document_id == replaced_doc_id
                        )
                    )
                    chunk_ids = [str(cid) for (cid,) in result.all()]
                    if chunk_ids:
                        await self.index_manager.delete_nodes(
                            kb_id=job.knowledge_base_id,
                            node_ids=chunk_ids,
                            store_type=kb.vector_store_type,
                        )
                        await self._emit_event(
                            session,
                            "log",
                            {
                                "message": f"Deleted {len(chunk_ids)} vectors for replaced document"
                            },
                        )
                except Exception as e:
                    logger.warning(f"Failed to cleanup vectors: {e}")

                await self._emit_event(
                    session,
                    "log",
                    {"message": f"Replacing existing document {replaced_doc_id}"},
                )

        # Stage 1: PARSING
        await self._update_stage(session, job, "PARSING", 0)

        file_service = FileService(session)
        from .content_extractor import DocumentContentExtractor

        content_extractor = DocumentContentExtractor(file_service)

        file_type = job.file_type or self._infer_file_type(
            job.original_filename, job.file_path
        )

        if file_type in {"xls", "xlsx", "csv"}:
            parsed_data = await self._parse_tabular(
                session,
                job,
                file_service,
                file_type,
                profile_id,
                clean_data,
                max_sheet_rows,
                preprocessing=preprocessing,
            )
        elif file_type == "pdf":
            parsed_data = await self._parse_pdf(
                session,
                job,
                content_extractor,
                max_pdf_pages,
                preprocessing=preprocessing,
            )
        else:
            parsed_data = await self._parse_generic(
                session, job, content_extractor, max_pdf_pages
            )

        if await self._check_cancel(session, job):
            return

        # Stage 2: CHUNKING with LlamaIndex
        await self._update_stage(session, job, "CHUNKING", STAGE_WEIGHTS["PARSING"])

        # Get embedding model for semantic chunking
        (
            embed_model,
            embed_info,
        ) = await self.embedding_service.get_embed_model_with_info(
            str(kb.embedding_model_id)
        )
        embed_dim = embed_info.get("embed_dim", 384)

        doc_processor = get_document_processor(embed_model=embed_model)

        if file_type in {"xls", "xlsx", "csv"}:
            nodes = await self._chunk_tabular(
                session, job, kb, parsed_data, clean_data, embed_info
            )
        elif file_type == "pdf" and parsed_data.get("pages"):
            nodes = await self._chunk_pdf(
                session, job, kb, doc_processor, parsed_data, embed_info, preprocessing
            )
        else:
            nodes = await self._chunk_generic(
                session, job, kb, doc_processor, parsed_data, embed_info, preprocessing
            )

        # Enforce max chunks limit
        if len(nodes) > max_chunks:
            await self._emit_event(
                session,
                "warning",
                {"message": f"Truncated from {len(nodes)} to {max_chunks} chunks"},
            )
            nodes = nodes[:max_chunks]

        job.total_items = len(nodes)
        job.processed_items = 0
        await session.commit()

        await self._emit_event(
            session,
            "progress",
            {"stage": "CHUNKING", "total_chunks": len(nodes)},
        )

        if await self._check_cancel(session, job):
            return

        # Stage 3: Create document and chunk records
        await self._update_stage(
            session,
            job,
            "EMBEDDING",
            STAGE_WEIGHTS["PARSING"] + STAGE_WEIGHTS["CHUNKING"],
        )

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

        # Create chunk records with original node IDs preserved
        chunk_records = []
        node_id_map = {}  # Maps original node_id -> chunk_id

        for i, node in enumerate(nodes):
            node.metadata["document_id"] = str(document.id)
            original_node_id = node.node_id

            # Store relationships before modifications
            parent_id = None
            child_ids = []
            if hasattr(node, "relationships"):
                from llama_index.core.schema import NodeRelationship

                if NodeRelationship.PARENT in node.relationships:
                    parent_rel = node.relationships[NodeRelationship.PARENT]
                    parent_id = (
                        parent_rel.node_id
                        if hasattr(parent_rel, "node_id")
                        else str(parent_rel)
                    )
                if NodeRelationship.CHILD in node.relationships:
                    child_rel = node.relationships[NodeRelationship.CHILD]
                    if isinstance(child_rel, list):
                        child_ids = [
                            c.node_id if hasattr(c, "node_id") else str(c)
                            for c in child_rel
                        ]
                    else:
                        child_ids = [
                            child_rel.node_id
                            if hasattr(child_rel, "node_id")
                            else str(child_rel)
                        ]

            chunk_record = DocumentChunk(
                content=node.get_content(),
                chunk_index=i,
                token_count=len(node.get_content().split()),
                document_id=document.id,
                chunk_metadata={
                    "original_node_id": original_node_id,
                    "parent_node_id": parent_id,
                    "child_node_ids": child_ids,
                    **node.metadata,
                },
            )
            chunk_records.append(chunk_record)
            session.add(chunk_record)

            if i > 0 and i % 50 == 0:
                if await self._check_cancel(session, job):
                    document.status = "FAILED"
                    await session.commit()
                    return

                job.processed_items = i
                await session.commit()

        await session.flush()

        # Map original node IDs to chunk IDs
        for chunk_record, node in zip(chunk_records, nodes, strict=False):
            node_id_map[node.node_id] = str(chunk_record.id)

        # Update node IDs and relationships to use chunk IDs
        for chunk_record, node in zip(chunk_records, nodes, strict=False):
            node.node_id = str(chunk_record.id)
            node.metadata["chunk_id"] = str(chunk_record.id)

            # Update relationship IDs to point to new chunk IDs
            if hasattr(node, "relationships"):
                from llama_index.core.schema import NodeRelationship, RelatedNodeInfo

                if NodeRelationship.PARENT in node.relationships:
                    parent_rel = node.relationships[NodeRelationship.PARENT]
                    old_parent_id = (
                        parent_rel.node_id
                        if hasattr(parent_rel, "node_id")
                        else str(parent_rel)
                    )
                    if old_parent_id in node_id_map:
                        node.relationships[NodeRelationship.PARENT] = RelatedNodeInfo(
                            node_id=node_id_map[old_parent_id]
                        )

                if NodeRelationship.CHILD in node.relationships:
                    child_rel = node.relationships[NodeRelationship.CHILD]
                    if isinstance(child_rel, list):
                        updated_children = []
                        for child in child_rel:
                            old_child_id = (
                                child.node_id
                                if hasattr(child, "node_id")
                                else str(child)
                            )
                            if old_child_id in node_id_map:
                                updated_children.append(
                                    RelatedNodeInfo(node_id=node_id_map[old_child_id])
                                )
                        if updated_children:
                            node.relationships[NodeRelationship.CHILD] = (
                                updated_children
                            )
                    else:
                        old_child_id = (
                            child_rel.node_id
                            if hasattr(child_rel, "node_id")
                            else str(child_rel)
                        )
                        if old_child_id in node_id_map:
                            node.relationships[NodeRelationship.CHILD] = (
                                RelatedNodeInfo(node_id=node_id_map[old_child_id])
                            )

        if await self._check_cancel(session, job):
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

        await self._emit_event(
            session,
            "progress",
            {
                "stage": "UPSERTING",
                "message": "Indexing to vector store...",
                "processed_items": len(nodes),
                "total_items": len(nodes),
            },
        )

        # Index using LlamaIndex index manager
        await self.index_manager.add_nodes(
            kb_id=job.knowledge_base_id,
            nodes=nodes,
            embed_model=embed_model,
            store_type=kb.vector_store_type,
            embed_dim=embed_dim,
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
        preprocessing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Parse CSV/XLSX file and return row data."""
        from airbeeps.files.storage import storage_service

        preprocessing = preprocessing or {}

        # Get preprocessing options
        sheet_names_filter = preprocessing.get(
            "sheet_names"
        )  # List of sheet names to process
        header_row = preprocessing.get("header_row", 0)
        skip_rows = preprocessing.get("skip_rows", 0)

        file_bytes, _ = await storage_service.download_file(job.file_path)
        if isinstance(file_bytes, BytesIO):
            file_bytes.seek(0)
        else:
            file_bytes = BytesIO(file_bytes)

        all_dataframes = []
        all_sheet_names = []

        if file_type == "csv":
            df = pd.read_csv(file_bytes, header=header_row)
            if skip_rows > 0:
                df = df.iloc[skip_rows:]
            all_dataframes.append(df)
            all_sheet_names.append("Sheet1")
        else:
            sheets = pd.read_excel(file_bytes, sheet_name=None, header=header_row)
            if not sheets:
                raise ValueError("No sheets found in Excel file")

            # Filter sheets if specified
            for sheet_name, df in sheets.items():
                if sheet_names_filter and sheet_name not in sheet_names_filter:
                    continue

                if skip_rows > 0:
                    df = df.iloc[skip_rows:]

                df = df.dropna(axis=1, how="all")
                all_dataframes.append(df)
                all_sheet_names.append(sheet_name)

            if not all_dataframes:
                # If filter excluded all sheets, use first sheet as fallback
                first_sheet_name = next(iter(sheets.keys()))
                df = sheets[first_sheet_name]
                if skip_rows > 0:
                    df = df.iloc[skip_rows:]
                df = df.dropna(axis=1, how="all")
                all_dataframes.append(df)
                all_sheet_names.append(first_sheet_name)

        # Combine dataframes (add sheet name to metadata in chunking phase)
        combined_df = (
            pd.concat(all_dataframes, ignore_index=True)
            if len(all_dataframes) > 1
            else all_dataframes[0]
        )
        combined_df = combined_df.dropna(axis=1, how="all")

        if len(combined_df) > max_rows:
            await self._emit_event(
                session,
                "warning",
                {"message": f"Truncated from {len(combined_df)} to {max_rows} rows"},
            )
            combined_df = combined_df.head(max_rows)

        sheet_summary = ", ".join(all_sheet_names)
        await self._emit_event(
            session,
            "log",
            {
                "message": f"Parsed {len(combined_df)} rows from {len(all_sheet_names)} sheet(s): {sheet_summary}"
            },
        )

        profile_config, profile_name = await self._resolve_profile_config(
            session, job.knowledge_base_id, profile_id, file_type
        )
        if profile_name:
            await self._emit_event(
                session,
                "log",
                {"message": f"Using ingestion profile: {profile_name}"},
            )

        return {
            "title": job.original_filename,
            "content": f"Tabular source: {job.original_filename}",
            "metadata": {
                "source_type": "file",
                "original_filename": job.original_filename,
                "sheets": all_sheet_names,
                "sheet": all_sheet_names[0] if len(all_sheet_names) == 1 else None,
            },
            "dataframes": list(zip(all_sheet_names, all_dataframes, strict=False)),
            "dataframe": combined_df,  # Keep for backward compatibility
            "sheet_name": all_sheet_names[0]
            if len(all_sheet_names) == 1
            else "Combined",
            "profile_config": profile_config,
        }

    async def _parse_generic(
        self,
        session: AsyncSession,
        job: IngestionJob,
        content_extractor,
        max_pdf_pages: int = 500,
    ) -> dict[str, Any]:
        """Parse generic file and return content."""
        _, content = await content_extractor.extract_from_file_path(
            job.file_path, job.original_filename, max_pdf_pages=max_pdf_pages
        )

        await self._emit_event(
            session,
            "log",
            {"message": f"Extracted {len(content)} characters"},
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
        preprocessing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Parse PDF with page-level tracking."""
        preprocessing = preprocessing or {}

        # Apply preprocessing overrides
        effective_max_pages = preprocessing.get("pdf_max_pages") or max_pdf_pages
        page_range = preprocessing.get("pdf_page_range")

        try:
            title, content, pages = await content_extractor.extract_pdf_with_pages(
                job.file_path,
                job.original_filename,
                max_pages=effective_max_pages,
                page_range=page_range,
            )

            await self._emit_event(
                session,
                "log",
                {"message": f"Extracted {len(pages)} pages, {len(content)} characters"},
            )

            return {
                "title": title or job.original_filename,
                "content": content,
                "pages": pages,
                "metadata": {
                    "source_type": "file",
                    "original_filename": job.original_filename,
                    "total_pages": len(pages),
                },
            }
        except Exception as e:
            logger.warning(f"PDF page extraction failed: {e}")
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
        embed_info: dict[str, Any],
    ) -> list[TextNode]:
        """Create LlamaIndex nodes from tabular data."""
        df = parsed_data["dataframe"]
        sheet_name = parsed_data["sheet_name"]

        nodes = []
        for idx, row in df.iterrows():
            row_text = self._row_to_text(row, df.columns, clean_data)
            if not row_text.strip():
                continue

            row_number = int(idx) + 2

            node = TextNode(
                text=row_text,
                metadata={
                    "knowledge_base_id": str(job.knowledge_base_id),
                    "title": job.original_filename,
                    "sheet": sheet_name,
                    "row_number": row_number,
                    "file_path": job.file_path,
                    "file_type": job.file_type,
                    **embed_info,
                },
            )
            nodes.append(node)

        return nodes

    async def _chunk_generic(
        self,
        session: AsyncSession,
        job: IngestionJob,
        kb: KnowledgeBase,
        doc_processor: DocumentProcessor,
        parsed_data: dict[str, Any],
        embed_info: dict[str, Any],
        preprocessing: dict[str, Any] | None = None,
    ) -> list[TextNode]:
        """Create LlamaIndex nodes from generic content."""
        preprocessing = preprocessing or {}

        # Get chunking overrides from preprocessing config
        chunking_strategy = preprocessing.get("chunking_strategy", "auto")
        chunk_size = preprocessing.get("chunk_size_override")
        chunk_overlap = preprocessing.get("chunk_overlap_override")

        content = parsed_data["content"]
        base_metadata = {
            "knowledge_base_id": str(job.knowledge_base_id),
            "title": job.original_filename,
            "file_path": job.file_path,
            "file_type": job.file_type,
            **embed_info,
            **parsed_data.get("metadata", {}),
        }

        nodes = doc_processor.process_text(
            content=content,
            metadata=base_metadata,
            use_semantic=settings.RAG_ENABLE_SEMANTIC_CHUNKING,
            use_hierarchical=settings.RAG_ENABLE_HIERARCHICAL,
            strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        return nodes

    async def _chunk_pdf(
        self,
        session: AsyncSession,
        job: IngestionJob,
        kb: KnowledgeBase,
        doc_processor: DocumentProcessor,
        parsed_data: dict[str, Any],
        embed_info: dict[str, Any],
        preprocessing: dict[str, Any] | None = None,
    ) -> list[TextNode]:
        """Create LlamaIndex nodes from PDF with page tracking."""
        preprocessing = preprocessing or {}

        # Get chunking overrides from preprocessing config
        chunking_strategy = preprocessing.get("chunking_strategy", "auto")
        chunk_size = preprocessing.get("chunk_size_override")
        chunk_overlap = preprocessing.get("chunk_overlap_override")

        pages = parsed_data.get("pages", [])
        all_nodes = []

        for page_data in pages:
            page_number = page_data["page"]
            page_text = page_data["text"]

            if not page_text.strip():
                continue

            page_metadata = {
                "knowledge_base_id": str(job.knowledge_base_id),
                "title": job.original_filename,
                "file_path": job.file_path,
                "file_type": job.file_type,
                "page_number": page_number,
                **embed_info,
                **parsed_data.get("metadata", {}),
            }

            page_nodes = doc_processor.process_text(
                content=page_text,
                metadata=page_metadata,
                use_semantic=settings.RAG_ENABLE_SEMANTIC_CHUNKING,
                use_hierarchical=settings.RAG_ENABLE_HIERARCHICAL,
                strategy=chunking_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            all_nodes.extend(page_nodes)

        return all_nodes

    def _row_to_text(self, row: pd.Series, columns: pd.Index, clean_data: bool) -> str:
        """Convert DataFrame row to text."""
        parts = []
        for col in columns:
            val = row.get(col)
            if pd.isna(val):
                continue
            if isinstance(val, float) and val.is_integer():
                val = str(int(val))
            else:
                val = str(val)
            if clean_data:
                val = apply_cleaners(val, enabled=True)
            if val:
                parts.append(f"{col}: {val}")
        return "\n".join(parts)

    async def _resolve_profile_config(
        self,
        session: AsyncSession,
        knowledge_base_id: uuid.UUID,
        profile_id: str | None,
        file_type: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Resolve ingestion profile config."""
        if profile_id:
            try:
                profile = await session.get(
                    IngestionProfile, uuid.UUID(str(profile_id))
                )
                if profile and profile.status == "ACTIVE":
                    return profile.config, profile.name
            except Exception:
                pass

        # KB default
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
        except Exception:
            pass

        # Builtin default
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
            for p in result.scalars().all():
                if not p.file_types or file_type in (p.file_types or []):
                    return p.config, p.name
        except Exception:
            pass

        return None, None

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
            {"stage": stage, "progress": base_progress},
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
        logger.debug(f"Job {self.job_id} event: {event_type}")

    async def _check_cancel(self, session: AsyncSession, job: IngestionJob) -> bool:
        """Check if cancellation was requested."""
        try:
            await session.refresh(job)
        except Exception:
            pass

        cancel_requested = bool((job.job_config or {}).get("cancel_requested"))

        if not (self._cancel_check() or cancel_requested):
            return False

        await self._mark_cancelled(session, job)
        return True

    async def _mark_cancelled(self, session: AsyncSession, job: IngestionJob) -> None:
        """Mark job as cancelled."""
        try:
            if job.document_id:
                document = await session.get(Document, job.document_id)
                if document:
                    document.status = "DELETED"

                result = await session.execute(
                    select(DocumentChunk.id).where(
                        DocumentChunk.document_id == job.document_id
                    )
                )
                chunk_ids = [str(cid) for (cid,) in result.all()]
                if chunk_ids:
                    kb = await session.get(KnowledgeBase, job.knowledge_base_id)
                    await self.index_manager.delete_nodes(
                        kb_id=job.knowledge_base_id,
                        node_ids=chunk_ids,
                        store_type=kb.vector_store_type if kb else None,
                    )
        except Exception as e:
            logger.warning(f"Cancel cleanup failed: {e}")

        job.status = "CANCELED"
        job.stage = None
        await session.commit()

        await self._emit_event(session, "canceled", {"job_id": str(self.job_id)})
        logger.info(f"Ingestion job {self.job_id} was cancelled")

    async def _mark_failed(self, session: AsyncSession, error: str) -> None:
        """Mark job as failed."""
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
        name = (filename or file_path or "").lower()
        ext_map = {
            ".pdf": "pdf",
            ".xlsx": "xlsx",
            ".xls": "xls",
            ".csv": "csv",
            ".docx": "docx",
            ".doc": "doc",
            ".txt": "txt",
            ".md": "md",
        }
        for ext, ftype in ext_map.items():
            if name.endswith(ext):
                return ftype
        return "unknown"
