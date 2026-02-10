"""
Cache backend implementations: In-memory and Redis.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get a value from cache. Returns None if not found or expired."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set a value in cache with optional TTL (seconds). Returns True on success."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key from cache. Returns True if key existed."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""

    @abstractmethod
    async def clear(self, pattern: str | None = None) -> int:
        """Clear cache. If pattern provided, only clear matching keys. Returns count of deleted keys."""

    @abstractmethod
    async def close(self) -> None:
        """Close the cache connection."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the cache backend is healthy."""

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values. Default implementation calls get() for each key."""
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result

    async def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values. Default implementation calls set() for each key."""
        for key, value in mapping.items():
            await self.set(key, value, ttl)
        return True

    async def delete_many(self, keys: list[str]) -> int:
        """Delete multiple keys. Returns count of deleted keys."""
        count = 0
        for key in keys:
            if await self.delete(key):
                count += 1
        return count


class InMemoryCache(CacheBackend):
    """
    In-memory cache backend using Python dict.

    Thread-safe for async operations. Includes automatic TTL expiration.
    Suitable for single-instance deployments or development.
    """

    def __init__(self, max_size: int = 10000):
        self._cache: dict[str, tuple[Any, float | None]] = {}
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def _start_cleanup(self) -> None:
        """Start background cleanup task for expired entries."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        async with self._lock:
            expired_keys = [
                k
                for k, (_, expires) in self._cache.items()
                if expires is not None and expires <= now
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    async def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache is full."""
        if len(self._cache) >= self._max_size:
            # Remove 10% of oldest entries (by expiration time or FIFO)
            to_remove = max(1, self._max_size // 10)
            # Sort by expiration time (None = no expiry = keep longer)
            items = sorted(
                self._cache.items(),
                key=lambda x: x[1][1] if x[1][1] is not None else float("inf"),
            )
            for key, _ in items[:to_remove]:
                del self._cache[key]
            logger.debug(f"Evicted {to_remove} cache entries due to size limit")

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires = entry
            if expires is not None and expires <= time.time():
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        async with self._lock:
            await self._evict_if_needed()
            expires = time.time() + ttl if ttl is not None else None
            self._cache[key] = (value, expires)
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        value = await self.get(key)
        return value is not None

    async def clear(self, pattern: str | None = None) -> int:
        async with self._lock:
            if pattern is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            # Simple pattern matching (prefix*)
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            else:
                keys_to_delete = [k for k in self._cache if k == pattern]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    async def close(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def health_check(self) -> bool:
        return True  # In-memory is always healthy

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "backend": "memory",
            "size": len(self._cache),
            "max_size": self._max_size,
        }


class RedisCache(CacheBackend):
    """
    Redis cache backend.

    Requires redis[hiredis] package. Supports connection pooling,
    automatic reconnection, and distributed caching.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        password: str | None = None,
        ssl: bool = False,
        max_connections: int = 50,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        key_prefix: str = "airbeeps:",
    ):
        self._url = url
        self._password = password
        self._ssl = ssl
        self._max_connections = max_connections
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._key_prefix = key_prefix
        self._redis: Any = None
        self._pool: Any = None

    async def _get_client(self):
        """Get or create Redis client with connection pool."""
        if self._redis is None:
            try:
                import redis.asyncio as redis
            except ImportError:
                raise ImportError(
                    "Redis package not installed. Install with: pip install 'redis[hiredis]'"
                )

            # Create connection pool
            self._pool = redis.ConnectionPool.from_url(
                self._url,
                password=self._password if self._password else None,
                max_connections=self._max_connections,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                decode_responses=True,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            logger.info(f"Redis cache connected: {self._url}")
        return self._redis

    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> Any | None:
        try:
            client = await self._get_client()
            value = await client.get(self._make_key(key))
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis get error for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        try:
            client = await self._get_client()
            serialized = json.dumps(value, default=str)
            if ttl is not None:
                await client.setex(self._make_key(key), ttl, serialized)
            else:
                await client.set(self._make_key(key), serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis set error for key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        try:
            client = await self._get_client()
            result = await client.delete(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.warning(f"Redis delete error for key '{key}': {e}")
            return False

    async def exists(self, key: str) -> bool:
        try:
            client = await self._get_client()
            return await client.exists(self._make_key(key)) > 0
        except Exception as e:
            logger.warning(f"Redis exists error for key '{key}': {e}")
            return False

    async def clear(self, pattern: str | None = None) -> int:
        try:
            client = await self._get_client()
            if pattern is None:
                pattern = "*"
            full_pattern = self._make_key(pattern)

            # Use SCAN for safe pattern deletion
            count = 0
            async for key in client.scan_iter(match=full_pattern, count=100):
                await client.delete(key)
                count += 1
            return count
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")
            return 0

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
        logger.info("Redis cache connection closed")

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return False

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Optimized multi-get using Redis MGET."""
        if not keys:
            return {}
        try:
            client = await self._get_client()
            full_keys = [self._make_key(k) for k in keys]
            values = await client.mget(full_keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        pass
            return result
        except Exception as e:
            logger.warning(f"Redis mget error: {e}")
            return await super().get_many(keys)

    async def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Optimized multi-set using Redis pipeline."""
        if not mapping:
            return True
        try:
            client = await self._get_client()
            async with client.pipeline() as pipe:
                for key, value in mapping.items():
                    serialized = json.dumps(value, default=str)
                    full_key = self._make_key(key)
                    if ttl is not None:
                        pipe.setex(full_key, ttl, serialized)
                    else:
                        pipe.set(full_key, serialized)
                await pipe.execute()
            return True
        except Exception as e:
            logger.warning(f"Redis mset error: {e}")
            return await super().set_many(mapping, ttl)

    async def stats(self) -> dict[str, Any]:
        """Get Redis server statistics."""
        try:
            client = await self._get_client()
            info = await client.info()
            return {
                "backend": "redis",
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
            }
        except Exception as e:
            return {"backend": "redis", "error": str(e)}
