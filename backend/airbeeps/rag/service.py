"""
RAG Service - SOTA LlamaIndex Implementation.

Orchestrates the complete RAG pipeline:
- Document ingestion with semantic/hierarchical chunking
- Multi-vector-store support (Qdrant, ChromaDB, PGVector, Milvus)
- Query transformation (HyDE, multi-query, step-back)
- Hybrid retrieval (dense + BM25 with RRF fusion)
- Cross-encoder reranking
- Auto-merging for hierarchical chunks
"""

import logging
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import pandas as pd
from llama_index.core.schema import Document as LlamaDocument
from llama_index.core.schema import NodeWithScore, TextNode
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.config import settings
from airbeeps.files.service import FileService

from .cleaners import apply_cleaners
from .content_extractor import DocumentContentExtractor
from .doc_processor import DocumentProcessor, get_document_processor
from .embeddings import EmbeddingService, get_embedding_service
from .hybrid_retriever import build_hybrid_retriever
from .index_manager import IndexManager, get_index_manager
from .models import Document, DocumentChunk, KnowledgeBase
from .query_transform import QueryTransformer, QueryTransformType, get_query_transformer
from .reranker import get_reranker
from .stores import VectorStoreType

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result from a retrieval query."""

    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    # Source info for citations
    node_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    title: str | None = None

    # Retrieval info
    retrieval_sources: list[str] = field(default_factory=list)


@dataclass
class RetrievalConfig:
    """Configuration for retrieval operations."""

    k: int = 5
    fetch_k: int | None = None
    score_threshold: float | None = None

    # Feature flags
    use_hybrid: bool = True
    use_rerank: bool = True
    use_hierarchical: bool = True
    query_transform: str = "multi_query"

    # Reranker settings
    reranker_model: str | None = None
    rerank_top_n: int | None = None

    # Hybrid settings
    hybrid_alpha: float = 0.5

    @classmethod
    def from_settings(cls) -> "RetrievalConfig":
        """Create config from application settings."""
        return cls(
            use_hybrid=settings.RAG_ENABLE_HYBRID_SEARCH,
            use_rerank=settings.RAG_ENABLE_RERANKING,
            use_hierarchical=settings.RAG_ENABLE_HIERARCHICAL,
            query_transform=settings.RAG_QUERY_TRANSFORM_TYPE,
            reranker_model=settings.RAG_RERANKER_MODEL,
            rerank_top_n=settings.RAG_RERANKER_TOP_N,
            hybrid_alpha=settings.RAG_HYBRID_ALPHA,
        )


class RAGService:
    """
    SOTA RAG Service using LlamaIndex.

    Provides end-to-end RAG functionality:
    - Knowledge base management
    - Document ingestion with smart chunking
    - Retrieval with advanced features
    """

    def __init__(
        self,
        session: AsyncSession,
        file_service: FileService | None = None,
    ):
        """
        Initialize the RAG service.

        Args:
            session: SQLAlchemy async session
            file_service: Optional file service for document access
        """
        self.session = session
        self.embedding_service = get_embedding_service()
        self.index_manager = get_index_manager()

        # File handling
        if file_service:
            self.file_service = file_service
        else:
            self.file_service = FileService(session)

        self.content_extractor = DocumentContentExtractor(self.file_service)

        # Document processor (initialized lazily with embedding model)
        self._doc_processor: DocumentProcessor | None = None

    async def _get_doc_processor(
        self, embedding_model_id: str | None = None
    ) -> DocumentProcessor:
        """Get document processor with embedding model for semantic chunking."""
        if embedding_model_id:
            embed_model = await self.embedding_service.get_embed_model(
                embedding_model_id
            )
            return get_document_processor(embed_model=embed_model)

        if self._doc_processor is None:
            self._doc_processor = get_document_processor()

        return self._doc_processor

    # =========================================================================
    # Knowledge Base Management
    # =========================================================================

    async def create_knowledge_base(
        self,
        name: str,
        description: str | None,
        embedding_model_id: str | None,
        owner_id: uuid.UUID,
        vector_store_type: str | None = None,
        retrieval_config: dict[str, Any] | None = None,
    ) -> KnowledgeBase:
        """Create a new knowledge base."""
        logger.info(f"Creating knowledge base '{name}' for owner {owner_id}")

        # Check for existing KB with same name
        existing = await self.session.execute(
            select(KnowledgeBase).where(
                and_(
                    KnowledgeBase.name == name,
                    KnowledgeBase.owner_id == owner_id,
                    KnowledgeBase.status == "ACTIVE",
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Knowledge base with name '{name}' already exists")

        kb = KnowledgeBase(
            name=name,
            description=description,
            owner_id=owner_id,
            embedding_model_id=embedding_model_id,
            vector_store_type=vector_store_type or settings.VECTOR_STORE_TYPE,
            retrieval_config=retrieval_config or {},
        )

        self.session.add(kb)
        await self.session.commit()
        await self.session.refresh(kb)

        logger.info(f"Created knowledge base: {kb.name} (ID: {kb.id})")
        return kb

    async def get_knowledge_base(
        self,
        kb_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
    ) -> KnowledgeBase | None:
        """Get a knowledge base by ID."""
        query = select(KnowledgeBase).where(
            and_(KnowledgeBase.id == kb_id, KnowledgeBase.status == "ACTIVE")
        )
        if owner_id:
            query = query.where(KnowledgeBase.owner_id == owner_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_knowledge_bases(
        self,
        owner_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeBase]:
        """Get all knowledge bases for an owner."""
        result = await self.session.execute(
            select(KnowledgeBase)
            .where(
                and_(
                    KnowledgeBase.owner_id == owner_id,
                    KnowledgeBase.status == "ACTIVE",
                )
            )
            .offset(skip)
            .limit(limit)
            .order_by(KnowledgeBase.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_knowledge_base(
        self,
        kb_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
    ) -> bool:
        """Delete a knowledge base and its vector collection."""
        kb = await self.get_knowledge_base(kb_id, owner_id)
        if not kb:
            return False

        # Delete vector collection
        await self.index_manager.delete_collection(
            kb_id=kb_id,
            store_type=kb.vector_store_type,
        )

        # Soft delete KB
        kb.status = "DELETED"
        await self.session.commit()

        logger.info(f"Deleted knowledge base: {kb_id}")
        return True

    # =========================================================================
    # Document Ingestion
    # =========================================================================

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
        file_hash: str | None = None,
    ) -> Document:
        """Add a document to a knowledge base."""
        logger.info(f"Adding document '{title}' to KB {knowledge_base_id}")

        # Verify KB exists and belongs to user
        kb = await self.get_knowledge_base(knowledge_base_id, owner_id)
        if not kb:
            raise ValueError("Knowledge base not found or access denied")

        if not kb.embedding_model_id:
            raise ValueError("Knowledge base embedding model is not configured")

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

        try:
            # Get embedding model
            (
                embed_model,
                embed_info,
            ) = await self.embedding_service.get_embed_model_with_info(
                str(kb.embedding_model_id)
            )
            embed_dim = embed_info.get("embed_dim", 384)

            # Process content into nodes
            doc_processor = await self._get_doc_processor(str(kb.embedding_model_id))

            base_metadata = {
                "document_id": str(document.id),
                "knowledge_base_id": str(knowledge_base_id),
                "title": title,
                "file_path": file_path,
                "file_type": file_type,
                "source_url": source_url,
                **embed_info,
                **(metadata or {}),
            }

            nodes = doc_processor.process_text(
                content=content,
                metadata=base_metadata,
                use_semantic=settings.RAG_ENABLE_SEMANTIC_CHUNKING,
                use_hierarchical=settings.RAG_ENABLE_HIERARCHICAL,
            )

            # Save chunk records to database with original node IDs preserved
            chunk_records = []
            node_id_map = {}  # Maps original node_id -> chunk_id for relationship updates

            for i, node in enumerate(nodes):
                original_node_id = node.node_id

                # Store relationships before any modifications
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
                self.session.add(chunk_record)

            await self.session.flush()

            # Map original node IDs to chunk IDs
            for chunk_record, node in zip(chunk_records, nodes, strict=False):
                node_id_map[node.node_id] = str(chunk_record.id)

            # Update node IDs and relationships to use chunk IDs
            for chunk_record, node in zip(chunk_records, nodes, strict=False):
                node.node_id = str(chunk_record.id)
                node.metadata["chunk_id"] = str(chunk_record.id)

                # Update relationship IDs to point to new chunk IDs
                if hasattr(node, "relationships"):
                    from llama_index.core.schema import (
                        NodeRelationship,
                        RelatedNodeInfo,
                    )

                    if NodeRelationship.PARENT in node.relationships:
                        parent_rel = node.relationships[NodeRelationship.PARENT]
                        old_parent_id = (
                            parent_rel.node_id
                            if hasattr(parent_rel, "node_id")
                            else str(parent_rel)
                        )
                        if old_parent_id in node_id_map:
                            node.relationships[NodeRelationship.PARENT] = (
                                RelatedNodeInfo(node_id=node_id_map[old_parent_id])
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
                                        RelatedNodeInfo(
                                            node_id=node_id_map[old_child_id]
                                        )
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

            # Index nodes in vector store
            await self.index_manager.add_nodes(
                kb_id=knowledge_base_id,
                nodes=nodes,
                embed_model=embed_model,
                store_type=kb.vector_store_type,
                embed_dim=embed_dim,
            )

            document.status = "ACTIVE"
            await self.session.commit()

            logger.info(
                f"Added document '{title}' with {len(nodes)} chunks to KB {knowledge_base_id}"
            )
            return document

        except Exception as e:
            await self.session.rollback()
            document.status = "FAILED"
            await self.session.commit()
            logger.error(f"Failed to add document '{title}': {e}", exc_info=True)
            raise

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
        """Add a document from a file path."""
        logger.info(
            f"Adding document from file '{filename or file_path}' to KB {knowledge_base_id}"
        )

        # Get file record if exists
        file_record = await self.file_service.get_file_by_path(file_path)
        if file_record:
            title = file_record.filename
            file_hash = file_record.file_hash
        else:
            title = filename or file_path.split("/")[-1]
            file_hash = None

        # Handle deduplication
        dedup_status = "created"
        replaced_id: uuid.UUID | None = None

        if file_hash:
            existing = await self._get_document_by_hash(knowledge_base_id, file_hash)
            if existing:
                if dedup_strategy == "skip":
                    return existing, "skipped", None
                elif dedup_strategy == "replace":
                    replaced_id = existing.id
                    await self.delete_document(existing.id, owner_id)
                    dedup_status = "replaced"

        # Infer file type
        file_type = self._infer_file_type(filename, file_path)

        # Handle tabular files specially
        if file_type in {"xls", "xlsx", "csv"}:
            document = await self._add_tabular_document(
                file_path=file_path,
                title=title,
                knowledge_base_id=knowledge_base_id,
                owner_id=owner_id,
                file_type=file_type,
                file_hash=file_hash,
                metadata=metadata,
                clean_data=clean_data,
            )
            return document, dedup_status, replaced_id

        # Extract content from file
        _, content = await self.content_extractor.extract_from_file_path(
            file_path, filename
        )

        document = await self.add_document(
            title=title,
            content=content,
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
            file_path=file_path,
            file_type=file_type,
            metadata={
                "source_type": "file",
                "original_filename": filename,
                **(metadata or {}),
            },
            file_hash=file_hash,
        )

        return document, dedup_status, replaced_id

    async def _add_tabular_document(
        self,
        file_path: str,
        title: str,
        knowledge_base_id: uuid.UUID,
        owner_id: uuid.UUID,
        file_type: str,
        file_hash: str | None,
        metadata: dict[str, Any] | None,
        clean_data: bool = False,
    ) -> Document:
        """Add a tabular (Excel/CSV) document with row-wise chunking."""
        logger.info(f"Processing tabular file '{title}' for KB {knowledge_base_id}")

        kb = await self.get_knowledge_base(knowledge_base_id, owner_id)
        if not kb or not kb.embedding_model_id:
            raise ValueError("Knowledge base not found or missing embedding model")

        # Download file
        file_bytes, _ = await self.content_extractor._download_file_from_storage(
            file_path
        )
        if isinstance(file_bytes, BytesIO):
            file_bytes.seek(0)
        else:
            file_bytes = BytesIO(file_bytes)

        # Read data
        if file_type == "csv":
            df = pd.read_csv(file_bytes)
            sheet_name = "Sheet1"
        else:
            sheets = pd.read_excel(file_bytes, sheet_name=None)
            if not sheets:
                raise ValueError("No sheets found in Excel file")
            sheet_name = next(iter(sheets.keys()))
            df = sheets[sheet_name]

        df = df.dropna(axis=1, how="all")

        # Create document record
        document = Document(
            title=title,
            content=f"Tabular source: {title}",
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
            file_path=file_path,
            file_type=file_type,
            doc_metadata=metadata or {},
            status="INDEXING",
            file_hash=file_hash,
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)

        try:
            (
                embed_model,
                embed_info,
            ) = await self.embedding_service.get_embed_model_with_info(
                str(kb.embedding_model_id)
            )
            embed_dim = embed_info.get("embed_dim", 384)

            # Create nodes from rows
            nodes = []
            chunk_records = []

            for idx, row in df.iterrows():
                row_text = self._row_to_text(row, df.columns, clean_data)
                if not row_text.strip():
                    continue

                row_number = int(idx) + 2

                node = TextNode(
                    text=row_text,
                    metadata={
                        "document_id": str(document.id),
                        "knowledge_base_id": str(knowledge_base_id),
                        "title": title,
                        "sheet": sheet_name,
                        "row_number": row_number,
                        "file_path": file_path,
                        "file_type": file_type,
                        **embed_info,
                    },
                )
                nodes.append(node)

                chunk_record = DocumentChunk(
                    content=row_text,
                    chunk_index=len(chunk_records),
                    token_count=len(row_text.split()),
                    document_id=document.id,
                    chunk_metadata=node.metadata,
                )
                chunk_records.append(chunk_record)
                self.session.add(chunk_record)

            await self.session.flush()

            # Update node IDs
            for chunk_record, node in zip(chunk_records, nodes, strict=False):
                node.node_id = str(chunk_record.id)
                node.metadata["chunk_id"] = str(chunk_record.id)

            # Index nodes
            await self.index_manager.add_nodes(
                kb_id=knowledge_base_id,
                nodes=nodes,
                embed_model=embed_model,
                store_type=kb.vector_store_type,
                embed_dim=embed_dim,
            )

            document.status = "ACTIVE"
            await self.session.commit()

            logger.info(f"Added tabular document '{title}' with {len(nodes)} rows")
            return document

        except Exception as e:
            await self.session.rollback()
            document.status = "FAILED"
            await self.session.commit()
            logger.error(f"Failed to add tabular document: {e}", exc_info=True)
            raise

    def _row_to_text(
        self, row: pd.Series, columns: pd.Index, clean_data: bool = False
    ) -> str:
        """Convert a DataFrame row to text."""
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

    async def delete_document(
        self,
        document_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
    ) -> bool:
        """Delete a document and its vectors."""
        result = await self.session.execute(
            select(Document)
            .options(
                selectinload(Document.chunks), selectinload(Document.knowledge_base)
            )
            .where(and_(Document.id == document_id, Document.status == "ACTIVE"))
        )
        document = result.scalar_one_or_none()

        if not document:
            return False

        if owner_id and document.owner_id != owner_id:
            return False

        # Get KB to use its configured store type
        kb = document.knowledge_base
        if not kb:
            kb_result = await self.session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == document.knowledge_base_id
                )
            )
            kb = kb_result.scalar_one_or_none()

        store_type = kb.vector_store_type if kb else settings.VECTOR_STORE_TYPE

        # Delete from vector store
        chunk_ids = [str(c.id) for c in document.chunks]
        if chunk_ids:
            await self.index_manager.delete_nodes(
                kb_id=document.knowledge_base_id,
                node_ids=chunk_ids,
                store_type=store_type,
            )

        document.status = "DELETED"
        await self.session.commit()

        logger.info(f"Deleted document {document_id} with {len(chunk_ids)} chunks")
        return True

    # =========================================================================
    # Retrieval
    # =========================================================================

    async def relevance_search(
        self,
        query: str,
        knowledge_base_id: uuid.UUID,
        k: int = 5,
        fetch_k: int | None = None,
        score_threshold: float | None = None,
        use_hybrid: bool | None = None,
        use_rerank: bool | None = None,
        query_transform: str | None = None,
        rerank_top_k: int | None = None,
        rerank_model_id: str | None = None,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        """
        Perform SOTA retrieval on a knowledge base.

        Args:
            query: Search query
            knowledge_base_id: Target knowledge base
            k: Number of results
            fetch_k: Number to fetch before reranking
            score_threshold: Minimum similarity score
            use_hybrid: Enable hybrid search
            use_rerank: Enable reranking
            query_transform: Query transformation type
            rerank_top_k: Reranker top-n
            rerank_model_id: Specific reranker model name (e.g., 'BAAI/bge-reranker-v2-m3')

        Returns:
            List of retrieval results
        """
        logger.debug(f"Relevance search in KB {knowledge_base_id}: {query[:100]}...")

        kb = await self.get_knowledge_base(knowledge_base_id)
        if not kb:
            raise ValueError("Knowledge base not found")

        if not kb.embedding_model_id:
            raise ValueError("Knowledge base embedding model not configured")

        # Apply defaults from settings
        use_hybrid = (
            use_hybrid if use_hybrid is not None else settings.RAG_ENABLE_HYBRID_SEARCH
        )
        use_rerank = (
            use_rerank if use_rerank is not None else settings.RAG_ENABLE_RERANKING
        )
        query_transform = query_transform or settings.RAG_QUERY_TRANSFORM_TYPE
        fetch_k = fetch_k or max(k * 3, k)

        # Get embedding model
        (
            embed_model,
            embed_info,
        ) = await self.embedding_service.get_embed_model_with_info(
            str(kb.embedding_model_id)
        )
        embed_dim = embed_info.get("embed_dim", 384)

        # Get index
        index = await self.index_manager.get_index(
            kb_id=knowledge_base_id,
            embed_model=embed_model,
            store_type=kb.vector_store_type,
            embed_dim=embed_dim,
        )

        # Transform query
        # For LLM-based transforms (HyDE, step-back), we need to provide an LLM
        llm = None
        if query_transform in ["hyde", "step_back"]:
            try:
                from airbeeps.llm.service import get_default_llm

                llm = await get_default_llm()
            except Exception as e:
                logger.warning(f"Failed to get LLM for query transformation: {e}")

        transformer = get_query_transformer(transform_type=query_transform, llm=llm)
        queries = await transformer.transform(query)

        # Build retriever
        storage_context = self.index_manager.get_storage_context(knowledge_base_id)

        if use_hybrid and storage_context:
            retriever = build_hybrid_retriever(
                index=index,
                top_k=fetch_k,
                storage_context=storage_context,
                use_auto_merge=settings.RAG_ENABLE_HIERARCHICAL,
            )
        else:
            retriever = index.as_retriever(similarity_top_k=fetch_k)

        # Retrieve for all query variants and merge
        all_nodes: dict[str, NodeWithScore] = {}

        for q in queries:
            nodes = await retriever.aretrieve(q)
            for node in nodes:
                node_id = node.node.node_id
                if node_id not in all_nodes or (node.score or 0) > (
                    all_nodes[node_id].score or 0
                ):
                    all_nodes[node_id] = node

        results_list = list(all_nodes.values())

        # Apply reranking
        if use_rerank and results_list:
            from llama_index.core.schema import QueryBundle

            query_bundle = QueryBundle(query_str=query)

            # Check for ensemble reranking config in kwargs or KB retrieval_config
            ensemble_config = kwargs.get("ensemble_rerankers")
            if ensemble_config is None and kb.retrieval_config:
                ensemble_config = kb.retrieval_config.get("ensemble_rerankers")

            if ensemble_config and len(ensemble_config) > 1:
                # Use ensemble reranking
                from .reranker import get_ensemble_reranker

                fusion_method = kwargs.get("rerank_fusion_method", "rrf")
                if kb.retrieval_config:
                    fusion_method = kb.retrieval_config.get(
                        "rerank_fusion_method", fusion_method
                    )

                ensemble_reranker = get_ensemble_reranker(
                    reranker_configs=ensemble_config,
                    fusion_method=fusion_method,
                    top_n=rerank_top_k or k,
                )
                if ensemble_reranker:
                    results_list = ensemble_reranker.postprocess_nodes(
                        results_list, query_bundle
                    )
            else:
                # Single reranker - rerank_model_id should be treated as a model name string
                reranker = get_reranker(
                    top_n=rerank_top_k or k,
                    model=rerank_model_id if rerank_model_id else None,
                )
                if reranker:
                    results_list = reranker.postprocess_nodes(
                        results_list, query_bundle
                    )

        # Apply score threshold
        if score_threshold:
            results_list = [
                n for n in results_list if (n.score or 0) >= score_threshold
            ]

        # Limit to k results
        results_list = results_list[:k]

        # Convert to RetrievalResult
        results = []
        for node_with_score in results_list:
            node = node_with_score.node
            metadata = node.metadata or {}

            results.append(
                RetrievalResult(
                    content=node.get_content(),
                    score=node_with_score.score or 0.0,
                    metadata=metadata,
                    node_id=node.node_id,
                    document_id=metadata.get("document_id"),
                    chunk_id=metadata.get("chunk_id"),
                    chunk_index=metadata.get("chunk_index"),
                    title=metadata.get("title"),
                )
            )

        logger.info(f"Retrieved {len(results)} results from KB {knowledge_base_id}")
        return results

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_document_by_hash(
        self, knowledge_base_id: uuid.UUID, file_hash: str
    ) -> Document | None:
        """Get document by file hash."""
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

    def _infer_file_type(
        self, filename: str | None, file_path: str | None
    ) -> str | None:
        """Infer file type from filename or path."""
        target = filename or file_path
        if not target:
            return None

        from pathlib import Path

        ext = Path(target).suffix.lower()

        mapping = {
            ".txt": "txt",
            ".md": "md",
            ".markdown": "md",
            ".pdf": "pdf",
            ".doc": "doc",
            ".docx": "docx",
            ".ppt": "ppt",
            ".pptx": "pptx",
            ".xls": "xls",
            ".xlsx": "xlsx",
            ".csv": "csv",
            ".json": "json",
            ".xml": "xml",
            ".html": "html",
            ".htm": "html",
        }

        return mapping.get(ext)

    async def get_collection_stats(self, kb_id: uuid.UUID) -> dict[str, Any]:
        """Get vector collection statistics for a KB."""
        kb = await self.get_knowledge_base(kb_id)
        if not kb:
            return {"error": "Knowledge base not found"}

        return await self.index_manager.get_collection_stats(
            kb_id=kb_id,
            store_type=kb.vector_store_type,
        )

    async def reindex_knowledge_base(
        self,
        kb_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Reindex all documents in a knowledge base."""
        logger.info(f"Starting reindex for KB {kb_id}")

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
            raise ValueError("Knowledge base embedding model not configured")

        # Delete existing collection
        await self.index_manager.delete_collection(kb_id, kb.vector_store_type)

        # Get embedding model
        (
            embed_model,
            embed_info,
        ) = await self.embedding_service.get_embed_model_with_info(
            str(kb.embedding_model_id)
        )
        embed_dim = embed_info.get("embed_dim", 384)

        doc_processor = await self._get_doc_processor(str(kb.embedding_model_id))

        total_docs = 0
        total_chunks = 0

        for document in kb.documents:
            if document.status != "ACTIVE":
                continue

            total_docs += 1

            # Clear old chunks
            for chunk in list(document.chunks):
                await self.session.delete(chunk)

            # Reprocess document
            nodes = doc_processor.process_text(
                content=document.content,
                metadata={
                    "document_id": str(document.id),
                    "knowledge_base_id": str(kb_id),
                    "title": document.title,
                    **embed_info,
                },
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
                self.session.add(chunk_record)

            await self.session.flush()

            # Update node IDs
            for chunk_record, node in zip(chunk_records, nodes, strict=False):
                node.node_id = str(chunk_record.id)
                node.metadata["chunk_id"] = str(chunk_record.id)

            # Index
            await self.index_manager.add_nodes(
                kb_id=kb_id,
                nodes=nodes,
                embed_model=embed_model,
                store_type=kb.vector_store_type,
                embed_dim=embed_dim,
            )

            total_chunks += len(nodes)

        kb.reindex_required = False
        await self.session.commit()

        logger.info(f"Reindex complete: {total_docs} docs, {total_chunks} chunks")

        return {
            "knowledge_base_id": str(kb_id),
            "documents_reindexed": total_docs,
            "chunks_indexed": total_chunks,
        }
