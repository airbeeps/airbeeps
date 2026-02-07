import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class KnowledgeBaseCreate(BaseModel):
    """Create Knowledge Base Request"""

    name: str = Field(..., max_length=200, description="Knowledge base name")
    description: str | None = Field(None, description="Knowledge base description")
    embedding_model_id: str | None = Field(
        None, description="Embedding model ID (UUID format)"
    )
    vector_store_type: str | None = Field(
        default=None,
        description="Vector store type: qdrant, chromadb, pgvector, milvus",
    )
    retrieval_config: dict[str, Any] | None = Field(
        default=None, description="Retrieval configuration (hybrid, reranking, etc.)"
    )


class KnowledgeBaseUpdate(BaseModel):
    """Update Knowledge Base Request"""

    name: str | None = Field(None, max_length=200, description="Knowledge base name")
    description: str | None = Field(None, description="Knowledge base description")
    embedding_model_id: str | None = Field(
        None, description="Embedding model ID (UUID format)"
    )
    vector_store_type: str | None = Field(
        None, description="Vector store type: qdrant, chromadb, pgvector, milvus"
    )
    retrieval_config: dict[str, Any] | None = Field(
        None, description="Retrieval configuration (hybrid, reranking, etc.)"
    )


class KnowledgeBaseResponse(BaseModel):
    """Knowledge Base Response"""

    id: uuid.UUID
    name: str
    description: str | None
    embedding_model_id: uuid.UUID | None
    embedding_model_name: str | None = None
    vector_store_type: str
    retrieval_config: dict[str, Any]
    reindex_required: bool
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentCreate(BaseModel):
    """Create Document Request"""

    title: str = Field(..., max_length=500, description="Document title")
    content: str = Field(..., min_length=1, description="Document content")
    knowledge_base_id: uuid.UUID = Field(..., description="Knowledge base ID")
    source_url: str | None = Field(None, max_length=1000, description="Source URL")
    file_path: str | None = Field(None, max_length=1000, description="File path")
    file_type: str | None = Field(
        None,
        max_length=50,
        description="File type, e.g., 'pdf', 'txt', 'docx', 'md' etc.",
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Metadata"
    )


class DocumentCreateFromFile(BaseModel):
    """Create Document From File Request"""

    file_path: str = Field(..., max_length=1000, description="File storage path")
    knowledge_base_id: uuid.UUID = Field(..., description="Knowledge base ID")
    filename: str | None = Field(
        None,
        max_length=255,
        description="Original filename (optional, used to infer title and file type)",
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Extra metadata"
    )
    dedup_strategy: str = Field(
        default="replace",
        description="Deduplication strategy: skip|replace|version",
    )
    clean_data: bool = Field(
        default=False,
        description="Apply ingestion cleaning (remove banners, inline image tags, extra blanks)",
    )


class DocumentResponse(BaseModel):
    """Document Response"""

    id: uuid.UUID
    title: str
    source_url: str | None
    file_path: str | None
    file_type: str | None
    file_hash: str | None
    knowledge_base_id: uuid.UUID
    status: str
    doc_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentUpsertResponse(DocumentResponse):
    """Document Response with dedup metadata"""

    dedup_status: str | None = Field(
        default=None, description="created|skipped|replaced|versioned"
    )
    replaced_document_id: uuid.UUID | None = Field(
        default=None, description="Document ID that was replaced"
    )


class DocumentListResponse(BaseModel):
    """Document List Response"""

    id: uuid.UUID
    title: str
    source_url: str | None
    file_path: str | None
    file_type: str | None
    file_hash: str | None
    knowledge_base_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime
    # Exclude full content to reduce response size

    class Config:
        from_attributes = True


