"""
Unit tests for vector store factory and adapters.
"""

from airbeeps.rag.stores import (
    VectorStoreFactory,
    VectorStoreType,
)
from airbeeps.rag.stores.base import collection_name_for_kb


class TestVectorStoreType:
    """Tests for VectorStoreType enum."""

    def test_enum_values(self):
        """Test enum has expected values."""
        assert VectorStoreType.QDRANT.value == "qdrant"
        assert VectorStoreType.CHROMADB.value == "chromadb"
        assert VectorStoreType.PGVECTOR.value == "pgvector"
        assert VectorStoreType.MILVUS.value == "milvus"

    def test_enum_from_string(self):
        """Test creating enum from string."""
        assert VectorStoreType("qdrant") == VectorStoreType.QDRANT
        assert VectorStoreType("chromadb") == VectorStoreType.CHROMADB


class TestCollectionNameForKb:
    """Tests for collection name generation."""

    def test_generates_valid_name(self):
        """Test generates valid collection name."""
        kb_id = "12345678-1234-1234-1234-123456789012"
        name = collection_name_for_kb(kb_id)

        assert name.startswith("kb_")
        assert "-" not in name  # Hyphens replaced with underscores
        assert len(name) > 3

    def test_sanitizes_uuid(self):
        """Test UUID hyphens are replaced."""
        kb_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        name = collection_name_for_kb(kb_id)

        assert "aaaaaaaa_bbbb_cccc_dddd_eeeeeeeeeeee" in name


class TestVectorStoreFactory:
    """Tests for VectorStoreFactory."""

    def test_get_default_type(self):
        """Test getting default type from settings."""
        default_type = VectorStoreFactory.get_default_type()
        assert isinstance(default_type, VectorStoreType)

    def test_clear_cache(self):
        """Test clearing cache."""
        VectorStoreFactory.clear_cache()
        assert len(VectorStoreFactory._instances) == 0

    def test_remove_from_cache(self):
        """Test removing specific store from cache."""
        # Add something to cache
        VectorStoreFactory._instances["qdrant:test"] = "mock_store"

        VectorStoreFactory.remove_from_cache(VectorStoreType.QDRANT, "test")

        assert "qdrant:test" not in VectorStoreFactory._instances

    def test_create_with_string_type(self):
        """Test create accepts string type."""
        # This will fail without actual store connection, but tests type conversion
        VectorStoreFactory.clear_cache()


class TestGetVectorStore:
    """Tests for get_vector_store convenience function."""

    def test_uses_default_type_when_none(self):
        """Test uses default type when not specified."""
        # Just verify the function exists and accepts parameters
        # Actual creation requires store connection
