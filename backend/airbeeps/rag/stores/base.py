"""
Base protocol and utilities for vector store adapters.
"""

from typing import Any, Protocol

from llama_index.core.schema import BaseNode


class VectorStoreHealth(Protocol):
    """Protocol for vector store health checks."""

    async def check_health(self) -> dict[str, Any]:
        """
        Check the health of the vector store connection.

        Returns:
            Dict with health status, e.g.:
            {
                "healthy": True,
                "store_type": "qdrant",
                "collection_count": 5,
                "latency_ms": 12.5
            }
        """
        ...


class VectorStoreAdmin(Protocol):
    """Protocol for vector store administrative operations."""

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete an entire collection."""
        ...

    async def list_collections(self) -> list[str]:
        """List all collections."""
        ...

    async def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get statistics for a collection."""
        ...


def prepare_nodes_for_indexing(nodes: list[BaseNode]) -> list[BaseNode]:
    """
    Prepare nodes for indexing by ensuring required fields are set.

    Args:
        nodes: List of nodes to prepare

    Returns:
        Prepared nodes
    """
    for node in nodes:
        # Ensure node has an ID
        if not node.node_id:
            import uuid

            node.node_id = str(uuid.uuid4())

        # Ensure metadata is a dict
        if node.metadata is None:
            node.metadata = {}

    return nodes


def collection_name_for_kb(kb_id: str) -> str:
    """
    Generate a collection name for a knowledge base.

    Args:
        kb_id: Knowledge base UUID

    Returns:
        Collection name string
    """
    # Sanitize for compatibility with all vector stores
    clean_id = str(kb_id).replace("-", "_")
    return f"kb_{clean_id}"
