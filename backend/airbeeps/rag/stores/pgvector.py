"""
PGVector vector store adapter for LlamaIndex.

Uses PostgreSQL with the pgvector extension for vector similarity search.
Ideal when you want to keep vectors in your existing PostgreSQL database.
"""

import logging
from typing import Any

from llama_index.core.vector_stores.types import BasePydanticVectorStore

from airbeeps.config import settings

logger = logging.getLogger(__name__)


def create_pgvector_store(
    collection_name: str,
    embed_dim: int = 384,
    **kwargs: Any,
) -> BasePydanticVectorStore:
    """
    Create a PGVector store instance.

    Args:
        collection_name: Name of the table/collection
        embed_dim: Embedding dimension
        **kwargs: Additional configuration overrides

    Returns:
        Configured PGVectorStore
    """
    from llama_index.vector_stores.postgres import PGVectorStore

    # Get connection string - use dedicated setting or fall back to main DB
    connection_string = kwargs.get(
        "connection_string",
        settings.PGVECTOR_CONNECTION_STRING
        or _convert_async_url(settings.DATABASE_URL),
    )
    schema = kwargs.get("schema", settings.PGVECTOR_SCHEMA)

    logger.info(f"Creating PGVector store for table: {collection_name}")

    return PGVectorStore.from_params(
        database=_extract_database_name(connection_string),
        host=_extract_host(connection_string),
        port=_extract_port(connection_string),
        user=_extract_user(connection_string),
        password=_extract_password(connection_string),
        table_name=collection_name,
        schema_name=schema,
        embed_dim=embed_dim,
        hybrid_search=kwargs.get("hybrid_search", settings.RAG_ENABLE_HYBRID_SEARCH),
        hnsw_kwargs={
            "hnsw_m": kwargs.get("hnsw_m", 16),
            "hnsw_ef_construction": kwargs.get("hnsw_ef_construction", 64),
            "hnsw_ef_search": kwargs.get("hnsw_ef_search", 40),
        },
    )


def _convert_async_url(url: str) -> str:
    """Convert async SQLAlchemy URL to sync format for pgvector."""
    # Convert sqlite+aiosqlite to just use postgres format
    if "sqlite" in url:
        logger.warning("PGVector requires PostgreSQL, not SQLite")
        raise ValueError("PGVector requires a PostgreSQL database, not SQLite")

    # Convert asyncpg to psycopg2 format
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _extract_database_name(url: str) -> str:
    """Extract database name from connection URL."""
    # Format: postgresql://user:pass@host:port/dbname
    if "/" in url.split("@")[-1]:
        return url.split("/")[-1].split("?")[0]
    return "postgres"


def _extract_host(url: str) -> str:
    """Extract host from connection URL."""
    try:
        after_at = url.split("@")[1]
        host_port = after_at.split("/")[0]
        return host_port.split(":")[0]
    except (IndexError, ValueError):
        return "localhost"


def _extract_port(url: str) -> str:
    """Extract port from connection URL."""
    try:
        after_at = url.split("@")[1]
        host_port = after_at.split("/")[0]
        if ":" in host_port:
            return host_port.split(":")[1]
        return "5432"
    except (IndexError, ValueError):
        return "5432"


def _extract_user(url: str) -> str:
    """Extract user from connection URL."""
    try:
        after_protocol = url.split("://")[1]
        user_pass = after_protocol.split("@")[0]
        return user_pass.split(":")[0]
    except (IndexError, ValueError):
        return "postgres"


def _extract_password(url: str) -> str:
    """Extract password from connection URL."""
    try:
        after_protocol = url.split("://")[1]
        user_pass = after_protocol.split("@")[0]
        if ":" in user_pass:
            return user_pass.split(":")[1]
        return ""
    except (IndexError, ValueError):
        return ""


async def delete_pgvector_collection(collection_name: str) -> bool:
    """Delete a PGVector table/collection."""
    try:
        # Use asyncpg to drop the table
        import asyncpg

        connection_string = settings.PGVECTOR_CONNECTION_STRING or _convert_async_url(
            settings.DATABASE_URL
        )

        conn = await asyncpg.connect(connection_string)
        try:
            schema = settings.PGVECTOR_SCHEMA
            await conn.execute(f'DROP TABLE IF EXISTS "{schema}"."{collection_name}"')
            logger.info(f"Deleted PGVector table: {collection_name}")
            return True
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to delete PGVector table {collection_name}: {e}")
        return False


async def get_pgvector_collection_stats(collection_name: str) -> dict[str, Any]:
    """Get statistics for a PGVector table."""
    try:
        import asyncpg

        connection_string = settings.PGVECTOR_CONNECTION_STRING or _convert_async_url(
            settings.DATABASE_URL
        )

        conn = await asyncpg.connect(connection_string)
        try:
            schema = settings.PGVECTOR_SCHEMA
            count = await conn.fetchval(
                f'SELECT COUNT(*) FROM "{schema}"."{collection_name}"'
            )
            return {
                "name": collection_name,
                "count": count,
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to get PGVector table stats: {e}")
        return {"name": collection_name, "error": str(e)}
