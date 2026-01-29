"""Unit tests for the async_redis_cache module."""

from unittest.mock import AsyncMock, patch

import pytest

from lambda_framework.cache import (
    CacheInfo,
    _decode,
    _default_key_func,
    _encode,
    async_redis_cache,
)


class TestEncodeDecode:
    """Tests for JSON encoding and decoding functions."""

    def test_encode_string(self):
        """Should encode a string to JSON."""
        assert _encode("hello") == '"hello"'

    def test_encode_int(self):
        """Should encode an integer to JSON."""
        assert _encode(42) == "42"

    def test_encode_float(self):
        """Should encode a float to JSON."""
        assert _encode(3.14) == "3.14"

    def test_encode_bool(self):
        """Should encode a boolean to JSON."""
        assert _encode(True) == "true"
        assert _encode(False) == "false"

    def test_encode_none(self):
        """Should encode None to JSON."""
        assert _encode(None) == "null"

    def test_encode_list(self):
        """Should encode a list to JSON."""
        assert _encode([1, 2, 3]) == "[1, 2, 3]"

    def test_encode_dict_with_sorted_keys(self):
        """Should encode a dict with sorted keys."""
        result = _encode({"b": 2, "a": 1})
        assert result == '{"a": 1, "b": 2}'

    def test_decode_string(self):
        """Should decode a JSON string."""
        assert _decode('"hello"') == "hello"

    def test_decode_int(self):
        """Should decode a JSON integer."""
        assert _decode("42") == 42

    def test_decode_dict(self):
        """Should decode a JSON object."""
        assert _decode('{"a": 1, "b": 2}') == {"a": 1, "b": 2}

    def test_encode_decode_roundtrip(self):
        """Should roundtrip encode and decode."""
        data = {"name": "test", "values": [1, 2, 3], "nested": {"a": True}}
        assert _decode(_encode(data)) == data


class TestDefaultKeyFunc:
    """Tests for the default key generation function."""

    def test_generates_key_with_module_and_qualname(self):
        """Should generate key with module and qualified name."""

        def sample_func(x: int) -> int:
            return x * 2

        key = _default_key_func(sample_func, 42)
        assert "test_cache_unit" in key
        assert "sample_func" in key

    def test_different_args_produce_different_keys(self):
        """Different arguments should produce different keys."""

        def func(x: int) -> int:
            return x

        key1 = _default_key_func(func, 1)
        key2 = _default_key_func(func, 2)
        assert key1 != key2

    def test_same_args_produce_same_keys(self):
        """Same arguments should produce the same key."""

        def func(x: int) -> int:
            return x

        key1 = _default_key_func(func, 42)
        key2 = _default_key_func(func, 42)
        assert key1 == key2

    def test_kwargs_affect_key(self):
        """Keyword arguments should affect the key."""

        def func(x: int, y: int = 0) -> int:
            return x + y

        key1 = _default_key_func(func, 1, y=2)
        key2 = _default_key_func(func, 1, y=3)
        assert key1 != key2


class TestCacheInfo:
    """Tests for the CacheInfo dataclass."""

    def test_default_values(self):
        """Should have zero default values."""
        info = CacheInfo()
        assert info.hits == 0
        assert info.misses == 0
        assert info.currsize == 0

    def test_can_set_values(self):
        """Should allow setting values."""
        info = CacheInfo(hits=10, misses=5, currsize=15)
        assert info.hits == 10
        assert info.misses == 5
        assert info.currsize == 15


