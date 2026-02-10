"""
Tests for KB Pipeline Builder functionality (Phase 4).

Tests the visual pipeline builder backend support:
1. POST /knowledge-bases/{kb_id}/preview endpoint
2. RAGConfigPreview and PipelinePreviewRequest/Response schemas
3. Integration with RAG retrieval
"""

import pytest


class TestPipelinePreviewEndpoint:
    """Tests for the pipeline preview endpoint."""

    @pytest.mark.asyncio
    async def test_preview_requires_auth(self, client):
        """Test that preview endpoint requires authentication."""
        fake_kb_id = "00000000-0000-0000-0000-000000000000"

        # Try to access without auth
        preview_resp = await client.post(
            f"/api/v1/admin/rag/knowledge-bases/{fake_kb_id}/preview",
            json={"query": "Test query"},
            # No headers = no auth
        )

        assert preview_resp.status_code in (401, 403)


class TestPipelinePreviewSchemas:
    """Tests for pipeline preview schemas."""

    def test_rag_config_preview_defaults(self):
        """Test RAGConfigPreview default values."""
        from airbeeps.rag.api.v1.schemas import RAGConfigPreview

        config = RAGConfigPreview()

        assert config.retrieval_count == 5
        assert config.similarity_threshold == 0.7
        assert config.hybrid_enabled is False
        assert config.multi_query is False
        assert config.multi_query_count == 3

    def test_rag_config_preview_custom(self):
        """Test RAGConfigPreview with custom values."""
        from airbeeps.rag.api.v1.schemas import RAGConfigPreview

        config = RAGConfigPreview(
            retrieval_count=15,
            similarity_threshold=0.9,
            hybrid_enabled=True,
            multi_query=True,
            multi_query_count=5,
            rerank_model_id="model-123",
            rerank_top_k=20,
        )

        assert config.retrieval_count == 15
        assert config.similarity_threshold == 0.9
        assert config.hybrid_enabled is True
        assert config.multi_query is True
        assert config.multi_query_count == 5
        assert config.rerank_model_id == "model-123"
        assert config.rerank_top_k == 20

    def test_rag_config_preview_validation(self):
        """Test RAGConfigPreview validation."""
        from pydantic import ValidationError

        from airbeeps.rag.api.v1.schemas import RAGConfigPreview

        # retrieval_count out of range
        with pytest.raises(ValidationError):
            RAGConfigPreview(retrieval_count=0)

        with pytest.raises(ValidationError):
            RAGConfigPreview(retrieval_count=100)  # Max is 20

        # similarity_threshold out of range
        with pytest.raises(ValidationError):
            RAGConfigPreview(similarity_threshold=1.5)

        with pytest.raises(ValidationError):
            RAGConfigPreview(similarity_threshold=-0.1)

    def test_pipeline_preview_request(self):
        """Test PipelinePreviewRequest schema."""
        from airbeeps.rag.api.v1.schemas import PipelinePreviewRequest, RAGConfigPreview

        # Without config
        req = PipelinePreviewRequest(query="Test query")
        assert req.query == "Test query"
        assert req.rag_config is None

        # With config
        config = RAGConfigPreview(retrieval_count=10)
        req = PipelinePreviewRequest(query="Another query", rag_config=config)
        assert req.query == "Another query"
        assert req.rag_config.retrieval_count == 10

    def test_pipeline_preview_request_validation(self):
        """Test PipelinePreviewRequest validation."""
        from pydantic import ValidationError

        from airbeeps.rag.api.v1.schemas import PipelinePreviewRequest

        # Empty query
        with pytest.raises(ValidationError):
            PipelinePreviewRequest(query="")

        # Query too long
        with pytest.raises(ValidationError):
            PipelinePreviewRequest(query="x" * 2001)

    def test_pipeline_preview_response(self):
        """Test PipelinePreviewResponse schema."""
        from airbeeps.rag.api.v1.schemas import (
            PipelinePreviewResponse,
            RAGRetrievedDocument,
        )

        response = PipelinePreviewResponse(
            query="Test query",
            documents=[
                RAGRetrievedDocument(
                    content="Document content",
                    metadata={"source": "test.pdf", "page": 1},
                    score=0.95,
                    similarity=0.92,
                ),
            ],
            config_used={
                "retrieval_count": 5,
                "similarity_threshold": 0.7,
            },
        )

        assert response.query == "Test query"
        assert len(response.documents) == 1
        assert response.documents[0].content == "Document content"
        assert response.documents[0].score == 0.95
        assert response.config_used["retrieval_count"] == 5

    def test_rag_retrieved_document(self):
        """Test RAGRetrievedDocument schema."""
        from airbeeps.rag.api.v1.schemas import RAGRetrievedDocument

        doc = RAGRetrievedDocument(
            content="This is the document content",
            metadata={
                "source": "example.pdf",
                "page": 5,
                "chunk_index": 12,
            },
            score=0.88,
            similarity=0.85,
        )

        assert doc.content == "This is the document content"
        assert doc.metadata["source"] == "example.pdf"
        assert doc.metadata["page"] == 5
        assert doc.score == 0.88
        assert doc.similarity == 0.85

        # Optional fields
        doc_minimal = RAGRetrievedDocument(
            content="Minimal doc",
            metadata={},
        )
        assert doc_minimal.score is None
        assert doc_minimal.similarity is None


class TestKBBuilderComponents:
    """Tests for KB Builder component structure validation."""

    def test_kb_builder_components_exist(self):
        """Verify all required KB builder component files exist."""
        from pathlib import Path

        components_dir = (
            Path(__file__).parent.parent.parent.parent
            / "frontend"
            / "app"
            / "components"
            / "admin"
            / "kb-builder"
        )

        expected_files = [
            "index.ts",
            "KBPipelineBuilder.vue",
            "PipelinePreview.vue",
            "nodes/BaseNode.vue",
            "nodes/DocumentSourceNode.vue",
            "nodes/ChunkingNode.vue",
            "nodes/EmbeddingNode.vue",
            "nodes/RetrievalNode.vue",
            "nodes/RerankerNode.vue",
            "nodes/OutputNode.vue",
        ]

        for file in expected_files:
            file_path = components_dir / file
            assert file_path.exists(), f"Expected component file {file} not found"

    def test_kb_builder_node_types_complete(self):
        """Verify all pipeline node types are defined."""
        from pathlib import Path

        nodes_dir = (
            Path(__file__).parent.parent.parent.parent
            / "frontend"
            / "app"
            / "components"
            / "admin"
            / "kb-builder"
            / "nodes"
        )

        # All required node types for the pipeline
        required_nodes = [
            "DocumentSourceNode.vue",
            "ChunkingNode.vue",
            "EmbeddingNode.vue",
            "RetrievalNode.vue",
            "RerankerNode.vue",
            "OutputNode.vue",
        ]

        existing_nodes = list(nodes_dir.glob("*.vue"))
        existing_names = {f.name for f in existing_nodes}

        for node in required_nodes:
            assert node in existing_names, f"Required node {node} not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
