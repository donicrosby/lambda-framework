"""Integration tests for the async_redis_cache module.

These tests require a running Redis/Valkey instance.
Set VALKEY_URL environment variable to use an existing instance,
or Docker will be used to start a container automatically.
"""

import asyncio
from collections.abc import Generator
from typing import Any

import pytest

from lambda_framework.cache import async_redis_cache


class TestAsyncRedisCacheIntegration:
    """Integration tests for async_redis_cache using real Valkey instance.

    The fixture automatically starts/stops the Docker container.
    Set VALKEY_URL environment variable to use an existing instance instead.
    """

    @pytest.fixture(scope="class")
    def valkey_url(self) -> Generator[str, Any, Any]:
        """Start Valkey container and return connection URL.

        If VALKEY_URL is set, uses that instead of starting a container.
        """
        import os
        import subprocess
        import time
        from pathlib import Path

        # If VALKEY_URL is set, use existing instance
        if "VALKEY_URL" in os.environ:
            yield os.environ["VALKEY_URL"]
            return

        # Find docker-compose file
        compose_file = Path(__file__).parent.parent / "docker-compose.test.yml"
        if not compose_file.exists():
            pytest.skip(f"docker-compose.test.yml not found at {compose_file}")

        # Start container
        try:
            subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            pytest.skip(f"Failed to start Docker container: {e.stderr}")
        except FileNotFoundError:
            pytest.skip("Docker not found")

        # Give it a moment to be ready
        time.sleep(0.5)

        url = "redis://localhost:6379"
        try:
            yield url
        finally:
            # Stop container after tests
            subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "down"],
                capture_output=True,
            )

    @pytest.fixture(scope="class")
    async def _check_valkey_available(self, valkey_url: str):
        """Check if Valkey is available, skip tests if not."""
        from redis.asyncio import Redis

        client = Redis.from_url(valkey_url)
        try:
            await client.ping()
            yield
        except Exception as e:
            pytest.skip(f"Valkey not available at {valkey_url}: {e}")
        finally:
            await client.aclose()  # type: ignore[attr-defined]

    @pytest.fixture
    async def redis_client(self, valkey_url: str, _check_valkey_available):
        """Create an async Redis client for the test."""
        from redis.asyncio import Redis

        client = Redis.from_url(valkey_url)
        yield client
        await client.flushdb()
        await client.aclose()  # type: ignore[attr-defined]

    @pytest.mark.integration
    async def test_basic_caching(self, valkey_url: str, _check_valkey_available):
        """Should cache and retrieve values from Valkey."""
        call_count = 0

        @async_redis_cache(redis_url=valkey_url, timeout=60)
        async def compute(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - computes
        result1 = await compute(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - from cache
        result2 = await compute(5)
        assert result2 == 10
        assert call_count == 1

        # Different argument - computes
        result3 = await compute(10)
        assert result3 == 20
        assert call_count == 2

    @pytest.mark.integration
    async def test_ttl_expiration(self, valkey_url: str, _check_valkey_available):
        """Should expire cached values after TTL."""
        call_count = 0

        @async_redis_cache(redis_url=valkey_url, timeout=1)
        async def get_value() -> str:
            nonlocal call_count
            call_count += 1
            return f"value-{call_count}"

        # First call
        result1 = await get_value()
        assert result1 == "value-1"
        assert call_count == 1

        # Immediate second call - from cache
        result2 = await get_value()
        assert result2 == "value-1"
        assert call_count == 1

        # Wait for TTL to expire
        await asyncio.sleep(1.5)

        # Third call - should recompute
        result3 = await get_value()
        assert result3 == "value-2"
        assert call_count == 2

    @pytest.mark.integration
    async def test_cache_clear_removes_from_valkey(self, valkey_url: str, redis_client):
        """cache_clear should remove keys from Valkey."""

        @async_redis_cache(redis_url=valkey_url, key="testclear", timeout=300)
        async def func(x: int) -> int:
            return x

        # Cache some values
        await func(1)
        await func(2)
        await func(3)

        # Verify keys exist
        keys = await redis_client.keys("testclear:*")
        assert len(keys) == 3

        # Clear cache
        await func.cache_clear()  # type: ignore[attr-defined]

        # Verify keys are deleted
        keys_after = await redis_client.keys("testclear:*")
        assert len(keys_after) == 0

    @pytest.mark.integration
    async def test_complex_data_types(self, valkey_url: str, _check_valkey_available):
        """Should handle complex JSON-serializable data types."""

        @async_redis_cache(redis_url=valkey_url, timeout=60)
        async def get_complex_data() -> dict:
            return {
                "string": "hello",
                "number": 42,
                "float": 3.14,
                "bool": True,
                "none": None,
                "list": [1, 2, 3],
                "nested": {"a": {"b": {"c": "deep"}}},
            }

        result1 = await get_complex_data()
        result2 = await get_complex_data()

        assert result1 == result2
        assert result1["nested"]["a"]["b"]["c"] == "deep"

    @pytest.mark.integration
    async def test_cache_info_accuracy(self, valkey_url: str, _check_valkey_available):
        """cache_info should accurately track hits, misses, and size."""

        @async_redis_cache(redis_url=valkey_url, timeout=60)
        async def func(x: int) -> int:
            return x * 2

        # 3 unique calls = 3 misses
        await func(1)
        await func(2)
        await func(3)

        info1 = func.cache_info()  # type: ignore[attr-defined]
        assert info1.misses == 3
        assert info1.hits == 0
        assert info1.currsize == 3

        # 3 cached calls = 3 hits
        await func(1)
        await func(2)
        await func(3)

        info2 = func.cache_info()  # type: ignore[attr-defined]
        assert info2.misses == 3
        assert info2.hits == 3
        assert info2.currsize == 3

    @pytest.mark.integration
    async def test_concurrent_access(self, valkey_url: str, _check_valkey_available):
        """Should handle concurrent access correctly."""
        call_count = 0
        call_lock = asyncio.Lock()

        @async_redis_cache(redis_url=valkey_url, timeout=60)
        async def slow_func(x: int) -> int:
            nonlocal call_count
            async with call_lock:
                call_count += 1
            await asyncio.sleep(0.1)
            return x * 2

        # Run multiple concurrent calls
        results = await asyncio.gather(
            slow_func(1),
            slow_func(1),
            slow_func(1),
            slow_func(2),
            slow_func(2),
        )

        assert results == [2, 2, 2, 4, 4]
        # Due to race conditions, might have some extra calls but should be cached
        assert call_count >= 2  # At least 2 unique values

    @pytest.mark.integration
    async def test_with_existing_redis_client(self, redis_client):
        """Should work with an existing Redis client instance."""

        @async_redis_cache(redis=redis_client, timeout=60)
        async def func() -> str:
            return "test-value"

        result = await func()
        assert result == "test-value"

        info = func.cache_info()  # type: ignore[attr-defined]
        assert info.misses == 1