class TestAsyncRedisCacheUnit:
    """Unit tests for async_redis_cache decorator using mocks."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock async Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        return mock

    async def test_caches_function_result(self, mock_redis: AsyncMock):
        """Should cache the result of the decorated function."""
        call_count = 0

        @async_redis_cache(redis=mock_redis, timeout=60)
        async def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - cache miss
        result1 = await expensive_func(5)
        assert result1 == 10
        assert call_count == 1
        mock_redis.set.assert_called_once()

        # Simulate cache hit by returning cached value
        mock_redis.get.return_value = _encode(10)

        # Second call - cache hit
        result2 = await expensive_func(5)
        assert result2 == 10
        assert call_count == 1  # Function not called again

    async def test_cache_miss_calls_function(self, mock_redis: AsyncMock):
        """On cache miss, should call the function and cache result."""

        @async_redis_cache(redis=mock_redis, timeout=60)
        async def func(x: int) -> dict:
            return {"value": x}

        result = await func(42)

        assert result == {"value": 42}
        mock_redis.get.assert_called_once()
        mock_redis.set.assert_called_once()

    async def test_cache_hit_returns_cached_value(self, mock_redis: AsyncMock):
        """On cache hit, should return cached value without calling function."""
        mock_redis.get.return_value = _encode({"cached": True})
        call_count = 0

        @async_redis_cache(redis=mock_redis, timeout=60)
        async def func() -> dict:
            nonlocal call_count
            call_count += 1
            return {"cached": False}

        result = await func()

        assert result == {"cached": True}
        assert call_count == 0
        mock_redis.set.assert_not_called()

    async def test_timeout_passed_to_redis_set(self, mock_redis: AsyncMock):
        """Should pass timeout to Redis SET command."""

        @async_redis_cache(redis=mock_redis, timeout=3600)
        async def func() -> str:
            return "value"

        await func()

        # Check that set was called with ex=3600
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == 3600

    async def test_no_timeout_when_none(self, mock_redis: AsyncMock):
        """Should not set expiration when timeout is None."""

        @async_redis_cache(redis=mock_redis, timeout=None)
        async def func() -> str:
            return "value"

        await func()

        # Check that set was called without ex parameter
        call_args = mock_redis.set.call_args
        assert "ex" not in call_args.kwargs or call_args.kwargs.get("ex") is None

    async def test_custom_key_func(self, mock_redis: AsyncMock):
        """Should use custom key function when provided."""

        def my_key_func(func, user_id: int) -> str:
            return f"custom:user:{user_id}"

        @async_redis_cache(redis=mock_redis, key_func=my_key_func)
        async def get_user(user_id: int) -> dict:
            return {"id": user_id}

        await get_user(123)

        # Check the key used
        call_args = mock_redis.get.call_args
        assert "custom:user:123" in call_args.args[0]

    async def test_key_prefix(self, mock_redis: AsyncMock):
        """Should prepend key prefix when provided."""

        @async_redis_cache(redis=mock_redis, key="myprefix")
        async def func() -> str:
            return "value"

        await func()

        call_args = mock_redis.get.call_args
        assert call_args.args[0].startswith("myprefix:")

    async def test_cache_info_tracks_hits(self, mock_redis: AsyncMock):
        """cache_info should track cache hits."""
        mock_redis.get.return_value = _encode("cached")

        @async_redis_cache(redis=mock_redis)
        async def func() -> str:
            return "fresh"

        await func()
        await func()

        info = func.cache_info()  # type: ignore[attr-defined]
        assert info.hits == 2
        assert info.misses == 0

    async def test_cache_info_tracks_misses(self, mock_redis: AsyncMock):
        """cache_info should track cache misses."""

        @async_redis_cache(redis=mock_redis)
        async def func(x: int) -> int:
            return x

        await func(1)
        await func(2)

        info = func.cache_info()  # type: ignore[attr-defined]
        assert info.misses == 2

    async def test_cache_info_tracks_currsize(self, mock_redis: AsyncMock):
        """cache_info.currsize should track number of cached keys."""

        @async_redis_cache(redis=mock_redis)
        async def func(x: int) -> int:
            return x

        await func(1)
        await func(2)
        await func(3)

        info = func.cache_info()  # type: ignore[attr-defined]
        assert info.currsize == 3

    async def test_cache_clear_deletes_keys(self, mock_redis: AsyncMock):
        """cache_clear should delete all tracked keys from Redis."""

        @async_redis_cache(redis=mock_redis)
        async def func(x: int) -> int:
            return x

        await func(1)
        await func(2)

        await func.cache_clear()  # type: ignore[attr-defined]

        mock_redis.delete.assert_called_once()
        # Should have deleted 2 keys
        assert len(mock_redis.delete.call_args.args) == 2

    async def test_cache_clear_resets_stats(self, mock_redis: AsyncMock):
        """cache_clear should reset cache statistics."""

        @async_redis_cache(redis=mock_redis)
        async def func(x: int) -> int:
            return x

        await func(1)
        await func(2)

        await func.cache_clear()  # type: ignore[attr-defined]

        info = func.cache_info()  # type: ignore[attr-defined]
        assert info.hits == 0
        assert info.misses == 0
        assert info.currsize == 0

    async def test_redis_get_error_gracefully_handled(self, mock_redis: AsyncMock):
        """Redis GET errors should be handled gracefully."""
        from redis.exceptions import RedisError

        mock_redis.get.side_effect = RedisError("Connection error")

        @async_redis_cache(redis=mock_redis)
        async def func() -> str:
            return "fallback"

        result = await func()

        assert result == "fallback"

    async def test_redis_set_error_gracefully_handled(self, mock_redis: AsyncMock):
        """Redis SET errors should be handled gracefully."""
        from redis.exceptions import RedisError

        mock_redis.set.side_effect = RedisError("Connection error")

        @async_redis_cache(redis=mock_redis)
        async def func() -> str:
            return "value"

        result = await func()

        assert result == "value"

    async def test_raises_error_when_no_redis_provided(self):
        """Should raise ValueError when no redis or redis_url provided."""

        @async_redis_cache()
        async def func() -> str:
            return "value"

        with pytest.raises(ValueError, match="Either 'redis' or 'redis_url'"):
            await func()

    async def test_lazy_redis_creation_from_url(self):
        """Should create Redis client lazily from URL."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.set = AsyncMock(return_value=True)

        with patch(
            "lambda_framework.cache.AIORedis.from_url", return_value=mock_client
        ) as mock_from_url:

            @async_redis_cache(redis_url="redis://localhost:6379")
            async def func() -> str:
                return "value"

            await func()

            mock_from_url.assert_called_once_with("redis://localhost:6379")

    async def test_preserves_function_metadata(self, mock_redis: AsyncMock):
        """Decorator should preserve function metadata."""

        @async_redis_cache(redis=mock_redis)
        async def my_documented_func() -> str:
            """Return a test value."""
            return "value"

        assert my_documented_func.__name__ == "my_documented_func"
        assert my_documented_func.__doc__ == "Return a test value."
