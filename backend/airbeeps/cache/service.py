"""
Cache service providing high-level caching operations.
"""

import hashlib
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from ..config import settings
from .backends import CacheBackend, InMemoryCache, RedisCache

logger = logging.getLogger(__name__)

# Global cache instance
_cache_instance: CacheBackend | None = None

T = TypeVar("T")


def cache_key(*args: Any, prefix: str = "") -> str:
    """
    Generate a cache key from arguments.

    Args:
        *args: Values to include in the key
        prefix: Optional prefix for the key

    Returns:
        A consistent cache key string

    Example:
        key = cache_key("user", user_id, "conversations", prefix="chat")
        # Returns: "chat:user:123:conversations"
    """
    parts = [str(arg) for arg in args if arg is not None]
    key = ":".join(parts)
    if prefix:
        key = f"{prefix}:{key}"
    return key


def cache_key_hash(*args: Any, prefix: str = "") -> str:
    """
    Generate a hashed cache key for long or complex values.

    Args:
        *args: Values to hash
        prefix: Optional prefix for the key

    Returns:
        A cache key with hashed content
    """
    content = ":".join(str(arg) for arg in args)
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    if prefix:
        return f"{prefix}:{content_hash}"
    return content_hash


async def get_cache() -> CacheBackend:
    """
    Get the cache backend instance.

    Creates the appropriate backend based on configuration:
    - If REDIS_ENABLED=true, uses Redis
    - Otherwise, uses in-memory cache

    Returns:
        The configured cache backend
    """
    global _cache_instance

    if _cache_instance is not None:
        return _cache_instance

    if settings.REDIS_ENABLED:
        logger.info("Initializing Redis cache backend")
        _cache_instance = RedisCache(
            url=settings.REDIS_URL,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            ssl=settings.REDIS_SSL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        )
        # Verify connection
        if not await _cache_instance.health_check():
            logger.warning("Redis connection failed, falling back to in-memory cache")
            _cache_instance = InMemoryCache()
    else:
        logger.info("Initializing in-memory cache backend (Redis disabled)")
        _cache_instance = InMemoryCache()

    return _cache_instance


async def close_cache() -> None:
    """Close the cache connection."""
    global _cache_instance
    if _cache_instance is not None:
        await _cache_instance.close()
        _cache_instance = None