class RAGQueryRequest(BaseModel):
    """RAG Query Request"""

    query: str = Field(..., min_length=1, max_length=2000, description="Query question")
    knowledge_base_id: uuid.UUID = Field(..., description="Knowledge base ID")
    k: int = Field(
        default=5, ge=1, le=20, description="Number of relevant documents to return"
    )
    fetch_k: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Initial fetch size before filtering/dedup (defaults to 3x k)",
    )
    score_threshold: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Similarity threshold (0-1); results below are dropped",
    )
    search_type: str = Field(
        default="similarity", description="Retriever search type: similarity|mmr"
    )
    mmr_lambda: float | None = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="MMR lambda (only used when search_type=mmr)",
    )
    filters: dict[str, Any] | None = Field(
        default=None, description="Optional metadata filters (e.g., file_type, status)"
    )
    multi_query: bool = Field(
        default=False,
        description="Generate alternative queries for better recall (heuristic, no LLM).",
    )
    multi_query_count: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Max alternative queries to generate when multi_query is true.",
    )
    rerank_top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional embedding-based rerank of top candidates.",
    )
    rerank_model_id: str | None = Field(
        default=None,
        description="Optional reranker model name (e.g., 'BAAI/bge-reranker-v2-m3').",
    )
    hybrid_enabled: bool = Field(
        default=False,
        description="Enable lightweight BM25 lexical fusion with dense results.",
    )
    hybrid_corpus_limit: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Max chunks to consider for BM25 (limits memory/time).",
    )


class ChunkInfo(BaseModel):
    """Document Chunk Info"""

    content: str
    metadata: dict[str, Any]
    score: float
    similarity: float


class RAGQueryResponse(BaseModel):
    """RAG Query Response"""

    query: str
    knowledge_base_id: uuid.UUID
    score_threshold: float | None = None
    fetch_k: int | None = None
    search_type: str | None = None
    filters: dict[str, Any] | None = None
    multi_query: bool | None = None
    rerank_top_k: int | None = None
    hybrid_enabled: bool | None = None
    documents: list["RAGRetrievedDocument"]


class RAGRetrievedDocument(BaseModel):
    """Retrieved document chunk with metadata"""

    content: str
    metadata: dict[str, Any]
    score: float | None = None
    similarity: float | None = None


class RAGChatRequest(BaseModel):
    """RAG Chat Request"""

    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    knowledge_base_id: uuid.UUID = Field(..., description="Knowledge base ID")
    conversation_id: uuid.UUID | None = Field(None, description="Conversation ID")
    k: int = Field(
        default=3, ge=1, le=10, description="Number of documents to retrieve"
    )
    fetch_k: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Initial fetch size before filtering/dedup (defaults to 3x k)",
    )
    score_threshold: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Similarity threshold (0-1), recommended: 0.3-0.6. Higher values are stricter, >0.7 may filter out most results",
    )
    search_type: str = Field(
        default="similarity", description="Retriever search type: similarity|mmr"
    )
    mmr_lambda: float | None = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="MMR lambda (only used when search_type=mmr)",
    )
    filters: dict[str, Any] | None = Field(
        default=None, description="Optional metadata filters (e.g., file_type, status)"
    )
    multi_query: bool = Field(
        default=False,
        description="Generate alternative queries for better recall (heuristic, no LLM).",
    )
    multi_query_count: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Max alternative queries to generate when multi_query is true.",
    )
    rerank_top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional embedding-based rerank of top candidates.",
    )
    rerank_model_id: str | None = Field(
        default=None,
        description="Optional reranker model name (e.g., 'BAAI/bge-reranker-v2-m3').",
    )
    hybrid_enabled: bool = Field(
        default=False,
        description="Enable lightweight BM25 lexical fusion with dense results.",
    )
    hybrid_corpus_limit: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Max chunks to consider for BM25 (limits memory/time).",
    )


class RAGChatResponse(BaseModel):
    """RAG Chat Response"""

    message: str
    response: str
    knowledge_base_id: uuid.UUID
    conversation_id: uuid.UUID | None
    relevant_chunks: list[ChunkInfo]


