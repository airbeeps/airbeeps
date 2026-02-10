"""
Airbeeps Cache Module

Provides a unified caching interface with Redis and in-memory backends.
Redis is optional and can be enabled via AIRBEEPS_REDIS_ENABLED=true.

Usage:
    from airbeeps.cache import get_cache, CacheService

    cache = await get_cache()
    await cache.set("key", {"data": "value"}, ttl=3600)
    value = await cache.get("key")
"""

from .backends import CacheBackend, InMemoryCache, RedisCache
from .service import CacheService, cache_key, get_cache

__all__ = [
    "CacheBackend",
    "CacheService",
    "InMemoryCache",
    "RedisCache",
    "cache_key",
    "get_cache",
]
