"""Async Redis cache decorator module.

Provides an async-compatible caching decorator similar to pottery's redis_cache,
supporting TTL, custom key functions, and JSON serialization.
"""

import functools
import json
import logging
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar, overload

from redis.asyncio import Redis as AIORedis

_DEFAULT_TIMEOUT: int = 60  # One minute in seconds

P = ParamSpec("P")
R = TypeVar("R")

# JSON-serializable types
JSONTypes = str | int | float | bool | None | list[Any] | dict[str, Any]

logger = logging.getLogger(__name__)


@dataclass
class CacheInfo:
    """Cache statistics, similar to functools.lru_cache().cache_info()."""

    hits: int = 0
    misses: int = 0
    currsize: int = 0


def _encode(value: JSONTypes) -> str:
    """Encode a value to JSON string, matching pottery's encoding.

    Args:
        value: A JSON-serializable value.

    Returns:
        A JSON string with sorted keys for consistent hashing.

    """
    return json.dumps(value, sort_keys=True)


def _decode(encoded_value: str) -> JSONTypes:
    """Decode a JSON string back to a Python value.

    Args:
        encoded_value: A JSON string.

    Returns:
        The decoded Python value.

    """
    return json.loads(encoded_value)


def _default_key_func(
    func: Callable[P, Any], *args: Hashable, **kwargs: Hashable
) -> str:
    """Generate a cache key from function signature and arguments.

    This matches pottery's key generation approach using hash of args/kwargs.

    Args:
        func: The decorated function.
        *args: Positional arguments passed to the function.
        **kwargs: Keyword arguments passed to the function.

    Returns:
        A string cache key combining the function name and argument hash.

    """
    kwargs_items = frozenset(kwargs.items())
    arg_hash = hash((args, kwargs_items))
    func_name = getattr(func, "__qualname__", func.__name__)  # type: ignore[attr-defined]
    func_module = getattr(func, "__module__", "__main__")
    return f"{func_module}:{func_name}:{arg_hash}"


@overload
def async_redis_cache(
    *,
    redis: AIORedis | None = None,
    redis_url: str | None = None,
    key: str | None = None,
    timeout: int | None = _DEFAULT_TIMEOUT,
    key_func: Callable[..., str] | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]: ...


@overload
def async_redis_cache(
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]: ...


def async_redis_cache(  # noqa: C901
    func: Callable[P, Awaitable[R]] | None = None,
    *,
    redis: AIORedis | None = None,
    redis_url: str | None = None,
    key: str | None = None,
    timeout: int | None = _DEFAULT_TIMEOUT,
    key_func: Callable[..., str] | None = None,
) -> (
    Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]
    | Callable[P, Awaitable[R]]
):
    """Async Redis-backed caching decorator with an API similar to pottery's redis_cache.

    This decorator caches the results of async functions in Redis with support for
    TTL (time-to-live), custom key generation, and JSON serialization.

    Args:
        func: The async function to decorate (when used without parentheses).
        redis: An existing async Redis client instance.
        redis_url: A Redis URL string to create a new connection.
            Either `redis` or `redis_url` must be provided.
        key: Optional key prefix for the cache. Defaults to function's qualified name.
        timeout: Time-to-live in seconds for cached values.
            Defaults to one week (604800 seconds). Set to None for no expiration.
        key_func: Optional custom function to generate cache keys.
            Should accept (func, *args, **kwargs) and return a string.
            Defaults to pottery-style key generation using argument hashing.

    Returns:
        A decorated async function with caching enabled.

    Raises:
        ValueError: If neither `redis` nor `redis_url` is provided when the
            decorated function is called.

    Example:
        Basic usage with Redis URL::

            @async_redis_cache(redis_url="redis://localhost:6379", timeout=3600)
            async def fetch_secret(secret_name: str) -> str:
                # Expensive operation to fetch secret
                return await get_secret_from_api(secret_name)

        With existing Redis client::

            redis_client = Redis.from_url("redis://localhost:6379")

            @async_redis_cache(redis=redis_client, timeout=300)
            async def get_user_data(user_id: int) -> dict:
                return await fetch_from_database(user_id)

        With custom key function::

            def my_key_func(func, user_id: int, **kwargs) -> str:
                return f"user:{user_id}"

            @async_redis_cache(redis_url="redis://localhost", key_func=my_key_func)
            async def get_user(user_id: int) -> dict:
                return await fetch_user(user_id)

    """

    def decorator(  # noqa: C901
        fn: Callable[P, Awaitable[R]],
    ) -> Callable[P, Awaitable[R]]:
        # Cache statistics
        cache_info = CacheInfo()

        # Track all cache keys for this function
        _cache_keys: set[str] = set()

        # Lazy Redis client initialization
        _redis_client: AIORedis | None = redis

        async def _get_redis() -> AIORedis:
            nonlocal _redis_client
            if _redis_client is None:
                if redis_url is None:
                    raise ValueError(
                        "Either 'redis' or 'redis_url' must be provided to "
                        "async_redis_cache"
                    )
                _redis_client = AIORedis.from_url(redis_url)
            return _redis_client

        def _make_key(*args: Any, **kwargs: Any) -> str:
            """Generate the full cache key."""
            if key_func is not None:
                base_key = key_func(fn, *args, **kwargs)
            else:
                base_key = _default_key_func(fn, *args, **kwargs)

            if key is not None:
                return f"{key}:{base_key}"
            return base_key

        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            client = await _get_redis()
            cache_key = _make_key(*args, **kwargs)

            # Try to get cached value
            try:
                cached_value = await client.get(cache_key)
                if cached_value is not None:
                    cache_info.hits += 1
                    return _decode(cached_value)  # type: ignore[return-value]
            except Exception:
                # On Redis errors, fall through to call the function
                # This matches pottery's behavior of graceful degradation
                logger.debug(
                    "Redis cache get failed for key %s, calling function", cache_key
                )

            # Cache miss - call the function
            cache_info.misses += 1
            result = await fn(*args, **kwargs)

            # Store result in cache
            try:
                encoded_value = _encode(result)  # type: ignore[arg-type]
                if timeout is not None:
                    await client.set(cache_key, encoded_value, ex=timeout)
                else:
                    await client.set(cache_key, encoded_value)
                # Track this key for potential clearing
                _cache_keys.add(cache_key)
            except Exception:
                # On Redis errors, silently fail - the function result is still returned
                # This matches pottery's behavior
                logger.debug("Redis cache set failed for key %s", cache_key)

            return result

        def get_cache_info() -> CacheInfo:
            """Return cache statistics with current size from tracked keys."""
            cache_info.currsize = len(_cache_keys)
            return cache_info

        # Attach cache_info as an attribute (similar to functools.lru_cache)
        wrapper.cache_info = get_cache_info  # type: ignore[attr-defined]

        async def cache_clear() -> None:
            """Clear all cached values for this function from Redis.

            Deletes all tracked cache keys from Redis and resets local statistics.
            Only keys that were set during this process's lifetime will be cleared.
            """
            if _cache_keys:
                try:
                    client = await _get_redis()
                    await client.delete(*_cache_keys)
                    logger.debug("Cleared %d cache keys", len(_cache_keys))
                except Exception:
                    logger.debug("Failed to clear cache keys from Redis")
            _cache_keys.clear()
            cache_info.hits = 0
            cache_info.misses = 0

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]

        return wrapper

    # Support both @async_redis_cache and @async_redis_cache(...) syntax
    if func is not None:
        # Called without parentheses: @async_redis_cache
        # This will fail at runtime since redis/redis_url is required,
        # but we support the syntax for consistency
        return decorator(func)

    return decorator