class DocumentChunkResponse(BaseModel):
    """Document Chunk Response"""

    id: uuid.UUID
    content: str
    chunk_index: int
    token_count: int | None
    document_id: uuid.UUID
    chunk_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentChunkListResponse(BaseModel):
    """Document Chunk List Response"""

    id: uuid.UUID
    content: str
    chunk_index: int
    token_count: int | None
    document_id: uuid.UUID
    chunk_metadata: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """Error Response"""

    error: str
    detail: str | None = None
    code: str | None = None


# =============================================================================
# Ingestion Job schemas (Phase A: async ingestion with streaming)
# =============================================================================


class IngestionJobCreate(BaseModel):
    """Create Ingestion Job Request (for one-step upload)"""

    knowledge_base_id: uuid.UUID = Field(..., description="Target knowledge base ID")
    dedup_strategy: str = Field(
        default="replace",
        description="Deduplication strategy: skip|replace|version",
    )
    clean_data: bool = Field(
        default=False,
        description="Apply ingestion cleaning (remove banners, inline image tags, extra blanks)",
    )
    profile_id: uuid.UUID | None = Field(
        None,
        description="Optional ingestion profile ID for CSV/XLSX mapping",
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Extra metadata to attach to the document",
    )


class IngestionJobResponse(BaseModel):
    """Ingestion Job Response"""

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    owner_id: uuid.UUID
    file_path: str
    original_filename: str
    file_type: str | None
    file_hash: str | None
    status: str  # PENDING | RUNNING | SUCCEEDED | FAILED | CANCELED
    stage: str | None  # PARSING | CHUNKING | EMBEDDING | UPSERTING
    progress: int  # 0-100
    total_items: int | None
    processed_items: int | None
    document_id: uuid.UUID | None
    chunks_created: int | None
    error_message: str | None
    job_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IngestionJobEventResponse(BaseModel):
    """Ingestion Job Event Response"""

    id: uuid.UUID
    job_id: uuid.UUID
    seq: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class IngestionJobCreateResponse(BaseModel):
    """Response after creating an ingestion job"""

    job_id: uuid.UUID
    message: str = "Ingestion job created and queued"


class IngestionJobListResponse(BaseModel):
    """List of ingestion jobs"""

    items: list[IngestionJobResponse]
    total: int


# =============================================================================
# Ingestion Profile schemas (Phase B: schema/mapping/templates)
# =============================================================================


class IngestionProfileColumnConfig(BaseModel):
    """Column configuration in a profile"""

    name: str = Field(..., description="Column name as it appears in the file")
    type: str = Field(
        default="string", description="Data type: string|number|date|boolean"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Alternative column names"
    )


class IngestionProfileRowTemplate(BaseModel):
    """Row rendering template configuration"""

    format: str = Field(
        default="key_value", description="Template format: key_value|custom"
    )
    include_labels: bool = Field(
        default=True, description="Include column labels in text"
    )
    omit_empty: bool = Field(default=True, description="Omit empty/null values")
    field_order: list[str] | None = Field(
        None, description="Custom field order for text"
    )
    custom_template: str | None = Field(
        None, description="Jinja2 template for custom format"
    )


class IngestionProfileConfig(BaseModel):
    """Full profile configuration"""

    columns: list[IngestionProfileColumnConfig] = Field(default_factory=list)
    metadata_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of column names to metadata keys",
    )
    content_fields: list[str] = Field(
        default_factory=list,
        description="Columns to include in chunk text",
    )
    required_fields: list[str] = Field(
        default_factory=list,
        description="Required columns (validation)",
    )
    validation_mode: str = Field(
        default="warn",
        description="How to handle validation errors: warn|fail|skip",
    )
    row_template: IngestionProfileRowTemplate = Field(
        default_factory=IngestionProfileRowTemplate,
    )


