import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base

if TYPE_CHECKING:
    from airbeeps.ai_models.models import Model


# =============================================================================
# Ingestion Job & Event models (Phase A: async ingestion with streaming)
# =============================================================================


class IngestionJob(Base):
    """
    Persistent record for an ingestion job.

    Tracks the lifecycle of a file ingestion: from upload through parsing,
    chunking, embedding, and vector upsert. Supports streaming progress.
    """

    __tablename__ = "ingestion_jobs"

    # Target KB
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Owner (admin who triggered)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # File info
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Status: PENDING | RUNNING | SUCCEEDED | FAILED | CANCELED
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", nullable=False, index=True
    )

    # Stage: UPLOAD_STORED | PARSING | CHUNKING | EMBEDDING | UPSERTING | FINALIZING
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Progress (0-100)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Counters for granular progress
    total_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_items: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Result info
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    chunks_created: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error info
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Job config (dedup strategy, clean_data, profile_id, etc.)
    job_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Relationships
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase", foreign_keys=[knowledge_base_id]
    )
    document: Mapped["Document | None"] = relationship(
        "Document", foreign_keys=[document_id]
    )
    events: Mapped[list["IngestionJobEvent"]] = relationship(
        "IngestionJobEvent",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="IngestionJobEvent.seq",
    )


class IngestionJobEvent(Base):
    """
    Append-only event log for an ingestion job.

    Used for SSE streaming progress and debugging. Events are sequenced
    per job and can be replayed from a specific seq (Last-Event-ID).
    """

    __tablename__ = "ingestion_job_events"

    # Parent job
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Sequence number within job (for ordered replay)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)

    # Event type: job_started, stage_change, progress, log, warning, error, completed, canceled
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Event payload (stage, progress, message, etc.)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Relationship
    job: Mapped["IngestionJob"] = relationship("IngestionJob", back_populates="events")

    __table_args__ = (
        Index("ix_ingestion_job_events_job_seq", "job_id", "seq"),
        # Unique constraint ensures no duplicate seq per job (durability)
        # Note: This is handled by UniqueConstraint in migration
    )


# =============================================================================
# Ingestion Profile model (Phase B: schema/mapping/templates for CSV/XLSX)
# =============================================================================


class IngestionProfile(Base):
    """
    Reusable profile for structured file ingestion (CSV/XLSX).

    Defines column-to-metadata mappings, row text templates, validation rules,
    and column aliases. Replaces hard-coded field_map logic.
    """

    __tablename__ = "ingestion_profiles"

    # Owning KB (profiles are per-KB; can be null for global templates)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Owner (admin who created)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Profile name (e.g., "Support Cases", "Product Catalog")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Applicable file types (e.g., ["csv", "xlsx"])
    file_types: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Is this the default profile for the KB?
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Is this a built-in template (not editable by users)?
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Profile configuration (schema + mapping + template + validation)
    # Structure:
    # {
    #   "columns": [
    #     {"name": "Case ID", "type": "string", "aliases": ["CaseID", "case_id"]},
    #     ...
    #   ],
    #   "metadata_fields": {
    #     "Case ID": "case_id",
    #     "Priority": "priority",
    #     ...
    #   },
    #   "content_fields": ["Subject", "Description", "Resolution"],
    #   "required_fields": ["Case ID"],
    #   "validation_mode": "warn",  # "warn" | "fail" | "skip"
    #   "row_template": {
    #     "format": "key_value",  # "key_value" | "custom"
    #     "include_labels": true,
    #     "omit_empty": true,
    #     "field_order": ["Subject", "Description", "Resolution"],
    #     "custom_template": null  # Jinja2 template if format="custom"
    #   }
    # }
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    # Relationship
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship(
        "KnowledgeBase", foreign_keys=[knowledge_base_id]
    )


class KnowledgeBase(Base):
    """Knowledge Base Table"""

    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration
    embedding_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    reindex_required: Mapped[bool] = mapped_column(Boolean, default=False)

    # Vector store configuration
    vector_store_type: Mapped[str] = mapped_column(String(20), default="qdrant")
    # {
    #   "url": "http://localhost:6333",
    #   "api_key": "...",
    #   "collection_settings": {...}
    # }
    vector_store_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Retrieval configuration
    # {
    #   "use_hybrid": true,
    #   "use_rerank": true,
    #   "reranker_model": "BAAI/bge-reranker-v2-m3",
    #   "use_hierarchical": true,
    #   "query_transform": "multi_query",
    #   "semantic_chunking": true
    # }
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Associated user
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Status
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    # Relationships
    embedding_model: Mapped["Model | None"] = relationship(
        "Model", foreign_keys=[embedding_model_id], post_update=True
    )


class Document(Base):
    """Document Table"""

    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # File type, e.g., 'pdf', 'txt', 'docx', 'md', 'html' etc.
    # Hash of the original file content (for deduplication)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Associated knowledge base
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )

    # Associated user
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Document status
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    # Relationships
    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase", backref="documents"
    )


class DocumentChunk(Base):
    """Document Chunk Table"""

    __tablename__ = "document_chunks"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Associated document
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    # Metadata
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Relationships
    document: Mapped["Document"] = relationship("Document", backref="chunks")