class CacheService:
    """
    High-level cache service with typed operations and TTL presets.

    Usage:
        cache = CacheService()

        # Store conversation
        await cache.set_conversation(conv_id, conv_data)

        # Get with automatic TTL
        conv = await cache.get_conversation(conv_id)

        # Invalidate
        await cache.invalidate_conversation(conv_id)
    """

    def __init__(self, backend: CacheBackend | None = None):
        self._backend = backend

    async def _get_backend(self) -> CacheBackend:
        if self._backend is None:
            self._backend = await get_cache()
        return self._backend

    # =========================================================================
    # Conversation Cache
    # =========================================================================

    async def get_conversation(self, conversation_id: str) -> dict | None:
        """Get cached conversation."""
        backend = await self._get_backend()
        return await backend.get(cache_key("conv", conversation_id))

    async def set_conversation(self, conversation_id: str, data: dict) -> bool:
        """Cache conversation with configured TTL."""
        backend = await self._get_backend()
        return await backend.set(
            cache_key("conv", conversation_id),
            data,
            ttl=settings.CACHE_TTL_CONVERSATIONS,
        )

    async def invalidate_conversation(self, conversation_id: str) -> bool:
        """Invalidate conversation cache."""
        backend = await self._get_backend()
        return await backend.delete(cache_key("conv", conversation_id))

    async def invalidate_user_conversations(self, user_id: str) -> int:
        """Invalidate all conversations for a user."""
        backend = await self._get_backend()
        return await backend.clear(f"conv:user:{user_id}:*")

    # =========================================================================
    # RAG / Retrieval Cache
    # =========================================================================

    async def get_rag_result(
        self, kb_id: str, query_hash: str, k: int
    ) -> list[dict] | None:
        """Get cached RAG retrieval result."""
        backend = await self._get_backend()
        return await backend.get(cache_key("rag", kb_id, query_hash, k))

    async def set_rag_result(
        self, kb_id: str, query_hash: str, k: int, results: list[dict]
    ) -> bool:
        """Cache RAG retrieval result."""
        backend = await self._get_backend()
        return await backend.set(
            cache_key("rag", kb_id, query_hash, k),
            results,
            ttl=settings.CACHE_TTL_RAG_RESULTS,
        )

    async def invalidate_kb_cache(self, kb_id: str) -> int:
        """Invalidate all cache entries for a knowledge base."""
        backend = await self._get_backend()
        return await backend.clear(f"rag:{kb_id}:*")

    # =========================================================================
    # Embedding Cache
    # =========================================================================

    async def get_embedding(self, model_id: str, text_hash: str) -> list[float] | None:
        """Get cached embedding vector."""
        backend = await self._get_backend()
        return await backend.get(cache_key("embed", model_id, text_hash))

    async def set_embedding(
        self, model_id: str, text_hash: str, embedding: list[float]
    ) -> bool:
        """Cache embedding vector."""
        backend = await self._get_backend()
        return await backend.set(
            cache_key("embed", model_id, text_hash),
            embedding,
            ttl=settings.CACHE_TTL_EMBEDDINGS,
        )

    # =========================================================================
    # Model Discovery Cache
    # =========================================================================

    async def get_model_list(self, provider: str) -> list[dict] | None:
        """Get cached model list for provider."""
        backend = await self._get_backend()
        return await backend.get(cache_key("models", provider))

    async def set_model_list(self, provider: str, models: list[dict]) -> bool:
        """Cache model list for provider."""
        backend = await self._get_backend()
        return await backend.set(
            cache_key("models", provider),
            models,
            ttl=settings.CACHE_TTL_MODEL_DISCOVERY,
        )

    async def invalidate_model_cache(self, provider: str | None = None) -> int:
        """Invalidate model discovery cache."""
        backend = await self._get_backend()
        if provider:
            return await backend.clear(f"models:{provider}")
        return await backend.clear("models:*")

    # =========================================================================
    # Generic Operations
    # =========================================================================

    async def get(self, key: str) -> Any | None:
        """Generic get."""
        backend = await self._get_backend()
        return await backend.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Generic set with optional TTL."""
        backend = await self._get_backend()
        return await backend.set(key, value, ttl or settings.CACHE_TTL_DEFAULT)

    async def delete(self, key: str) -> bool:
        """Generic delete."""
        backend = await self._get_backend()
        return await backend.delete(key)

    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache entries matching pattern."""
        backend = await self._get_backend()
        return await backend.clear(pattern)

    async def health_check(self) -> bool:
        """Check cache backend health."""
        backend = await self._get_backend()
        return await backend.health_check()


def cached(
    ttl: int | None = None,
    prefix: str = "",
    key_builder: Callable[..., str] | None = None,
):
    """
    Decorator for caching async function results.

    Args:
        ttl: Cache TTL in seconds (uses default if None)
        prefix: Key prefix
        key_builder: Custom function to build cache key from args

    Example:
        @cached(ttl=300, prefix="user")
        async def get_user(user_id: str) -> dict:
            return await db.fetch_user(user_id)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            cache = await get_cache()

            # Build cache key
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                # Default: use function name and args
                key_parts = [func.__name__] + [str(a) for a in args]
                key_parts += [f"{k}={v}" for k, v in sorted(kwargs.items())]
                key = cache_key(*key_parts, prefix=prefix)

            # Try to get from cache
            cached_value = await cache.get(key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                await cache.set(key, result, ttl or settings.CACHE_TTL_DEFAULT)

            return result

        return wrapper

    return decorator