class IngestionProfileCreate(BaseModel):
    """Create Ingestion Profile Request"""

    name: str = Field(..., max_length=200, description="Profile name")
    description: str | None = Field(None, description="Profile description")
    file_types: list[str] = Field(
        default_factory=lambda: ["csv", "xlsx"],
        description="Applicable file types",
    )
    is_default: bool = Field(default=False, description="Set as default for KB")
    config: IngestionProfileConfig = Field(default_factory=IngestionProfileConfig)


class IngestionProfileUpdate(BaseModel):
    """Update Ingestion Profile Request"""

    name: str | None = Field(None, max_length=200, description="Profile name")
    description: str | None = Field(None, description="Profile description")
    file_types: list[str] | None = Field(None, description="Applicable file types")
    is_default: bool | None = Field(None, description="Set as default for KB")
    config: IngestionProfileConfig | None = Field(
        None, description="Profile configuration"
    )


class IngestionProfileResponse(BaseModel):
    """Ingestion Profile Response"""

    id: uuid.UUID
    knowledge_base_id: uuid.UUID | None
    owner_id: uuid.UUID
    name: str
    description: str | None
    file_types: list[str]
    is_default: bool
    is_builtin: bool
    config: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ColumnInferenceResult(BaseModel):
    """Result of column inference from a file"""

    name: str
    inferred_type: str
    sample_values: list[Any]
    non_null_count: int
    suggested_metadata_key: str | None = None


class ProfileInferenceResponse(BaseModel):
    """Response from profile inference endpoint"""

    columns: list[ColumnInferenceResult]
    row_count: int
    sheet_name: str | None
    suggested_profile: IngestionProfileConfig


class RowRenderPreviewRequest(BaseModel):
    """Request to preview row rendering with a profile"""

    profile_config: IngestionProfileConfig
    row_data: dict[str, Any]


class RowRenderPreviewResponse(BaseModel):
    """Response from row render preview"""

    row_text: str
    extracted_metadata: dict[str, Any]


# =============================================================================
# RAG Evaluation schemas
# =============================================================================


class EvaluationSample(BaseModel):
    """A single evaluation sample"""

    question: str = Field(..., description="The user's question")
    answer: str = Field(..., description="The generated answer")
    contexts: list[str] = Field(..., description="Retrieved context passages")
    ground_truth: str | None = Field(None, description="Optional ground truth answer")


class EvaluationRequest(BaseModel):
    """Request to evaluate RAG quality"""

    samples: list[EvaluationSample] = Field(..., description="Evaluation samples")
    metrics: list[str] | None = Field(
        None,
        description="Metrics to compute (default: all). Options: faithfulness, answer_relevancy, context_recall, context_precision",
    )


class EvaluationResponse(BaseModel):
    """RAG evaluation response"""

    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_recall: float | None = None
    context_precision: float | None = None
    overall_score: float | None = None
    num_samples: int = 0
    errors: list[str] = []
    metadata: dict[str, Any] = {}


# =============================================================================
# Vector store configuration schemas
# =============================================================================


# =============================================================================
# Document Preprocessing schemas (Smart Document Preprocessing)
# =============================================================================


class DocumentPreprocessingConfig(BaseModel):
    """Per-file preprocessing options passed during ingestion."""

    # PDF options
    pdf_max_pages: int | None = Field(
        None, ge=1, le=2000, description="Max pages to process"
    )
    pdf_page_range: str | None = Field(
        None, description="Page range to extract, e.g., '1-50' or '1,3,5-10'"
    )
    pdf_enable_ocr: bool = Field(
        default=False, description="Enable OCR for scanned PDFs"
    )

    # Excel/CSV options
    sheet_names: list[str] | None = Field(
        None, description="Sheets to process (None = all sheets)"
    )
    header_row: int = Field(
        default=0, ge=0, description="Row index for header (0-based)"
    )
    skip_rows: int = Field(
        default=0, ge=0, description="Number of rows to skip after header"
    )

    # Chunking options
    chunking_strategy: str = Field(
        default="auto",
        description="Chunking strategy: auto|semantic|hierarchical|sentence",
    )
    chunk_size_override: int | None = Field(
        None, ge=100, le=8000, description="Override chunk size"
    )
    chunk_overlap_override: int | None = Field(
        None, ge=0, le=500, description="Override chunk overlap"
    )

    # General options
    extract_tables_as_markdown: bool = Field(
        default=True, description="Convert tables to markdown format"
    )
    clean_data: bool = Field(
        default=True, description="Apply text cleaning (remove banners, extra blanks)"
    )

    @model_validator(mode="after")
    def validate_page_range(self):
        """Validate page range format if provided."""
        if self.pdf_page_range:
            # Basic validation: allow digits, commas, hyphens, spaces
            import re

            if not re.match(r"^[\d,\-\s]+$", self.pdf_page_range):
                raise ValueError(
                    "Invalid page range format. Use format like '1-50' or '1,3,5-10'"
                )
        return self


