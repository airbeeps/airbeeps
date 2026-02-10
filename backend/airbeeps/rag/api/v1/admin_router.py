import logging
import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.auth import current_active_user, current_superuser
from airbeeps.database import get_async_session
from airbeeps.files.models import FileStatus
from airbeeps.files.service import FileService
from airbeeps.files.storage import storage_service
from airbeeps.rag.models import Document, KnowledgeBase
from airbeeps.rag.service import RAGService
from airbeeps.users.models import User

from .schemas import (
    DocumentChunkListResponse,
    DocumentCreateFromFile,
    DocumentListResponse,
    DocumentPreprocessingConfig,
    DocumentResponse,
    EvaluationRequest,
    EvaluationResponse,
    ExcelSheetInfo,
    ExcelSheetsResponse,
    IngestionJobResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    PdfInfoResponse,
    PipelinePreviewRequest,
    PipelinePreviewResponse,
    PreviewRowsResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGRetrievedDocument,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# NOTE: Changing embedding model or chunk parameters via update_knowledge_base sets
# reindex_required=True, blocking ingestion/retrieval until reindex is run.


@router.get(
    "/knowledge-bases",
    response_model=Page[KnowledgeBaseResponse],
    summary="Get all knowledge bases (Admin)",
    description="Admin view all users' knowledge bases",
)
async def list_all_knowledge_bases(
    search: str | None = Query(None, description="Search in name or description"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get all knowledge bases (Admin)"""
    from sqlalchemy.orm import selectinload

    logger.info(f"Admin user {current_user.id} listing all knowledge bases")
    try:
        query = (
            select(KnowledgeBase)
            .options(selectinload(KnowledgeBase.embedding_model))
            .where(KnowledgeBase.status == "ACTIVE")
        )

        # Apply search filter
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (KnowledgeBase.name.ilike(search_term))
                | (KnowledgeBase.description.ilike(search_term))
            )

        query = query.order_by(KnowledgeBase.created_at.desc())

        def transform_kb(items: list[KnowledgeBase]) -> list[KnowledgeBaseResponse]:
            return [
                KnowledgeBaseResponse(
                    id=kb.id,
                    name=kb.name,
                    description=kb.description,
                    embedding_model_id=kb.embedding_model_id,
                    embedding_model_name=kb.embedding_model.display_name
                    if kb.embedding_model
                    else None,
                    chunk_size=kb.chunk_size,
                    chunk_overlap=kb.chunk_overlap,
                    reindex_required=kb.reindex_required,
                    status=kb.status,
                    created_at=kb.created_at,
                    updated_at=kb.updated_at,
                )
                for kb in items
            ]

        result = await sqlalchemy_paginate(session, query, transformer=transform_kb)
        logger.debug(
            f"Retrieved {len(result.items) if hasattr(result, 'items') else 'paginated'} knowledge bases"
        )
        return result
    except Exception as e:
        logger.error(
            f"Failed to retrieve knowledge bases for admin user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve knowledge bases",
        )


@router.get(
    "/knowledge-bases/all",
    response_model=list[KnowledgeBaseResponse],
    summary="Get all knowledge bases (No pagination)",
    description="Admin view all knowledge bases list, without pagination",
)
async def list_all_knowledge_bases_without_pagination(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get all knowledge bases (No pagination)"""
    from sqlalchemy.orm import selectinload

    logger.info(
        f"Admin user {current_user.id} listing all knowledge bases without pagination"
    )
    try:
        result = await session.execute(
            select(KnowledgeBase)
            .options(selectinload(KnowledgeBase.embedding_model))
            .where(KnowledgeBase.status == "ACTIVE")
            .order_by(KnowledgeBase.created_at.desc())
        )
        kbs = result.scalars().all()
        logger.debug(f"Retrieved {len(kbs)} knowledge bases")
        return [
            KnowledgeBaseResponse(
                id=kb.id,
                name=kb.name,
                description=kb.description,
                embedding_model_id=kb.embedding_model_id,
                embedding_model_name=kb.embedding_model.display_name
                if kb.embedding_model
                else None,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                reindex_required=kb.reindex_required,
                status=kb.status,
                created_at=kb.created_at,
                updated_at=kb.updated_at,
            )
            for kb in kbs
        ]
    except Exception as e:
        logger.error(
            f"Failed to retrieve knowledge bases for admin user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve knowledge bases",
        )


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseResponse,
    summary="Create knowledge base",
    description="Create a new knowledge base for storing and retrieving documents",
)
async def create_knowledge_base(
    kb_data: KnowledgeBaseCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Create knowledge base"""
    logger.info(f"Creating knowledge base '{kb_data.name}' for user {current_user.id}")
    try:
        service = RAGService(session)

        kb = await service.create_knowledge_base(
            name=kb_data.name,
            description=kb_data.description,
            embedding_model_id=kb_data.embedding_model_id,
            owner_id=current_user.id,
            vector_store_type=kb_data.vector_store_type,
            retrieval_config=kb_data.retrieval_config,
        )
        logger.info(f"Successfully created knowledge base {kb.id} named '{kb.name}'")
        return kb
    except ValueError as e:
        logger.warning(f"Invalid data for knowledge base creation: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to create knowledge base for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create knowledge base",
        )


@router.put(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    summary="Update knowledge base",
    description="Update knowledge base basic info. Changing embedding model or chunk parameters marks KB for reindex.",
)
async def update_knowledge_base(
    kb_id: uuid.UUID,
    kb_data: KnowledgeBaseUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Update knowledge base

    Changing embedding model or chunk parameters will set reindex_required so
    ingestion/retrieval is blocked until reindex is run.
    """
    logger.info(f"Updating knowledge base {kb_id} by user {current_user.id}")
    try:
        # Query knowledge base
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()
        if not kb:
            logger.warning(f"Knowledge base {kb_id} not found for update")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )

        changed = False

        # Allow setting embedding_model_id and mark reindex if it changes
        if kb_data.embedding_model_id is not None:
            if kb.embedding_model_id is None:
                logger.debug(
                    f"Setting embedding model {kb_data.embedding_model_id} for KB {kb_id}"
                )
                kb.embedding_model_id = kb_data.embedding_model_id
                changed = True
            elif str(kb.embedding_model_id) != kb_data.embedding_model_id:
                logger.warning(
                    "Embedding model for KB %s changed from %s to %s; marking reindex required",
                    kb_id,
                    kb.embedding_model_id,
                    kb_data.embedding_model_id,
                )
                kb.embedding_model_id = kb_data.embedding_model_id
                kb.reindex_required = True
                changed = True

        # Fields allowed to update
        updatable_fields = [
            ("name", kb_data.name),
            ("description", kb_data.description),
            ("vector_store_type", kb_data.vector_store_type),
            ("retrieval_config", kb_data.retrieval_config),
        ]

        for field_name, new_value in updatable_fields:
            if new_value is not None and getattr(kb, field_name) != new_value:
                logger.debug(
                    f"Updating KB {kb_id} field '{field_name}' to '{new_value}'"
                )
                setattr(kb, field_name, new_value)
                changed = True

        if not changed:
            logger.debug(f"No changes detected for KB {kb_id}")
            return kb  # Return directly if no changes

        await session.commit()
        await session.refresh(kb)
        logger.info(f"Successfully updated knowledge base {kb_id}")
        return kb
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to update knowledge base {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update knowledge base",
        )


@router.get(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    summary="Get knowledge base details (Admin)",
    description="Admin view details of any knowledge base",
)
async def get_knowledge_base_admin(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get knowledge base details (Admin)"""
    logger.debug(f"Admin user {current_user.id} retrieving knowledge base {kb_id}")
    try:
        from sqlalchemy.orm import selectinload

        result = await session.execute(
            select(KnowledgeBase)
            .options(selectinload(KnowledgeBase.embedding_model))
            .where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()

        if not kb:
            logger.warning(f"Knowledge base {kb_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )

        logger.debug(f"Successfully retrieved knowledge base {kb_id}")
        # Build response with model name
        return KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            embedding_model_id=kb.embedding_model_id,
            embedding_model_name=kb.embedding_model.display_name
            if kb.embedding_model
            else None,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            reindex_required=kb.reindex_required,
            status=kb.status,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve knowledge base {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve knowledge base",
        )


@router.post(
    "/knowledge-bases/{kb_id}/preview",
    response_model=PipelinePreviewResponse,
    summary="Preview RAG pipeline",
    description="Run a test query against a knowledge base with optional temporary config without saving.",
)
async def preview_rag_pipeline(
    kb_id: uuid.UUID,
    request: PipelinePreviewRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Preview RAG pipeline with test query and temporary config."""
    logger.info(f"Admin {current_user.id} previewing pipeline for KB {kb_id}")
    try:
        # Verify KB exists
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()
        if not kb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )

        # Build query parameters from request config
        config = request.rag_config
        k = config.retrieval_count if config else 5
        score_threshold = config.similarity_threshold if config else 0.7
        use_hybrid = config.hybrid_enabled if config else False
        multi_query = config.multi_query if config else False
        rerank_top_k = config.rerank_top_k if config else None
        rerank_model_id = config.rerank_model_id if config else None

        service = RAGService(session)
        results = await service.relevance_search(
            query=request.query,
            knowledge_base_id=kb_id,
            k=k,
            score_threshold=score_threshold,
            use_hybrid=use_hybrid,
            query_transform="multi_query" if multi_query else None,
            rerank_top_k=rerank_top_k,
            rerank_model_id=rerank_model_id,
        )

        retrieved_docs = [
            RAGRetrievedDocument(
                content=result.content,
                metadata=result.metadata or {},
                score=result.score,
                similarity=result.score,
            )
            for result in results
        ]

        return PipelinePreviewResponse(
            query=request.query,
            documents=retrieved_docs,
            config_used={
                "retrieval_count": k,
                "similarity_threshold": score_threshold,
                "hybrid_enabled": use_hybrid,
                "multi_query": multi_query,
                "rerank_top_k": rerank_top_k,
                "rerank_model_id": rerank_model_id,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline preview failed for KB {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline preview failed: {e!s}",
        )


@router.post(
    "/knowledge-bases/{kb_id}/reindex",
    summary="Reindex knowledge base",
    description="Rebuild all document chunks and vectors using current embedding model and chunk settings.",
)
async def reindex_knowledge_base(
    kb_id: uuid.UUID,
    clean_data: bool = False,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Reindex all documents in a knowledge base (admin)."""
    logger.info("Admin %s requested reindex for KB %s", current_user.id, kb_id)
    try:
        service = RAGService(session)
        result = await service.reindex_knowledge_base(kb_id, clean_data=clean_data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Failed to reindex KB %s: %s", kb_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reindex knowledge base",
        )


class KBHealthMetrics(BaseModel):
    """Knowledge base health metrics."""

    # Document stats
    total_documents: int
    active_documents: int
    failed_documents: int
    indexing_documents: int

    # Chunk stats
    total_chunks: int
    avg_chunks_per_document: float
    total_tokens: int
    avg_tokens_per_chunk: float

    # Content stats
    duplicate_document_count: int
    unique_file_hashes: int

    # Staleness (time since last update)
    oldest_document_days: float | None
    newest_document_days: float | None
    avg_document_age_days: float | None

    # Coverage (estimated based on chunk content)
    avg_chunk_length: float
    min_chunk_length: int
    max_chunk_length: int

    # Vector store stats
    vector_collection_exists: bool
    estimated_vector_count: int | None

    # Quality indicators
    health_score: float  # 0-100 composite score
    issues: list[str]  # List of detected issues


@router.get(
    "/knowledge-bases/{kb_id}/health",
    response_model=KBHealthMetrics,
    summary="Get KB health metrics",
    description="Get comprehensive health metrics for a knowledge base including staleness, duplication, and quality indicators.",
)
async def get_kb_health_metrics(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get health metrics for a knowledge base."""
    logger.info(f"Getting health metrics for KB {kb_id}")

    try:
        from airbeeps.rag.index_manager import get_index_manager
        from airbeeps.rag.models import DocumentChunk

        # Verify KB exists
        kb = await session.get(KnowledgeBase, kb_id)
        if not kb or kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        # Document stats
        doc_stats_query = select(
            func.count(Document.id).label("total"),
            func.count(Document.id).filter(Document.status == "ACTIVE").label("active"),
            func.count(Document.id).filter(Document.status == "FAILED").label("failed"),
            func.count(Document.id)
            .filter(Document.status == "INDEXING")
            .label("indexing"),
        ).where(Document.knowledge_base_id == kb_id)

        doc_stats = await session.execute(doc_stats_query)
        doc_row = doc_stats.one()

        total_documents = doc_row.total or 0
        active_documents = doc_row.active or 0
        failed_documents = doc_row.failed or 0
        indexing_documents = doc_row.indexing or 0

        # Chunk stats
        chunk_stats_query = (
            select(
                func.count(DocumentChunk.id).label("total"),
                func.sum(DocumentChunk.token_count).label("total_tokens"),
                func.avg(DocumentChunk.token_count).label("avg_tokens"),
                func.avg(func.length(DocumentChunk.content)).label("avg_length"),
                func.min(func.length(DocumentChunk.content)).label("min_length"),
                func.max(func.length(DocumentChunk.content)).label("max_length"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                and_(
                    Document.knowledge_base_id == kb_id,
                    Document.status == "ACTIVE",
                )
            )
        )

        chunk_stats = await session.execute(chunk_stats_query)
        chunk_row = chunk_stats.one()

        total_chunks = chunk_row.total or 0
        total_tokens = int(chunk_row.total_tokens or 0)
        avg_tokens = float(chunk_row.avg_tokens or 0)
        avg_length = float(chunk_row.avg_length or 0)
        min_length = int(chunk_row.min_length or 0)
        max_length = int(chunk_row.max_length or 0)

        avg_chunks_per_doc = total_chunks / max(active_documents, 1)

        # Duplicate detection
        duplicate_query = select(
            func.count(func.distinct(Document.file_hash)).label("unique_hashes")
        ).where(
            and_(
                Document.knowledge_base_id == kb_id,
                Document.status == "ACTIVE",
                Document.file_hash.isnot(None),
            )
        )
        dup_result = await session.execute(duplicate_query)
        unique_hashes = dup_result.scalar() or 0

        # Count docs with duplicate hashes
        dup_count_query = select(func.count(Document.id)).where(
            and_(
                Document.knowledge_base_id == kb_id,
                Document.status == "ACTIVE",
                Document.file_hash.in_(
                    select(Document.file_hash)
                    .where(
                        and_(
                            Document.knowledge_base_id == kb_id,
                            Document.status == "ACTIVE",
                            Document.file_hash.isnot(None),
                        )
                    )
                    .group_by(Document.file_hash)
                    .having(func.count(Document.id) > 1)
                ),
            )
        )
        dup_count_result = await session.execute(dup_count_query)
        duplicate_count = dup_count_result.scalar() or 0

        # Staleness metrics
        now = datetime.now(UTC)

        age_query = select(
            func.min(Document.created_at).label("oldest"),
            func.max(Document.created_at).label("newest"),
            func.avg(func.extract("epoch", now - Document.created_at) / 86400).label(
                "avg_age_days"
            ),
        ).where(
            and_(
                Document.knowledge_base_id == kb_id,
                Document.status == "ACTIVE",
            )
        )

        age_result = await session.execute(age_query)
        age_row = age_result.one()

        oldest_days = None
        newest_days = None
        avg_age_days = None

        if age_row.oldest:
            oldest_days = (now - age_row.oldest.replace(tzinfo=UTC)).days
        if age_row.newest:
            newest_days = (now - age_row.newest.replace(tzinfo=UTC)).days
        avg_age_days = (
            float(age_row.avg_age_days or 0) if age_row.avg_age_days else None
        )

        # Vector store stats
        index_manager = get_index_manager()
        vector_stats = await index_manager.get_collection_stats(
            kb_id, kb.vector_store_type
        )
        vector_exists = (
            vector_stats.get("exists", False)
            if isinstance(vector_stats, dict)
            else False
        )
        vector_count = (
            vector_stats.get("count") if isinstance(vector_stats, dict) else None
        )

        # Calculate health score and issues
        issues = []
        health_score = 100.0

        # Check for failed documents
        if failed_documents > 0:
            issues.append(f"{failed_documents} document(s) failed to index")
            health_score -= min(20, failed_documents * 5)

        # Check for indexing documents (stuck?)
        if indexing_documents > 0:
            issues.append(f"{indexing_documents} document(s) still indexing")
            health_score -= min(10, indexing_documents * 2)

        # Check for duplicates
        if duplicate_count > 0:
            issues.append(f"{duplicate_count} duplicate document(s) detected")
            health_score -= min(15, duplicate_count * 2)

        # Check for stale content (>30 days old)
        if oldest_days and oldest_days > 30:
            issues.append(f"Oldest document is {oldest_days} days old")
            if oldest_days > 90:
                health_score -= 10

        # Check for reindex required
        if kb.reindex_required:
            issues.append("Reindex required due to configuration changes")
            health_score -= 15

        # Check for empty KB
        if active_documents == 0:
            issues.append("No active documents in knowledge base")
            health_score -= 30

        # Check for no embedding model
        if not kb.embedding_model_id:
            issues.append("No embedding model configured")
            health_score -= 20

        # Vector store mismatch
        if (
            total_chunks > 0
            and vector_count is not None
            and abs(total_chunks - vector_count) > 10
        ):
            issues.append(
                f"Vector count mismatch: {total_chunks} chunks vs {vector_count} vectors"
            )
            health_score -= 10

        health_score = max(0, min(100, health_score))

        return KBHealthMetrics(
            total_documents=total_documents,
            active_documents=active_documents,
            failed_documents=failed_documents,
            indexing_documents=indexing_documents,
            total_chunks=total_chunks,
            avg_chunks_per_document=round(avg_chunks_per_doc, 1),
            total_tokens=total_tokens,
            avg_tokens_per_chunk=round(avg_tokens, 1),
            duplicate_document_count=duplicate_count,
            unique_file_hashes=unique_hashes,
            oldest_document_days=oldest_days,
            newest_document_days=newest_days,
            avg_document_age_days=round(avg_age_days, 1) if avg_age_days else None,
            avg_chunk_length=round(avg_length, 1),
            min_chunk_length=min_length,
            max_chunk_length=max_length,
            vector_collection_exists=vector_exists,
            estimated_vector_count=vector_count,
            health_score=round(health_score, 1),
            issues=issues,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get health metrics for KB {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get health metrics",
        )


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=Page[DocumentListResponse],
    summary="Get knowledge base documents (Admin)",
    description="Admin view all documents in any knowledge base",
)
async def list_documents_admin(
    kb_id: uuid.UUID,
    file_type: str | None = None,
    session: AsyncSession = Depends(get_async_session),
):
    """Get document list in knowledge base (Admin)"""
    logger.debug(f"Listing documents for KB {kb_id}, file_type={file_type}")
    try:
        # Verify knowledge base exists
        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        if not kb_result.scalar_one_or_none():
            logger.warning(f"Knowledge base {kb_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )

        # Build query conditions
        conditions = [Document.knowledge_base_id == kb_id, Document.status == "ACTIVE"]

        # Add filter condition if file type is specified
        if file_type:
            logger.debug(f"Filtering documents by file_type: {file_type}")
            conditions.append(Document.file_type == file_type)

        query = (
            select(Document)
            .where(and_(*conditions))
            .order_by(Document.created_at.desc())
        )
        result = await sqlalchemy_paginate(session, query)
        logger.debug(f"Retrieved documents for KB {kb_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve documents for KB {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents",
        )


class BulkDeleteDocumentsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Document IDs to delete"
    )


@router.delete(
    "/knowledge-bases/{kb_id}/documents",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Bulk delete documents in a knowledge base (Admin)",
    description="Deletes documents (soft delete), removes their vectors, and deletes underlying files.",
)
async def bulk_delete_documents(
    kb_id: uuid.UUID,
    req: BulkDeleteDocumentsRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    logger.info(
        f"Bulk deleting {len(req.ids)} documents from KB {kb_id} by user {current_user.id}"
    )
    try:
        # Ensure KB exists
        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        if not kb_result.scalar_one_or_none():
            logger.warning(f"Knowledge base {kb_id} not found for bulk delete")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )

        service = RAGService(session)
        file_service = FileService(session)

        deleted_count = 0
        for doc_id in req.ids:
            # Fetch document to get file_path before deletion
            doc_result = await session.execute(
                select(Document).where(
                    and_(
                        Document.id == doc_id,
                        Document.knowledge_base_id == kb_id,
                        Document.status == "ACTIVE",
                    )
                )
            )
            document = doc_result.scalar_one_or_none()
            if not document:
                logger.debug(f"Document {doc_id} not found or already deleted")
                continue

            file_path = document.file_path

            # Delete document (soft delete) and vectors
            await service.delete_document(document_id=doc_id, owner_id=None)
            deleted_count += 1
            logger.debug(f"Deleted document {doc_id}")

            # Delete underlying file from storage and mark record deleted if present
            if file_path:
                try:
                    await storage_service.delete_file(file_path)
                    logger.debug(f"Deleted file from storage: {file_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to delete file from storage {file_path}: {e}"
                    )

                try:
                    file_record = await file_service.get_file_by_path(file_path)
                    if file_record:
                        file_record.status = FileStatus.DELETED
                        await session.commit()
                        logger.debug(f"Marked file record as deleted: {file_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to mark file record as deleted {file_path}: {e}"
                    )

        logger.info(
            f"Successfully bulk deleted {deleted_count} documents from KB {kb_id}"
        )
        return
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Failed to bulk delete documents from KB {kb_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete documents",
        )


# =============================================================================
# KB Bulk Operations (Phase 2)
# =============================================================================


class BulkReindexRequest(BaseModel):
    """Request for bulk document reindex."""

    document_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Document IDs to reindex"
    )


class MoveDocumentsRequest(BaseModel):
    """Request to move documents between KBs."""

    document_ids: list[uuid.UUID] = Field(
        ..., min_length=1, description="Document IDs to move"
    )
    target_kb_id: uuid.UUID = Field(..., description="Target knowledge base ID")


class DuplicateInfo(BaseModel):
    """Information about a duplicate document."""

    document_id: uuid.UUID
    title: str
    file_hash: str
    duplicate_count: int
    duplicate_ids: list[uuid.UUID]


@router.post(
    "/knowledge-bases/{kb_id}/documents/bulk-reindex",
    summary="Bulk reindex selected documents",
    description="Reindex specific documents in a knowledge base without reindexing the entire KB.",
)
async def bulk_reindex_documents(
    kb_id: uuid.UUID,
    req: BulkReindexRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Reindex selected documents in a KB."""
    logger.info(
        f"Bulk reindexing {len(req.document_ids)} documents in KB {kb_id} by user {current_user.id}"
    )

    try:
        # Verify KB exists
        kb = await session.get(KnowledgeBase, kb_id)
        if not kb or kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        if not kb.embedding_model_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Knowledge base has no embedding model configured",
            )

        from sqlalchemy.orm import selectinload

        from airbeeps.rag.doc_processor import get_document_processor
        from airbeeps.rag.embeddings import get_embedding_service
        from airbeeps.rag.index_manager import get_index_manager
        from airbeeps.rag.models import DocumentChunk

        embedding_service = get_embedding_service()
        index_manager = get_index_manager()

        # Get embedding model
        embed_model, embed_info = await embedding_service.get_embed_model_with_info(
            str(kb.embedding_model_id)
        )
        embed_dim = embed_info.get("embed_dim", 384)
        doc_processor = get_document_processor(embed_model=embed_model)

        reindexed_count = 0
        errors = []

        for doc_id in req.document_ids:
            try:
                # Load document with chunks
                result = await session.execute(
                    select(Document)
                    .options(selectinload(Document.chunks))
                    .where(
                        and_(
                            Document.id == doc_id,
                            Document.knowledge_base_id == kb_id,
                            Document.status == "ACTIVE",
                        )
                    )
                )
                document = result.scalar_one_or_none()

                if not document:
                    errors.append(
                        {"document_id": str(doc_id), "error": "Document not found"}
                    )
                    continue

                # Delete old vectors
                chunk_ids = [str(c.id) for c in document.chunks]
                if chunk_ids:
                    await index_manager.delete_nodes(
                        kb_id=kb_id,
                        node_ids=chunk_ids,
                        store_type=kb.vector_store_type,
                    )

                # Delete old chunk records
                for chunk in list(document.chunks):
                    await session.delete(chunk)

                # Reprocess document
                from airbeeps.config import settings

                nodes = doc_processor.process_text(
                    content=document.content,
                    metadata={
                        "document_id": str(document.id),
                        "knowledge_base_id": str(kb_id),
                        "title": document.title,
                        **embed_info,
                    },
                    use_semantic=settings.RAG_ENABLE_SEMANTIC_CHUNKING,
                    use_hierarchical=settings.RAG_ENABLE_HIERARCHICAL,
                )

                # Create new chunk records
                chunk_records = []
                for i, node in enumerate(nodes):
                    chunk_record = DocumentChunk(
                        content=node.get_content(),
                        chunk_index=i,
                        token_count=len(node.get_content().split()),
                        document_id=document.id,
                        chunk_metadata={"node_id": node.node_id, **node.metadata},
                    )
                    chunk_records.append(chunk_record)
                    session.add(chunk_record)

                await session.flush()

                # Update node IDs
                for chunk_record, node in zip(chunk_records, nodes, strict=False):
                    node.node_id = str(chunk_record.id)
                    node.metadata["chunk_id"] = str(chunk_record.id)

                # Index nodes
                await index_manager.add_nodes(
                    kb_id=kb_id,
                    nodes=nodes,
                    embed_model=embed_model,
                    store_type=kb.vector_store_type,
                    embed_dim=embed_dim,
                )

                reindexed_count += 1
                logger.debug(f"Reindexed document {doc_id} with {len(nodes)} chunks")

            except Exception as e:
                logger.error(f"Failed to reindex document {doc_id}: {e}", exc_info=True)
                errors.append({"document_id": str(doc_id), "error": str(e)})

        await session.commit()

        return {
            "reindexed_count": reindexed_count,
            "total_requested": len(req.document_ids),
            "errors": errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(
            f"Failed to bulk reindex documents in KB {kb_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reindex documents",
        )


@router.post(
    "/knowledge-bases/{kb_id}/documents/move",
    summary="Move documents to another KB",
    description="Move documents from one knowledge base to another. Vectors are re-embedded for the target KB.",
)
async def move_documents_to_kb(
    kb_id: uuid.UUID,
    req: MoveDocumentsRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Move documents to a different knowledge base."""
    logger.info(
        f"Moving {len(req.document_ids)} documents from KB {kb_id} to KB {req.target_kb_id}"
    )

    if kb_id == req.target_kb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and target knowledge bases are the same",
        )

    try:
        # Verify source KB
        source_kb = await session.get(KnowledgeBase, kb_id)
        if not source_kb or source_kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source knowledge base not found",
            )

        # Verify target KB
        target_kb = await session.get(KnowledgeBase, req.target_kb_id)
        if not target_kb or target_kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target knowledge base not found",
            )

        if not target_kb.embedding_model_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target knowledge base has no embedding model configured",
            )

        from sqlalchemy.orm import selectinload

        from airbeeps.rag.doc_processor import get_document_processor
        from airbeeps.rag.embeddings import get_embedding_service
        from airbeeps.rag.index_manager import get_index_manager
        from airbeeps.rag.models import DocumentChunk

        embedding_service = get_embedding_service()
        index_manager = get_index_manager()

        # Get target embedding model
        embed_model, embed_info = await embedding_service.get_embed_model_with_info(
            str(target_kb.embedding_model_id)
        )
        embed_dim = embed_info.get("embed_dim", 384)
        doc_processor = get_document_processor(embed_model=embed_model)

        moved_count = 0
        errors = []

        for doc_id in req.document_ids:
            try:
                # Load document with chunks
                result = await session.execute(
                    select(Document)
                    .options(selectinload(Document.chunks))
                    .where(
                        and_(
                            Document.id == doc_id,
                            Document.knowledge_base_id == kb_id,
                            Document.status == "ACTIVE",
                        )
                    )
                )
                document = result.scalar_one_or_none()

                if not document:
                    errors.append(
                        {"document_id": str(doc_id), "error": "Document not found"}
                    )
                    continue

                # Delete old vectors from source KB
                chunk_ids = [str(c.id) for c in document.chunks]
                if chunk_ids:
                    await index_manager.delete_nodes(
                        kb_id=kb_id,
                        node_ids=chunk_ids,
                        store_type=source_kb.vector_store_type,
                    )

                # Delete old chunk records
                for chunk in list(document.chunks):
                    await session.delete(chunk)

                # Update document KB reference
                document.knowledge_base_id = req.target_kb_id

                # Reprocess for target KB
                from airbeeps.config import settings

                nodes = doc_processor.process_text(
                    content=document.content,
                    metadata={
                        "document_id": str(document.id),
                        "knowledge_base_id": str(req.target_kb_id),
                        "title": document.title,
                        **embed_info,
                    },
                    use_semantic=settings.RAG_ENABLE_SEMANTIC_CHUNKING,
                    use_hierarchical=settings.RAG_ENABLE_HIERARCHICAL,
                )

                # Create new chunk records
                chunk_records = []
                for i, node in enumerate(nodes):
                    chunk_record = DocumentChunk(
                        content=node.get_content(),
                        chunk_index=i,
                        token_count=len(node.get_content().split()),
                        document_id=document.id,
                        chunk_metadata={"node_id": node.node_id, **node.metadata},
                    )
                    chunk_records.append(chunk_record)
                    session.add(chunk_record)

                await session.flush()

                # Update node IDs
                for chunk_record, node in zip(chunk_records, nodes, strict=False):
                    node.node_id = str(chunk_record.id)
                    node.metadata["chunk_id"] = str(chunk_record.id)

                # Index in target KB
                await index_manager.add_nodes(
                    kb_id=req.target_kb_id,
                    nodes=nodes,
                    embed_model=embed_model,
                    store_type=target_kb.vector_store_type,
                    embed_dim=embed_dim,
                )

                moved_count += 1
                logger.debug(f"Moved document {doc_id} to KB {req.target_kb_id}")

            except Exception as e:
                logger.error(f"Failed to move document {doc_id}: {e}", exc_info=True)
                errors.append({"document_id": str(doc_id), "error": str(e)})

        await session.commit()

        return {
            "moved_count": moved_count,
            "total_requested": len(req.document_ids),
            "target_kb_id": str(req.target_kb_id),
            "errors": errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to move documents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move documents",
        )


@router.get(
    "/knowledge-bases/{kb_id}/duplicates",
    response_model=list[DuplicateInfo],
    summary="Detect duplicate documents in KB",
    description="Find documents with identical file hashes (duplicate content) in a knowledge base.",
)
async def detect_duplicate_documents(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Detect duplicate documents based on file hash."""
    logger.info(f"Detecting duplicates in KB {kb_id}")

    try:
        # Verify KB exists
        kb = await session.get(KnowledgeBase, kb_id)
        if not kb or kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        # Find documents with duplicate file hashes
        # First, get all file hashes that appear more than once

        duplicate_hashes_query = (
            select(
                Document.file_hash,
                func.count(Document.id).label("count"),
            )
            .where(
                and_(
                    Document.knowledge_base_id == kb_id,
                    Document.status == "ACTIVE",
                    Document.file_hash.isnot(None),
                )
            )
            .group_by(Document.file_hash)
            .having(func.count(Document.id) > 1)
        )

        result = await session.execute(duplicate_hashes_query)
        duplicate_hashes = {row[0]: row[1] for row in result.all()}

        if not duplicate_hashes:
            return []

        # Get documents for each duplicate hash
        duplicates = []
        for file_hash, count in duplicate_hashes.items():
            docs_result = await session.execute(
                select(Document)
                .where(
                    and_(
                        Document.knowledge_base_id == kb_id,
                        Document.file_hash == file_hash,
                        Document.status == "ACTIVE",
                    )
                )
                .order_by(Document.created_at.asc())
            )
            docs = docs_result.scalars().all()

            if docs:
                # First document is the "original", rest are duplicates
                original = docs[0]
                duplicate_ids = [d.id for d in docs[1:]]

                duplicates.append(
                    DuplicateInfo(
                        document_id=original.id,
                        title=original.title,
                        file_hash=file_hash,
                        duplicate_count=len(duplicate_ids),
                        duplicate_ids=duplicate_ids,
                    )
                )

        logger.info(f"Found {len(duplicates)} documents with duplicates in KB {kb_id}")
        return duplicates

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to detect duplicates in KB {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to detect duplicates",
        )


@router.post(
    "/knowledge-bases/{kb_id}/deduplicate",
    summary="Remove duplicate documents",
    description="Remove duplicate documents from a KB, keeping the oldest version of each.",
)
async def remove_duplicate_documents(
    kb_id: uuid.UUID,
    keep_strategy: str = Query(
        default="oldest", description="Which duplicate to keep: oldest or newest"
    ),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Remove duplicate documents, keeping one copy based on strategy."""
    logger.info(f"Deduplicating KB {kb_id} with strategy: {keep_strategy}")

    if keep_strategy not in ["oldest", "newest"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_strategy must be 'oldest' or 'newest'",
        )

    try:
        # Get duplicates
        kb = await session.get(KnowledgeBase, kb_id)
        if not kb or kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        # Find duplicate hashes
        duplicate_hashes_query = (
            select(Document.file_hash)
            .where(
                and_(
                    Document.knowledge_base_id == kb_id,
                    Document.status == "ACTIVE",
                    Document.file_hash.isnot(None),
                )
            )
            .group_by(Document.file_hash)
            .having(func.count(Document.id) > 1)
        )

        result = await session.execute(duplicate_hashes_query)
        duplicate_hashes = [row[0] for row in result.all()]

        if not duplicate_hashes:
            return {"removed_count": 0, "message": "No duplicates found"}

        from airbeeps.rag.index_manager import get_index_manager
        from airbeeps.rag.models import DocumentChunk

        index_manager = get_index_manager()
        removed_count = 0

        for file_hash in duplicate_hashes:
            # Get all docs with this hash, ordered by creation time
            order_by = (
                Document.created_at.asc()
                if keep_strategy == "oldest"
                else Document.created_at.desc()
            )

            docs_result = await session.execute(
                select(Document)
                .where(
                    and_(
                        Document.knowledge_base_id == kb_id,
                        Document.file_hash == file_hash,
                        Document.status == "ACTIVE",
                    )
                )
                .order_by(order_by)
            )
            docs = docs_result.scalars().all()

            # Keep first, delete rest
            for doc in docs[1:]:
                # Get chunk IDs for vector deletion
                chunks_result = await session.execute(
                    select(DocumentChunk.id).where(DocumentChunk.document_id == doc.id)
                )
                chunk_ids = [str(cid) for (cid,) in chunks_result.all()]

                if chunk_ids:
                    try:
                        await index_manager.delete_nodes(
                            kb_id=kb_id,
                            node_ids=chunk_ids,
                            store_type=kb.vector_store_type,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete vectors for doc {doc.id}: {e}"
                        )

                doc.status = "DELETED"
                removed_count += 1
                logger.debug(f"Marked duplicate document {doc.id} as deleted")

        await session.commit()

        return {
            "removed_count": removed_count,
            "unique_hashes_processed": len(duplicate_hashes),
            "message": f"Removed {removed_count} duplicate documents",
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to deduplicate KB {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deduplicate",
        )


@router.post(
    "/documents/from-file",
    response_model=IngestionJobResponse,
    summary="Add document from file (DEPRECATED - use /ingest)",
    description="DEPRECATED: This endpoint now redirects to job-based ingestion. Use POST /ingest directly.",
    deprecated=True,
)
async def add_document_from_file(
    doc_data: DocumentCreateFromFile,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    DEPRECATED: Add document to knowledge base from file path.

    This endpoint now creates an ingestion job instead of synchronous processing.
    Use POST /ingest directly for new implementations.
    """
    logger.warning(
        f"Deprecated /documents/from-file called by user {current_user.id}. "
        f"Use /ingest endpoint instead."
    )

    # Redirect to job-based ingestion
    from hashlib import sha256

    from airbeeps.files.storage import storage_service

    # Calculate file hash if not provided
    file_hash = None
    try:
        file_bytes, _ = await storage_service.download_file(doc_data.file_path)
        if hasattr(file_bytes, "read"):
            content = file_bytes.read()
        else:
            content = file_bytes
        file_hash = sha256(content).hexdigest()
    except Exception as e:
        logger.warning(f"Failed to calculate file hash: {e}")

    # Create ingestion job
    job = IngestionJob(
        knowledge_base_id=doc_data.knowledge_base_id,
        owner_id=current_user.id,
        file_path=doc_data.file_path,
        original_filename=doc_data.filename,
        file_type=doc_data.file_path.rsplit(".", 1)[-1].lower()
        if "." in doc_data.file_path
        else None,
        file_hash=file_hash,
        status="PENDING",
        job_config={
            "clean_data": doc_data.clean_data or False,
            "dedup_strategy": doc_data.dedup_strategy or "replace",
            "metadata": doc_data.metadata or {},
        },
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info(
        f"Created ingestion job {job.id} from deprecated /documents/from-file endpoint"
    )

    # Start background ingestion
    import asyncio

    from airbeeps.rag.ingestion_runner import IngestionRunner

    async def run_ingestion():
        runner = IngestionRunner(job.id)
        await runner.run()

    asyncio.create_task(run_ingestion())

    return IngestionJobResponse(
        id=job.id,
        knowledge_base_id=job.knowledge_base_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        original_filename=job.original_filename,
        file_type=job.file_type,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    summary="Get document details",
    description="Get detailed information of a specific document",
)
async def get_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get document details"""
    logger.debug(f"User {current_user.id} retrieving document {doc_id}")
    try:
        from sqlalchemy import and_, select

        from airbeeps.rag.models import Document

        result = await session.execute(
            select(Document).where(
                and_(
                    Document.id == doc_id,
                    Document.owner_id == current_user.id,
                    Document.status == "ACTIVE",
                )
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            logger.warning(f"Document {doc_id} not found for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        logger.debug(f"Successfully retrieved document {doc_id}")
        return document
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve document {doc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document",
        )


@router.get(
    "/documents/preview-row",
    summary="Preview a row from an Excel/CSV document",
    description="Returns row data for a given sheet/row number. Requires ownership or superuser.",
)
async def preview_excel_row(
    file_path: str,
    row_number: int,
    sheet: str | None = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    logger.debug(
        f"User {current_user.id} previewing row {row_number} from {file_path}, sheet={sheet}"
    )
    try:
        # Verify document exists and is accessible
        doc_result = await session.execute(
            select(Document).where(
                and_(Document.file_path == file_path, Document.status == "ACTIVE")
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            logger.warning(f"Document with file_path {file_path} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        if (not current_user.is_superuser) and (document.owner_id != current_user.id):
            logger.warning(
                f"User {current_user.id} denied access to document {file_path}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        file_bytes, _ = await storage_service.download_file(file_path)
        if isinstance(file_bytes, bytes):
            buffer = BytesIO(file_bytes)
        else:
            buffer = file_bytes  # assume BytesIO
        buffer.seek(0)

        sheets = pd.read_excel(buffer, sheet_name=None)
        if not sheets:
            logger.warning(f"No sheets found in Excel file {file_path}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No sheets found in Excel file",
            )
        sheet_name = sheet if sheet and sheet in sheets else next(iter(sheets.keys()))
        df = sheets[sheet_name].dropna(axis=1, how="all")

        # Row number is 1-based in Excel; first data row after header is typically 2
        row_index = max(row_number - 2, 0)
        if row_index >= len(df):
            logger.warning(f"Row {row_number} not found in file {file_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Row not found"
            )

        row = df.iloc[row_index]

        def _clean(val: Any):
            if pd.isna(val):
                return None
            if isinstance(val, float) and val.is_integer():
                return int(val)
            return val

        row_data = {
            str(col): _clean(val) for col, val in row.items() if not pd.isna(val)
        }

        logger.debug(f"Successfully previewed row {row_number} from {file_path}")
        return {
            "sheet": sheet_name,
            "row_number": row_number,
            "row": row_data,
            "file_path": file_path,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to preview row {row_number} from {file_path}: {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview row: {exc}",
        )


# =============================================================================
# Document Preprocessing Endpoints (Smart Document Preprocessing)
# =============================================================================


@router.post(
    "/documents/pdf-info",
    response_model=PdfInfoResponse,
    summary="Get PDF file information",
    description="Upload a PDF and get page count, size, and text detection info for preprocessing.",
)
async def get_pdf_info(
    file: UploadFile = File(...),
    current_user: User = Depends(current_superuser),
):
    """Return PDF page count, file size, has_text (vs scanned)."""
    logger.debug(f"Getting PDF info for file '{file.filename}'")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a PDF",
        )

    try:
        contents = await file.read()
        file_size = len(contents)
        buffer = BytesIO(contents)

        # Try to get PDF info
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader

        reader = PdfReader(buffer)
        page_count = len(reader.pages)

        # Check if PDF has extractable text (not just scanned)
        has_text = False
        for i, page in enumerate(reader.pages[:3]):  # Check first 3 pages
            text = page.extract_text() or ""
            if len(text.strip()) > 50:  # At least 50 chars of text
                has_text = True
                break

        # Get metadata
        metadata = reader.metadata or {}
        title = metadata.get("/Title") if metadata else None
        author = metadata.get("/Author") if metadata else None
        is_encrypted = reader.is_encrypted

        return PdfInfoResponse(
            page_count=page_count,
            file_size_bytes=file_size,
            has_text=has_text,
            title=str(title) if title else None,
            author=str(author) if author else None,
            is_encrypted=is_encrypted,
        )

    except Exception as e:
        logger.error(f"Failed to get PDF info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to analyze PDF: {e!s}",
        )


@router.post(
    "/documents/excel-sheets",
    response_model=ExcelSheetsResponse,
    summary="Get Excel file sheet information",
    description="Upload an Excel file and get list of sheets with row counts.",
)
async def get_excel_sheets(
    file: UploadFile = File(...),
    current_user: User = Depends(current_superuser),
):
    """Return list of sheet names with row/column counts."""
    logger.debug(f"Getting Excel sheets for file '{file.filename}'")

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in [".xlsx", ".xls", ".csv"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an Excel (.xlsx, .xls) or CSV file",
        )

    try:
        contents = await file.read()
        buffer = BytesIO(contents)

        if filename.lower().endswith(".csv"):
            # CSV is a single "sheet"
            df = pd.read_csv(buffer, nrows=0)  # Just read headers
            buffer.seek(0)
            row_count = sum(1 for _ in buffer) - 1  # Count lines minus header
            columns = [str(c) for c in df.columns]

            return ExcelSheetsResponse(
                sheets=[
                    ExcelSheetInfo(
                        name="Sheet1",
                        row_count=max(0, row_count),
                        column_count=len(columns),
                        columns=columns,
                    )
                ],
                file_name=filename,
            )

        # Excel file - read all sheets
        sheets_dict = pd.read_excel(buffer, sheet_name=None, nrows=0)
        buffer.seek(0)

        # Get row counts for each sheet
        sheet_infos = []
        all_sheets = pd.read_excel(buffer, sheet_name=None)

        for sheet_name, df in all_sheets.items():
            df = df.dropna(axis=1, how="all")
            columns = [str(c) for c in df.columns]
            sheet_infos.append(
                ExcelSheetInfo(
                    name=str(sheet_name),
                    row_count=len(df),
                    column_count=len(columns),
                    columns=columns,
                )
            )

        return ExcelSheetsResponse(
            sheets=sheet_infos,
            file_name=filename,
        )

    except Exception as e:
        logger.error(f"Failed to get Excel sheets: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to analyze Excel file: {e!s}",
        )


@router.post(
    "/documents/preview-rows",
    response_model=PreviewRowsResponse,
    summary="Preview rows from Excel/CSV file",
    description="Upload an Excel/CSV file and get first N rows for preview.",
)
async def preview_rows(
    file: UploadFile = File(...),
    sheet: str | None = Form(default=None),
    header_row: int = Form(default=0),
    skip_rows: int = Form(default=0),
    limit: int = Form(default=10),
    current_user: User = Depends(current_superuser),
):
    """Return first N rows as JSON for preview."""
    logger.debug(f"Previewing rows from file '{file.filename}'")

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in [".xlsx", ".xls", ".csv"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an Excel (.xlsx, .xls) or CSV file",
        )

    try:
        contents = await file.read()
        buffer = BytesIO(contents)

        if filename.lower().endswith(".csv"):
            df = pd.read_csv(
                buffer,
                header=header_row,
                skiprows=range(1, skip_rows + 1) if skip_rows else None,
            )
            sheet_name = "Sheet1"
        else:
            sheets = pd.read_excel(buffer, sheet_name=None, header=header_row)
            if not sheets:
                raise ValueError("No sheets found in Excel file")

            sheet_name = (
                sheet if sheet and sheet in sheets else next(iter(sheets.keys()))
            )
            df = sheets[sheet_name]

            # Apply skip_rows after header
            if skip_rows > 0:
                df = df.iloc[skip_rows:]

        df = df.dropna(axis=1, how="all")
        total_rows = len(df)

        # Limit rows for preview
        df = df.head(limit)

        # Clean up values
        def _clean(val):
            if pd.isna(val):
                return None
            if isinstance(val, float) and val.is_integer():
                return int(val)
            return val

        rows = []
        for _, row in df.iterrows():
            row_dict = {str(col): _clean(val) for col, val in row.items()}
            rows.append(row_dict)

        columns = [str(c) for c in df.columns]

        return PreviewRowsResponse(
            sheet_name=sheet_name,
            rows=rows,
            columns=columns,
            total_rows=total_rows,
        )

    except Exception as e:
        logger.error(f"Failed to preview rows: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to preview rows: {e!s}",
        )


@router.get(
    "/documents/{doc_id}/chunks",
    response_model=Page[DocumentChunkListResponse],
    summary="Get document chunks (Admin)",
    description="Admin view all chunks of any document",
)
async def get_document_chunks(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get document chunks (Admin)"""
    logger.debug(
        f"Admin user {current_user.id} retrieving chunks for document {doc_id}"
    )
    try:
        service = RAGService(session)

        # Admin can view chunks of any document, no owner_id verification needed
        chunks = await service.get_document_chunks(
            document_id=doc_id,
            owner_id=None,  # Admin permission, no owner restriction
            skip=0,
            limit=1000,  # Set a large limit to get all chunks
        )

        if not chunks:
            logger.warning(f"Document {doc_id} not found or has no chunks")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or has no chunks",
            )

        # Use fastapi_pagination for pagination
        from sqlalchemy import select

        from airbeeps.rag.models import DocumentChunk

        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        result = await sqlalchemy_paginate(session, query)
        logger.debug(f"Retrieved chunks for document {doc_id}")
        return result

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid document chunk request: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to retrieve chunks for document {doc_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document chunks",
        )


# =============================================================================
# Chunk Viewer Enhancements (Phase 2)
# =============================================================================


class ChunkSearchResult(BaseModel):
    """Search result for chunk content search."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    content_preview: str  # First 200 chars with search term highlighted
    match_count: int
    token_count: int | None
    metadata: dict[str, Any] = {}


class ChunkDetailResponse(BaseModel):
    """Detailed chunk information."""

    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    token_count: int | None
    metadata: dict[str, Any] = {}

    # Navigation
    prev_chunk_id: uuid.UUID | None
    next_chunk_id: uuid.UUID | None

    # Hierarchical info
    parent_chunk_id: uuid.UUID | None
    child_chunk_ids: list[uuid.UUID] = []


@router.get(
    "/documents/{doc_id}/chunks/search",
    response_model=list[ChunkSearchResult],
    summary="Search within document chunks",
    description="Search for text within chunks of a specific document.",
)
async def search_document_chunks(
    doc_id: uuid.UUID,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Search for text within document chunks."""
    logger.debug(f"Searching chunks in document {doc_id} for: {q}")

    try:
        from airbeeps.rag.models import DocumentChunk

        # Verify document exists
        doc_result = await session.execute(
            select(Document).where(
                and_(Document.id == doc_id, Document.status == "ACTIVE")
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Search chunks using ILIKE for case-insensitive search
        query = (
            select(DocumentChunk)
            .where(
                and_(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.content.ilike(f"%{q}%"),
                )
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(limit)
        )

        result = await session.execute(query)
        chunks = result.scalars().all()

        # Build results with match highlighting
        results = []
        for chunk in chunks:
            content = chunk.content
            q_lower = q.lower()
            content_lower = content.lower()

            # Count matches
            match_count = content_lower.count(q_lower)

            # Create preview with context around first match
            first_match_idx = content_lower.find(q_lower)
            if first_match_idx >= 0:
                start = max(0, first_match_idx - 50)
                end = min(len(content), first_match_idx + len(q) + 150)
                preview = content[start:end]
                if start > 0:
                    preview = "..." + preview
                if end < len(content):
                    preview = preview + "..."
            else:
                preview = content[:200] + ("..." if len(content) > 200 else "")

            results.append(
                ChunkSearchResult(
                    chunk_id=chunk.id,
                    document_id=doc_id,
                    document_title=document.title,
                    chunk_index=chunk.chunk_index,
                    content=content,
                    content_preview=preview,
                    match_count=match_count,
                    token_count=chunk.token_count,
                    metadata=chunk.chunk_metadata or {},
                )
            )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to search chunks in document {doc_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search chunks",
        )


@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkDetailResponse,
    summary="Get chunk details with navigation",
    description="Get detailed chunk information including prev/next navigation and hierarchy.",
)
async def get_chunk_detail(
    chunk_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get detailed chunk information with navigation."""
    logger.debug(f"Getting chunk detail for {chunk_id}")

    try:
        from airbeeps.rag.models import DocumentChunk

        # Get the chunk
        chunk = await session.get(DocumentChunk, chunk_id)
        if not chunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chunk not found",
            )

        # Get document
        document = await session.get(Document, chunk.document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Get prev/next chunks
        prev_chunk = None
        next_chunk = None

        if chunk.chunk_index > 0:
            prev_result = await session.execute(
                select(DocumentChunk.id).where(
                    and_(
                        DocumentChunk.document_id == chunk.document_id,
                        DocumentChunk.chunk_index == chunk.chunk_index - 1,
                    )
                )
            )
            prev_id = prev_result.scalar_one_or_none()
            if prev_id:
                prev_chunk = prev_id

        next_result = await session.execute(
            select(DocumentChunk.id).where(
                and_(
                    DocumentChunk.document_id == chunk.document_id,
                    DocumentChunk.chunk_index == chunk.chunk_index + 1,
                )
            )
        )
        next_id = next_result.scalar_one_or_none()
        if next_id:
            next_chunk = next_id

        # Extract hierarchical info from metadata
        metadata = chunk.chunk_metadata or {}
        parent_chunk_id = None
        child_chunk_ids = []

        if metadata.get("parent_node_id"):
            try:
                parent_chunk_id = uuid.UUID(metadata["parent_node_id"])
            except (ValueError, TypeError):
                pass

        if metadata.get("child_node_ids"):
            for child_id in metadata["child_node_ids"]:
                try:
                    child_chunk_ids.append(uuid.UUID(child_id))
                except (ValueError, TypeError):
                    pass

        return ChunkDetailResponse(
            id=chunk.id,
            document_id=chunk.document_id,
            document_title=document.title,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            token_count=chunk.token_count,
            metadata=metadata,
            prev_chunk_id=prev_chunk,
            next_chunk_id=next_chunk,
            parent_chunk_id=parent_chunk_id,
            child_chunk_ids=child_chunk_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chunk detail for {chunk_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get chunk detail",
        )


@router.post(
    "/documents/{doc_id}/reindex-from-chunks",
    summary="Reindex document from existing chunks",
    description="Re-embed and re-index a document using its existing chunks (useful after vector store reset).",
)
async def reindex_document_from_chunks(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Reindex a document using its existing chunks without re-chunking."""
    logger.info(f"Reindexing document {doc_id} from existing chunks")

    try:
        from sqlalchemy.orm import selectinload

        from airbeeps.rag.embeddings import get_embedding_service
        from airbeeps.rag.index_manager import get_index_manager

        # Load document with chunks
        result = await session.execute(
            select(Document)
            .options(
                selectinload(Document.chunks), selectinload(Document.knowledge_base)
            )
            .where(and_(Document.id == doc_id, Document.status == "ACTIVE"))
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        kb = document.knowledge_base
        if not kb or kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Knowledge base not found or inactive",
            )

        if not kb.embedding_model_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Knowledge base has no embedding model configured",
            )

        if not document.chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no chunks to reindex",
            )

        embedding_service = get_embedding_service()
        index_manager = get_index_manager()

        # Get embedding model
        embed_model, embed_info = await embedding_service.get_embed_model_with_info(
            str(kb.embedding_model_id)
        )
        embed_dim = embed_info.get("embed_dim", 384)

        # Delete existing vectors (if any)
        chunk_ids = [str(c.id) for c in document.chunks]
        try:
            await index_manager.delete_nodes(
                kb_id=document.knowledge_base_id,
                node_ids=chunk_ids,
                store_type=kb.vector_store_type,
            )
        except Exception as e:
            logger.warning(f"Failed to delete existing vectors: {e}")

        # Convert chunks to nodes
        from llama_index.core.schema import TextNode

        nodes = []
        for chunk in document.chunks:
            node = TextNode(
                text=chunk.content,
                id_=str(chunk.id),
                metadata={
                    "document_id": str(document.id),
                    "knowledge_base_id": str(document.knowledge_base_id),
                    "title": document.title,
                    "chunk_id": str(chunk.id),
                    "chunk_index": chunk.chunk_index,
                    **embed_info,
                    **(chunk.chunk_metadata or {}),
                },
            )
            node.node_id = str(chunk.id)
            nodes.append(node)

        # Re-embed and index
        await index_manager.add_nodes(
            kb_id=document.knowledge_base_id,
            nodes=nodes,
            embed_model=embed_model,
            store_type=kb.vector_store_type,
            embed_dim=embed_dim,
        )

        logger.info(f"Reindexed document {doc_id} with {len(nodes)} chunks")

        return {
            "document_id": str(doc_id),
            "chunks_reindexed": len(nodes),
            "message": f"Successfully reindexed {len(nodes)} chunks",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to reindex document {doc_id} from chunks: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reindex document",
        )


@router.delete(
    "/knowledge-bases/{kb_id}",
    summary="Delete knowledge base (Admin)",
    description="Admin delete any knowledge base and all its documents",
)
async def delete_knowledge_base_admin(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Delete knowledge base (Admin)"""
    logger.info(f"Admin user {current_user.id} deleting knowledge base {kb_id}")
    try:
        # Get knowledge base
        kb_result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one_or_none()

        if not kb:
            logger.warning(f"Knowledge base {kb_id} not found for deletion")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )

        service = RAGService(session)

        # Soft delete knowledge base
        kb.status = "DELETED"

        # Soft delete all related documents
        documents_result = await session.execute(
            select(Document).where(
                Document.knowledge_base_id == kb_id, Document.status == "ACTIVE"
            )
        )
        documents = documents_result.scalars().all()

        for doc in documents:
            doc.status = "DELETED"

        # Remove vector collection to avoid orphaned embeddings
        try:
            await service.delete_vector_collection(kb_id)
        except Exception as exc:
            logger.warning(
                "Failed to delete vector collection for KB %s: %s", kb_id, exc
            )

        await session.commit()

        logger.info(
            f"Successfully deleted knowledge base {kb_id} and {len(documents)} documents"
        )
        return {
            "message": "Knowledge base deleted successfully",
            "deleted_documents": len(documents),
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to delete knowledge base {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete knowledge base",
        )


@router.delete(
    "/documents/{doc_id}",
    summary="Delete document (Admin)",
    description="Admin delete any document",
)
async def delete_document_admin(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Delete document (Admin)"""
    logger.info(f"Admin user {current_user.id} deleting document {doc_id}")
    try:
        # Get document
        result = await session.execute(select(Document).where(Document.id == doc_id))
        document = result.scalar_one_or_none()

        if not document:
            logger.warning(f"Document {doc_id} not found for deletion")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        # Use RAG service to delete (including vector database cleanup)
        service = RAGService(session)
        # Temporarily set document owner to current admin user to pass permission check
        original_owner = document.owner_id
        success = await service.delete_document(doc_id, original_owner)

        if not success:
            logger.warning(f"Failed to delete document {doc_id} via service")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        logger.info(f"Successfully deleted document {doc_id}")
        return {"message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )


@router.post(
    "/get_relevant_documents",
    response_model=RAGQueryResponse,
)
async def rag_query(
    query_data: RAGQueryRequest, session: AsyncSession = Depends(get_async_session)
):
    """RAG Query using LlamaIndex pipeline"""
    logger.info(f"RAG query for KB {query_data.knowledge_base_id}, k={query_data.k}")
    logger.debug(f"Query: {query_data.query[:100]}...")
    try:
        service = RAGService(session)
        results = await service.relevance_search(
            query=query_data.query,
            knowledge_base_id=query_data.knowledge_base_id,
            k=query_data.k,
            fetch_k=query_data.fetch_k,
            score_threshold=query_data.score_threshold,
            use_hybrid=query_data.hybrid_enabled
            if query_data.hybrid_enabled is not None
            else None,
            use_rerank=query_data.rerank_top_k is not None
            if query_data.rerank_top_k
            else None,
            query_transform="multi_query" if query_data.multi_query else None,
            rerank_top_k=query_data.rerank_top_k,
            rerank_model_id=query_data.rerank_model_id,
        )
        retrieved_docs = [
            RAGRetrievedDocument(
                content=result.content,
                metadata=result.metadata or {},
                score=result.score,
                similarity=result.score,
            )
            for result in results
        ]
        logger.info(
            f"RAG query returned {len(retrieved_docs)} documents for KB {query_data.knowledge_base_id}"
        )
        return RAGQueryResponse(
            query=query_data.query,
            knowledge_base_id=query_data.knowledge_base_id,
            score_threshold=query_data.score_threshold,
            fetch_k=query_data.fetch_k,
            search_type=query_data.search_type,
            filters=query_data.filters,
            multi_query=query_data.multi_query,
            rerank_top_k=query_data.rerank_top_k,
            hybrid_enabled=query_data.hybrid_enabled,
            documents=retrieved_docs,
        )
    except ValueError as e:
        logger.warning(f"Invalid RAG query: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to get relevant documents for KB {query_data.knowledge_base_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get relevant documents",
        )


@router.post(
    "/knowledge-bases/{kb_id}/evaluate",
    response_model=EvaluationResponse,
    summary="Evaluate RAG quality",
    description="Run RAG evaluation on provided samples using RAGAS metrics",
)
async def evaluate_rag(
    kb_id: uuid.UUID,
    request: EvaluationRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Evaluate RAG quality for a knowledge base"""
    logger.info(f"RAG evaluation for KB {kb_id} with {len(request.samples)} samples")
    try:
        from airbeeps.rag.evaluator import EvaluationSample as EvalSample, get_evaluator

        # Convert request samples to evaluator format
        samples = [
            EvalSample(
                question=s.question,
                answer=s.answer,
                contexts=s.contexts,
                ground_truth=s.ground_truth,
            )
            for s in request.samples
        ]

        evaluator = get_evaluator()
        result = await evaluator.evaluate(samples, metrics=request.metrics)

        return EvaluationResponse(
            faithfulness=result.faithfulness,
            answer_relevancy=result.answer_relevancy,
            context_recall=result.context_recall,
            context_precision=result.context_precision,
            overall_score=result.overall_score,
            num_samples=result.num_samples,
            errors=result.errors,
            metadata=result.metadata,
        )
    except Exception as e:
        logger.error(f"RAG evaluation failed for KB {kb_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {e!s}",
        )


@router.get(
    "/stats",
    summary="Get system statistics (Admin)",
    description="Get usage statistics of the RAG system",
)
async def get_rag_stats(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get RAG system statistics"""
    logger.debug(f"Admin user {current_user.id} retrieving RAG statistics")
    try:
        # Count knowledge bases
        kb_count_result = await session.execute(
            select(func.count(KnowledgeBase.id)).where(KnowledgeBase.status == "ACTIVE")
        )
        kb_count = kb_count_result.scalar() or 0

        # Count documents
        doc_count_result = await session.execute(
            select(func.count(Document.id)).where(Document.status == "ACTIVE")
        )
        doc_count = doc_count_result.scalar() or 0

        # Count knowledge bases by user
        kb_by_user_result = await session.execute(
            select(func.count(KnowledgeBase.id).label("count"), KnowledgeBase.owner_id)
            .where(KnowledgeBase.status == "ACTIVE")
            .group_by(KnowledgeBase.owner_id)
        )
        kb_by_user = kb_by_user_result.all()

        logger.info(f"RAG stats: {kb_count} knowledge bases, {doc_count} documents")
        return {
            "total_knowledge_bases": kb_count,
            "total_documents": doc_count,
            "knowledge_bases_by_user": [
                {"user_id": str(row.owner_id), "count": row.count} for row in kb_by_user
            ],
            "avg_documents_per_kb": round(doc_count / kb_count, 2)
            if kb_count > 0
            else 0,
        }
    except Exception as e:
        logger.error(f"Failed to retrieve RAG statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics",
        )


# =============================================================================
# Ingestion Job endpoints (Phase A: async ingestion with streaming)
# =============================================================================

import asyncio
import contextlib
import json

from fastapi import File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from airbeeps.rag.job_queue import JobPriority, get_job_queue
from airbeeps.rag.models import IngestionJob, IngestionJobEvent

from .schemas import (
    IngestionJobCreateResponse,
    IngestionJobResponse,
)


@router.post(
    "/ingestion-jobs/from-upload",
    response_model=IngestionJobCreateResponse,
    summary="Create ingestion job from file upload",
    description="Upload a file and create an ingestion job. Returns job_id immediately for streaming progress.",
)
async def create_ingestion_job_from_upload(
    file: UploadFile = File(...),
    knowledge_base_id: uuid.UUID = Form(...),
    dedup_strategy: str = Form(default="replace"),
    clean_data: bool = Form(default=False),
    profile_id: uuid.UUID | None = Form(default=None),
    preprocessing_config: str | None = Form(default=None),
    priority: str = Form(default="normal"),  # low, normal, high, urgent
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Upload a file and create an async ingestion job.

    Returns a job_id immediately. Use the SSE endpoint to stream progress.
    """
    logger.info(
        f"Creating ingestion job for file '{file.filename}' to KB {knowledge_base_id} by user {current_user.id}"
    )

    try:
        # Load ingestion limits and defaults from system config
        from airbeeps.system_config.service import ConfigService

        config_service = ConfigService()
        limits = await config_service.get_config_value(
            session, "rag_ingestion_limits", {}
        )
        defaults = await config_service.get_config_value(
            session, "rag_ingestion_defaults", {}
        )

        max_file_size_mb = limits.get("max_file_size_mb", 50)
        max_concurrent_jobs = limits.get("max_concurrent_jobs", 3)
        allowed_file_types = limits.get(
            "allowed_file_types", ["pdf", "csv", "xlsx", "xls", "txt", "md", "docx"]
        )

        # Apply defaults if not explicitly provided
        effective_dedup_strategy = (
            dedup_strategy
            if dedup_strategy != "replace"
            else defaults.get("dedup_strategy", "replace")
        )
        effective_clean_data = (
            clean_data if clean_data else defaults.get("clean_data", False)
        )

        # Check file size limit
        if file.size and file.size > max_file_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds limit of {max_file_size_mb}MB",
            )

        # Check file type
        file_ext = ""
        if file.filename:
            file_ext = file.filename.lower().rsplit(".", 1)[-1]
        if file_ext and allowed_file_types and file_ext not in allowed_file_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{file_ext}' not allowed. Allowed: {', '.join(allowed_file_types)}",
            )

        # Check concurrent job limit
        running_count_result = await session.execute(
            select(func.count(IngestionJob.id)).where(
                and_(
                    IngestionJob.status.in_(["PENDING", "RUNNING"]),
                )
            )
        )
        running_count = running_count_result.scalar() or 0
        if running_count >= max_concurrent_jobs:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many concurrent jobs ({running_count}/{max_concurrent_jobs}). Please wait.",
            )

        # Verify KB exists
        kb = await session.get(KnowledgeBase, knowledge_base_id)
        if not kb or kb.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )

        # Store the file
        from airbeeps.files.models import FileType
        from airbeeps.files.service import FileService

        file_service = FileService(session)
        file_record = await file_service.upload_file(
            file=file,
            file_type=FileType.DOCUMENT,
            user_id=current_user.id,
            metadata={"target_kb": str(knowledge_base_id)},
        )

        # Infer file type
        file_type = None
        if file.filename:
            name_lower = file.filename.lower()
            if name_lower.endswith(".pdf"):
                file_type = "pdf"
            elif name_lower.endswith(".xlsx"):
                file_type = "xlsx"
            elif name_lower.endswith(".xls"):
                file_type = "xls"
            elif name_lower.endswith(".csv"):
                file_type = "csv"
            elif name_lower.endswith(".docx"):
                file_type = "docx"
            elif name_lower.endswith(".txt"):
                file_type = "txt"
            elif name_lower.endswith(".md"):
                file_type = "md"

        # Parse and validate preprocessing config if provided
        parsed_preprocessing = None
        if preprocessing_config:
            try:
                preprocessing_dict = json.loads(preprocessing_config)
                parsed_preprocessing = DocumentPreprocessingConfig(
                    **preprocessing_dict
                ).model_dump(exclude_none=True)
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid preprocessing_config: {e}",
                )

        # Create ingestion job with effective config from defaults
        job = IngestionJob(
            knowledge_base_id=knowledge_base_id,
            owner_id=current_user.id,
            file_path=file_record.file_path,
            original_filename=file.filename or "unknown",
            file_type=file_type,
            file_hash=file_record.file_hash,
            status="PENDING",
            job_config={
                "dedup_strategy": effective_dedup_strategy,
                "clean_data": effective_clean_data,
                "profile_id": str(profile_id) if profile_id else None,
                "preprocessing": parsed_preprocessing,
            },
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

        logger.info(f"Created ingestion job {job.id} for file {file.filename}")

        # Map priority string to enum
        priority_map = {
            "low": JobPriority.LOW,
            "normal": JobPriority.NORMAL,
            "high": JobPriority.HIGH,
            "urgent": JobPriority.URGENT,
        }
        job_priority = priority_map.get(priority.lower(), JobPriority.NORMAL)

        # Enqueue for background processing with priority
        queue = get_job_queue()
        await queue.enqueue(job.id, priority=job_priority)

        return IngestionJobCreateResponse(
            job_id=job.id,
            message=f"Ingestion job created and queued (priority: {job_priority.name})",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create ingestion job: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create ingestion job: {e!s}",
        )


@router.get(
    "/ingestion-jobs",
    response_model=list[IngestionJobResponse],
    summary="List ingestion jobs",
    description="List ingestion jobs with optional filtering by KB and status",
)
async def list_ingestion_jobs(
    knowledge_base_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """List ingestion jobs with optional filters."""
    logger.debug(f"Listing ingestion jobs for user {current_user.id}")

    try:
        query = select(IngestionJob).order_by(IngestionJob.created_at.desc())

        conditions = []
        if knowledge_base_id:
            conditions.append(IngestionJob.knowledge_base_id == knowledge_base_id)
        if status_filter:
            conditions.append(IngestionJob.status == status_filter)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.limit(limit)

        result = await session.execute(query)
        jobs = result.scalars().all()

        return jobs

    except Exception as e:
        logger.error(f"Failed to list ingestion jobs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list ingestion jobs",
        )


@router.get(
    "/ingestion-jobs/{job_id}",
    response_model=IngestionJobResponse,
    summary="Get ingestion job status",
    description="Get current status of an ingestion job",
)
async def get_ingestion_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get ingestion job status."""
    logger.debug(f"Getting ingestion job {job_id}")

    job = await session.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found",
        )

    return job


@router.get(
    "/ingestion-jobs/{job_id}/events",
    summary="Stream ingestion job events (SSE)",
    description="Server-Sent Events stream for real-time job progress",
)
async def stream_ingestion_job_events(
    job_id: uuid.UUID,
    request: Request,  # FastAPI Request for reading headers
    last_event_id_query: int | None = Query(None, alias="last_event_id"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Stream ingestion job events via Server-Sent Events.

    Supports reconnection via Last-Event-ID header (SSE standard) or query param fallback.
    """
    logger.debug(f"Starting SSE stream for ingestion job {job_id}")

    # Read Last-Event-ID from header (SSE standard) or fallback to query param
    last_event_id: int | None = None

    # Try to get from header first (SSE standard reconnection)
    header_value = request.headers.get("Last-Event-ID") or request.headers.get(
        "last-event-id"
    )
    if header_value:
        with contextlib.suppress(ValueError, TypeError):
            last_event_id = int(header_value)

    # Fallback to query param
    if last_event_id is None and last_event_id_query is not None:
        last_event_id = last_event_id_query

    # Verify job exists
    job = await session.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found",
        )

    async def event_generator():
        from airbeeps.database import get_async_session_context

        # Use passed last_event_id or start from 0
        last_seq = last_event_id or 0
        terminal_statuses = {"SUCCEEDED", "FAILED", "CANCELED"}

        while True:
            async with get_async_session_context() as db:
                # Get job status
                current_job = await db.get(IngestionJob, job_id)
                if not current_job:
                    yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
                    break

                # Get new events since last_seq
                result = await db.execute(
                    select(IngestionJobEvent)
                    .where(
                        and_(
                            IngestionJobEvent.job_id == job_id,
                            IngestionJobEvent.seq > last_seq,
                        )
                    )
                    .order_by(IngestionJobEvent.seq.asc())
                )
                events = result.scalars().all()

                for event in events:
                    event_data = {
                        "type": event.event_type,
                        "data": event.payload,
                        "seq": event.seq,
                        "timestamp": event.created_at.isoformat(),
                    }
                    yield f"id: {event.seq}\nevent: {event.event_type}\ndata: {json.dumps(event_data)}\n\n"
                    last_seq = event.seq

                # Send heartbeat with current status
                status_data = {
                    "status": current_job.status,
                    "stage": current_job.stage,
                    "progress": current_job.progress,
                    "processed_items": current_job.processed_items,
                    "total_items": current_job.total_items,
                }
                yield f"event: heartbeat\ndata: {json.dumps(status_data)}\n\n"

                # Stop if job is in terminal state
                if current_job.status in terminal_statuses:
                    yield f"event: done\ndata: {json.dumps({'status': current_job.status})}\n\n"
                    break

            # Poll interval
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/ingestion-jobs/{job_id}/cancel",
    response_model=IngestionJobResponse,
    summary="Cancel ingestion job",
    description="Request cancellation of a running ingestion job",
)
async def cancel_ingestion_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Request cancellation of an ingestion job."""
    logger.info(
        f"Cancellation requested for ingestion job {job_id} by user {current_user.id}"
    )

    job = await session.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found",
        )

    if job.status not in {"PENDING", "RUNNING"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in {job.status} status",
        )

    # Persist cancel request (durable across process restarts).
    # Note: JSON columns are not automatically mutation-tracked unless using MutableDict,
    # so we assign a new dict to ensure SQLAlchemy persists the change.
    job.job_config = {**(job.job_config or {}), "cancel_requested": True}

    # Best-effort: reflect intent immediately in stage for UI
    if job.status == "RUNNING":
        job.stage = "CANCELING"
    await session.commit()

    # Request cancellation from queue (best-effort; may be in-process only)
    queue = get_job_queue()
    if job.status == "RUNNING":
        await queue.cancel(job_id)
    else:
        # PENDING - just mark as canceled
        job.status = "CANCELED"
        await session.commit()

    await session.refresh(job)
    return job


@router.post(
    "/ingestion-jobs/{job_id}/retry",
    response_model=IngestionJobCreateResponse,
    summary="Retry failed ingestion job",
    description="Create a new job with the same configuration as a failed job",
)
async def retry_ingestion_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Retry a failed or canceled ingestion job."""
    logger.info(f"Retry requested for ingestion job {job_id} by user {current_user.id}")

    original_job = await session.get(IngestionJob, job_id)
    if not original_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found",
        )

    if original_job.status not in {"FAILED", "CANCELED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only retry jobs in FAILED or CANCELED status, got {original_job.status}",
        )

    # Sanitize job_config for retry (e.g., remove cancellation flag)
    new_job_config = dict(original_job.job_config or {})
    new_job_config.pop("cancel_requested", None)

    # Create new job with same config
    new_job = IngestionJob(
        knowledge_base_id=original_job.knowledge_base_id,
        owner_id=current_user.id,
        file_path=original_job.file_path,
        original_filename=original_job.original_filename,
        file_type=original_job.file_type,
        file_hash=original_job.file_hash,
        status="PENDING",
        job_config=new_job_config,
    )
    session.add(new_job)
    await session.commit()
    await session.refresh(new_job)

    logger.info(f"Created retry job {new_job.id} from original {job_id}")

    # Enqueue for processing
    queue = get_job_queue()
    await queue.enqueue(new_job.id)

    return IngestionJobCreateResponse(
        job_id=new_job.id,
        message="Retry job created and queued",
    )


@router.get(
    "/ingestion-jobs/queue/stats",
    summary="Get job queue statistics",
    description="Get statistics about the ingestion job queue including success rate, avg time, etc.",
)
async def get_job_queue_stats(
    current_user: User = Depends(current_superuser),
):
    """Get job queue statistics."""
    logger.debug(f"Getting job queue stats for user {current_user.id}")

    queue = get_job_queue()
    stats = await queue.get_stats()
    return stats.to_dict()


# =============================================================================
# Ingestion Profile endpoints (Phase B: schema/mapping/templates for CSV/XLSX)
# =============================================================================

from airbeeps.rag.models import IngestionProfile

from .schemas import (
    ColumnInferenceResult,
    IngestionProfileColumnConfig,
    IngestionProfileConfig,
    IngestionProfileCreate,
    IngestionProfileResponse,
    IngestionProfileRowTemplate,
    IngestionProfileUpdate,
    ProfileInferenceResponse,
    RowRenderPreviewRequest,
    RowRenderPreviewResponse,
)


@router.get(
    "/knowledge-bases/{kb_id}/ingestion-profiles",
    response_model=list[IngestionProfileResponse],
    summary="List ingestion profiles for a KB",
    description="Get all ingestion profiles for a knowledge base",
)
async def list_ingestion_profiles(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """List ingestion profiles for a knowledge base."""
    logger.debug(f"Listing ingestion profiles for KB {kb_id}")

    # Verify KB exists
    kb = await session.get(KnowledgeBase, kb_id)
    if not kb or kb.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    result = await session.execute(
        select(IngestionProfile)
        .where(
            and_(
                IngestionProfile.knowledge_base_id == kb_id,
                IngestionProfile.status == "ACTIVE",
            )
        )
        .order_by(
            IngestionProfile.is_default.desc(), IngestionProfile.created_at.desc()
        )
    )
    profiles = result.scalars().all()

    # Also include global builtin profiles (kb_id is None)
    builtin_result = await session.execute(
        select(IngestionProfile).where(
            and_(
                IngestionProfile.knowledge_base_id.is_(None),
                IngestionProfile.is_builtin,
                IngestionProfile.status == "ACTIVE",
            )
        )
    )
    builtin_profiles = builtin_result.scalars().all()

    return list(profiles) + list(builtin_profiles)


@router.post(
    "/knowledge-bases/{kb_id}/ingestion-profiles",
    response_model=IngestionProfileResponse,
    summary="Create ingestion profile",
    description="Create a new ingestion profile for a knowledge base",
)
async def create_ingestion_profile(
    kb_id: uuid.UUID,
    profile_data: IngestionProfileCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Create a new ingestion profile."""
    logger.info(f"Creating ingestion profile '{profile_data.name}' for KB {kb_id}")

    # Verify KB exists
    kb = await session.get(KnowledgeBase, kb_id)
    if not kb or kb.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    # If setting as default, clear other defaults
    if profile_data.is_default:
        await session.execute(
            select(IngestionProfile).where(
                and_(
                    IngestionProfile.knowledge_base_id == kb_id,
                    IngestionProfile.is_default,
                )
            )
        )
        result = await session.execute(
            select(IngestionProfile).where(
                and_(
                    IngestionProfile.knowledge_base_id == kb_id,
                    IngestionProfile.is_default,
                )
            )
        )
        for p in result.scalars().all():
            p.is_default = False

    profile = IngestionProfile(
        knowledge_base_id=kb_id,
        owner_id=current_user.id,
        name=profile_data.name,
        description=profile_data.description,
        file_types=profile_data.file_types,
        is_default=profile_data.is_default,
        is_builtin=False,
        config=profile_data.config.model_dump() if profile_data.config else {},
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)

    logger.info(f"Created ingestion profile {profile.id} for KB {kb_id}")
    return profile


@router.get(
    "/ingestion-profiles/{profile_id}",
    response_model=IngestionProfileResponse,
    summary="Get ingestion profile",
    description="Get a specific ingestion profile by ID",
)
async def get_ingestion_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Get an ingestion profile by ID."""
    profile = await session.get(IngestionProfile, profile_id)
    if not profile or profile.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion profile not found",
        )
    return profile


@router.put(
    "/ingestion-profiles/{profile_id}",
    response_model=IngestionProfileResponse,
    summary="Update ingestion profile",
    description="Update an existing ingestion profile",
)
async def update_ingestion_profile(
    profile_id: uuid.UUID,
    profile_data: IngestionProfileUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Update an ingestion profile."""
    logger.info(f"Updating ingestion profile {profile_id}")

    profile = await session.get(IngestionProfile, profile_id)
    if not profile or profile.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion profile not found",
        )

    if profile.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify builtin profiles",
        )

    # Update fields
    if profile_data.name is not None:
        profile.name = profile_data.name
    if profile_data.description is not None:
        profile.description = profile_data.description
    if profile_data.file_types is not None:
        profile.file_types = profile_data.file_types
    if profile_data.config is not None:
        profile.config = profile_data.config.model_dump()

    # Handle default flag
    if profile_data.is_default is not None:
        if profile_data.is_default and profile.knowledge_base_id:
            # Clear other defaults in this KB
            result = await session.execute(
                select(IngestionProfile).where(
                    and_(
                        IngestionProfile.knowledge_base_id == profile.knowledge_base_id,
                        IngestionProfile.is_default,
                        IngestionProfile.id != profile_id,
                    )
                )
            )
            for p in result.scalars().all():
                p.is_default = False
        profile.is_default = profile_data.is_default

    await session.commit()
    await session.refresh(profile)

    logger.info(f"Updated ingestion profile {profile_id}")
    return profile


@router.delete(
    "/ingestion-profiles/{profile_id}",
    summary="Delete ingestion profile",
    description="Delete an ingestion profile",
)
async def delete_ingestion_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Delete an ingestion profile."""
    logger.info(f"Deleting ingestion profile {profile_id}")

    profile = await session.get(IngestionProfile, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion profile not found",
        )

    if profile.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete builtin profiles",
        )

    profile.status = "DELETED"
    await session.commit()

    return {"message": "Profile deleted successfully"}


@router.post(
    "/ingestion-profiles/infer-from-upload",
    response_model=ProfileInferenceResponse,
    summary="Infer profile from uploaded file",
    description="Upload a CSV/XLSX file and get suggested column mappings",
)
async def infer_profile_from_upload(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Analyze an uploaded CSV/XLSX file and suggest a profile configuration.

    Returns detected columns, inferred types, and a suggested profile.
    """
    logger.info(f"Inferring profile from file '{file.filename}'")

    from io import BytesIO

    import pandas as pd

    try:
        contents = await file.read()
        buffer = BytesIO(contents)

        # Determine file type and read
        filename = file.filename or ""
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(buffer)
            sheet_name = None
        else:
            sheets = pd.read_excel(buffer, sheet_name=None)
            if not sheets:
                raise ValueError("No sheets found in Excel file")
            sheet_name = next(iter(sheets.keys()))
            df = sheets[sheet_name]

        # Drop empty columns
        df = df.dropna(axis=1, how="all")

        # Analyze columns
        columns = []
        metadata_fields = {}
        content_fields = []

        # Common metadata field patterns
        metadata_patterns = {
            "id": ["id", "case_id", "case id", "ticket_id", "ticket id", "record_id"],
            "number": ["number", "case_number", "case number", "ticket_number"],
            "priority": ["priority", "severity", "urgency"],
            "status": ["status", "state"],
            "category": ["category", "type", "classification"],
            "date": ["date", "created", "updated", "resolved"],
        }

        for col in df.columns:
            col_str = str(col)
            col_lower = col_str.lower().strip()

            # Sample values
            sample_values = df[col].dropna().head(5).tolist()
            non_null_count = int(df[col].notna().sum())

            # Infer type
            dtype = df[col].dtype
            if pd.api.types.is_numeric_dtype(dtype):
                inferred_type = "number"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                inferred_type = "date"
            elif pd.api.types.is_bool_dtype(dtype):
                inferred_type = "boolean"
            else:
                inferred_type = "string"

            # Suggest metadata key
            suggested_key = None
            for meta_key, patterns in metadata_patterns.items():
                if any(p in col_lower for p in patterns):
                    suggested_key = meta_key
                    metadata_fields[col_str] = meta_key
                    break

            # If not metadata, likely content
            if suggested_key is None:
                content_fields.append(col_str)

            columns.append(
                ColumnInferenceResult(
                    name=col_str,
                    inferred_type=inferred_type,
                    sample_values=sample_values[:5],
                    non_null_count=non_null_count,
                    suggested_metadata_key=suggested_key,
                )
            )

        # Build suggested profile
        suggested_profile = IngestionProfileConfig(
            columns=[
                IngestionProfileColumnConfig(
                    name=c.name,
                    type=c.inferred_type or "string",
                    aliases=[],
                )
                for c in columns
            ],
            metadata_fields=metadata_fields,
            content_fields=content_fields,
            required_fields=[],
            validation_mode="warn",
            row_template=IngestionProfileRowTemplate(
                format="key_value",
                include_labels=True,
                omit_empty=True,
            ),
        )

        return ProfileInferenceResponse(
            columns=columns,
            row_count=len(df),
            sheet_name=sheet_name,
            suggested_profile=suggested_profile,
        )

    except Exception as e:
        logger.error(f"Failed to infer profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to analyze file: {e!s}",
        )


@router.post(
    "/ingestion-profiles/preview-row-render",
    response_model=RowRenderPreviewResponse,
    summary="Preview row rendering with a profile",
    description="Preview how a row would be rendered using a profile configuration",
)
async def preview_row_render(
    request: RowRenderPreviewRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """
    Preview how a row would be rendered using a profile configuration.

    Returns the rendered row text and extracted metadata.
    """
    logger.debug("Previewing row render")

    profile_config = request.profile_config
    row_data = request.row_data

    # Normalize row_data keys using column aliases (so previews match ingestion behavior)
    try:
        alias_map: dict[str, str] = {}
        for col in profile_config.columns or []:
            canonical = col.name
            if canonical:
                alias_map[canonical.lower().strip()] = canonical
                for a in col.aliases or []:
                    alias_map[str(a).lower().strip()] = canonical

        if alias_map:
            normalized: dict[str, Any] = {}
            for k, v in row_data.items():
                canonical = alias_map.get(str(k).lower().strip(), str(k))
                # Prefer non-empty value if a collision occurs
                if canonical in normalized and (
                    normalized[canonical] is not None
                    and str(normalized[canonical]).strip()
                ):
                    continue
                normalized[canonical] = v
            row_data = normalized
    except Exception:
        # Best-effort only; keep original row_data on any issue
        pass

    # Extract metadata
    extracted_metadata = {}
    for col, meta_key in profile_config.metadata_fields.items():
        if col in row_data and row_data[col] is not None:
            extracted_metadata[meta_key] = str(row_data[col])

    # Build row text
    row_template = profile_config.row_template

    if row_template.format == "key_value":
        parts = []

        # Determine field order
        if row_template.field_order:
            fields = row_template.field_order
        elif profile_config.content_fields:
            fields = profile_config.content_fields
        else:
            fields = list(row_data.keys())

        for field in fields:
            if field not in row_data:
                continue

            val = row_data[field]
            if val is None or str(val).strip() == "":
                if row_template.omit_empty:
                    continue
                val = ""

            if row_template.include_labels:
                parts.append(f"{field}: {val}")
            else:
                parts.append(str(val))

        row_text = "\n".join(parts)
    else:
        # Custom template (Jinja2) - full implementation
        try:
            from jinja2 import (
                BaseLoader,
                Environment,
                TemplateSyntaxError,
                UndefinedError,
            )

            template_str = row_template.custom_template
            if not template_str:
                # Fallback to key_value if no template
                row_text = "\n".join(f"{k}: {v}" for k, v in row_data.items() if v)
            else:
                # autoescape=False is safe here as we control the template content and data
                env = Environment(loader=BaseLoader(), autoescape=False)  # noqa: S701
                template = env.from_string(template_str)
                row_text = template.render(**row_data)
        except TemplateSyntaxError as e:
            row_text = (
                f"[Template syntax error: {e.message}]\n\nFallback:\n"
                + "\n".join(f"{k}: {v}" for k, v in row_data.items() if v)
            )
        except UndefinedError as e:
            row_text = f"[Undefined variable: {e}]\n\nFallback:\n" + "\n".join(
                f"{k}: {v}" for k, v in row_data.items() if v
            )
        except Exception as e:
            row_text = f"[Template error: {e}]\n\nFallback:\n" + "\n".join(
                f"{k}: {v}" for k, v in row_data.items() if v
            )

    return RowRenderPreviewResponse(
        row_text=row_text,
        extracted_metadata=extracted_metadata,
    )
