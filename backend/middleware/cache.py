"""
Simple in-memory caching layer with TTL support.
Thread-safe caching for metadata and read operations.
"""

import time
import threading
import hashlib
import json
from typing import Any, Optional, Callable
from backend.logging_config import logger_chat

# Cache cleanup interval in seconds
CACHE_CLEANUP_INTERVAL = 300  # 5 minutes


class CacheEntry:
    """Single cache entry with TTL."""

    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl


class MemoryCache:
    """Thread-safe in-memory cache with TTL."""

    def __init__(self, max_size: int = 1000):
        self.cache: dict = {}
        self.max_size = max_size
        self._lock = threading.RLock()
        self._cleanup_thread: threading.Thread | None = None
        self._stop_cleanup = threading.Event()
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """Start background cleanup thread."""
        def cleanup_loop():
            while not self._stop_cleanup.wait(CACHE_CLEANUP_INTERVAL):
                with self._lock:
                    expired_keys = [
                        k for k, v in self.cache.items() if v.is_expired()
                    ]
                    for k in expired_keys:
                        del self.cache[k]
                    if expired_keys:
                        logger_chat.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries")

        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop_cleanup(self):
        """Stop the cleanup thread."""
        self._stop_cleanup.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=2)

    def _make_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_str = json.dumps(
            {
                "args": [str(a) for a in args],
                "kwargs": {k: str(v) for k, v in kwargs.items()},
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if exists and not expired."""
        with self._lock:
            if key not in self.cache:
                return None

            entry = self.cache[key]
            if entry.is_expired():
                del self.cache[key]
                return None

            return entry.value

    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        with self._lock:
            # Evict oldest entry if cache is full
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].created_at)
                del self.cache[oldest_key]

            self.cache[key] = CacheEntry(value, ttl)

    def invalidate(self, key: str):
        """Remove entry from cache."""
        with self._lock:
            self.cache.pop(key, None)

    def clear(self):
        """Clear entire cache."""
        with self._lock:
            self.cache.clear()

    def cleanup(self):
        """Remove expired entries."""
        with self._lock:
            expired_keys = [
                k for k, v in self.cache.items() if v.is_expired()
            ]
            for k in expired_keys:
                del self.cache[k]

    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "expired": sum(1 for v in self.cache.values() if v.is_expired()),
            }


# Global cache instance
_cache = MemoryCache(max_size=1000)


def cache_result(ttl: int = 3600):
    """
    Decorator to cache function results.

    Args:
        ttl: Time to live in seconds
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = _cache._make_key(func.__name__, *args, **kwargs)

            # Try to get from cache
            result = _cache.get(key)
            if result is not None:
                logger_chat.debug(f"Cache hit: {func.__name__}")
                return result

            # Execute function
            result = func(*args, **kwargs)

            # Store in cache
            _cache.set(key, result, ttl)
            logger_chat.debug(f"Cache set: {func.__name__} ({ttl}s TTL)")

            return result

        return wrapper

    return decorator


def get_cache() -> MemoryCache:
    """Get global cache instance."""
    return _cache


# Common cache keys for invalidation
class CacheKey:
    """Standard cache key patterns."""

    @staticmethod
    def sessions(user_id: str) -> str:
        return f"sessions:{user_id}"

    @staticmethod
    def session_history(session_id: str) -> str:
        return f"history:{session_id}"

    @staticmethod
    def uploaded_files(user_id: str) -> str:
        return f"files:{user_id}"

    @staticmethod
    def user_metadata(user_id: str) -> str:
        return f"user:{user_id}"


def invalidate_user_cache(user_id: str):
    """Invalidate all cache entries for a user."""
    _cache.invalidate(CacheKey.sessions(user_id))
    _cache.invalidate(CacheKey.uploaded_files(user_id))
    _cache.invalidate(CacheKey.user_metadata(user_id))
    logger_chat.info(f"User cache invalidated: {user_id}")