class PdfInfoResponse(BaseModel):
    """Response from PDF info endpoint."""

    page_count: int
    file_size_bytes: int
    has_text: bool = Field(
        description="True if PDF contains extractable text (not scanned)"
    )
    title: str | None = None
    author: str | None = None
    is_encrypted: bool = False


class ExcelSheetInfo(BaseModel):
    """Information about a single Excel sheet."""

    name: str
    row_count: int
    column_count: int
    columns: list[str] = Field(default_factory=list, description="Column headers")


class ExcelSheetsResponse(BaseModel):
    """Response from Excel sheets discovery endpoint."""

    sheets: list[ExcelSheetInfo]
    file_name: str | None = None


class PreviewRowsResponse(BaseModel):
    """Response from preview rows endpoint."""

    sheet_name: str | None = None
    rows: list[dict[str, Any]]
    columns: list[str]
    total_rows: int


class VectorStoreConfig(BaseModel):
    """Vector store configuration"""

    store_type: str = Field(
        default="qdrant",
        description="Vector store type: qdrant, chromadb, pgvector, milvus",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Store-specific configuration",
    )


class RetrievalConfigSchema(BaseModel):
    """Retrieval configuration"""

    use_hybrid: bool = Field(default=True, description="Enable hybrid search")
    use_rerank: bool = Field(default=True, description="Enable reranking")
    reranker_model: str | None = Field(None, description="Reranker model")
    use_hierarchical: bool = Field(
        default=True, description="Enable hierarchical chunks"
    )
    query_transform: str = Field(
        default="multi_query",
        description="Query transform type: none, hyde, multi_query, step_back",
    )
    semantic_chunking: bool = Field(
        default=True, description="Enable semantic chunking"
    )


class RAGConfigPreview(BaseModel):
    """RAG configuration for preview queries"""

    retrieval_count: int = Field(default=5, ge=1, le=20, description="Top K results")
    similarity_threshold: float | None = Field(
        default=0.7, ge=0.0, le=1.0, description="Similarity threshold"
    )
    hybrid_enabled: bool = Field(default=False, description="Enable hybrid search")
    multi_query: bool = Field(default=False, description="Enable multi-query")
    multi_query_count: int = Field(
        default=3, ge=1, le=5, description="Number of query variants"
    )
    rerank_model_id: str | None = Field(None, description="Reranker model ID")
    rerank_top_k: int | None = Field(
        None, ge=1, le=50, description="Rerank top K candidates"
    )


class PipelinePreviewRequest(BaseModel):
    """Request for previewing RAG pipeline with test query"""

    query: str = Field(..., min_length=1, max_length=2000, description="Test query")
    rag_config: RAGConfigPreview | None = Field(
        None, description="Optional RAG config to use for preview"
    )


class PipelinePreviewResponse(BaseModel):
    """Response for pipeline preview"""

    query: str
    documents: list[RAGRetrievedDocument]
    config_used: dict[str, Any] = Field(
        default_factory=dict, description="Actual config values used"
    )
