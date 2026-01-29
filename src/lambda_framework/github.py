"""GitHub rate limiter module."""

import asyncio
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import httpx
from githubkit.throttling import BaseThrottler
from pottery_semaphore import AIOSemaphore, Semaphore
from redis import Redis
from redis.asyncio import Redis as AIORedis
from typing_extensions import override

__all__ = ["LambdaThrottler"]

_DEFAULT_THROTTLE_KEY = "github-request-limit"
_DEFAULT_MUTATING_SLEEP_SECONDS = 1.0


class LambdaThrottler(BaseThrottler):
    """Lambda throttler for GitHub API rate limiting.

    Uses a distributed semaphore (via Redis/Valkey) to limit concurrent requests
    across multiple Lambda instances. Optionally adds a delay after mutating
    HTTP methods (POST, PUT, PATCH, DELETE) to respect GitHub's secondary rate limits.

    Args:
        max_concurrency: Maximum number of concurrent requests allowed.
        valkey_url: URL for Redis/Valkey connection. Used if valkey/aiovalkey not provided.
        valkey: Existing synchronous Redis client instance.
        aiovalkey: Existing async Redis client instance.
        throttle_key: Redis key for the distributed semaphore. Defaults to "github-request-limit".
        mutating_sleep_seconds: Seconds to sleep after mutating requests. Defaults to 1.0.
            Set to 0 to disable the delay.

    """

    _MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        max_concurrency: int,
        valkey_url: str | None = None,
        valkey: Redis | None = None,
        aiovalkey: AIORedis | None = None,
        throttle_key: str = _DEFAULT_THROTTLE_KEY,
        mutating_sleep_seconds: float = _DEFAULT_MUTATING_SLEEP_SECONDS,
    ) -> None:
        """Initialize the throttler."""
        self.max_concurrency = max_concurrency
        self._valkey_url: str | None = valkey_url
        self._valkey: Redis | None = valkey
        self._aiovalkey: AIORedis | None = aiovalkey
        self._throttle_key = throttle_key
        self._mutating_sleep_seconds = mutating_sleep_seconds
        self._semaphore: Semaphore | None = None
        self._async_semaphore: AIOSemaphore | None = None

    def _get_valkey(self) -> Redis:
        """Get the valkey."""
        if self._valkey is None:
            if self._valkey_url is None:
                raise ValueError("valkey_url is required")
            self._valkey = Redis.from_url(url=self._valkey_url)
        return self._valkey

    def _get_aiovalkey(self) -> AIORedis:
        """Get the aiovalkey."""
        if self._aiovalkey is None:
            if self._valkey_url is None:
                raise ValueError("valkey_url is required")
            self._aiovalkey = AIORedis.from_url(url=self._valkey_url)
        return self._aiovalkey

    @property
    def semaphore(self) -> Semaphore:
        """Get the semaphore."""
        if self._semaphore is None:
            self._semaphore = Semaphore(
                value=self.max_concurrency,
                key=self._throttle_key,
                masters={self._get_valkey()},
            )
        return self._semaphore

    @property
    def async_semaphore(self) -> AIOSemaphore:
        """Get the async semaphore."""
        if self._async_semaphore is None:
            self._async_semaphore = AIOSemaphore(
                value=self.max_concurrency,
                key=self._throttle_key,
                masters={self._get_aiovalkey()},
            )
        return self._async_semaphore

    @override
    @contextmanager
    def acquire(self, request: httpx.Request) -> Generator[None, Any, Any]:
        """Acquire the semaphore for a request.

        The semaphore limits concurrent requests. After the request completes,
        if it was a mutating method (POST, PUT, PATCH, DELETE), a configurable
        delay is added before returning. This delay occurs AFTER releasing the
        semaphore, so it doesn't block other concurrent requests.

        """
        with self.semaphore:
            yield
        if (
            request.method in self._MUTATING_METHODS
            and self._mutating_sleep_seconds > 0
        ):
            time.sleep(self._mutating_sleep_seconds)

    @override
    @asynccontextmanager
    async def async_acquire(self, request: httpx.Request) -> AsyncGenerator[None, Any]:
        """Acquire the semaphore for an async request.

        The semaphore limits concurrent requests. After the request completes,
        if it was a mutating method (POST, PUT, PATCH, DELETE), a configurable
        delay is added before returning. This delay occurs AFTER releasing the
        semaphore, so it doesn't block other concurrent requests.

        """
        async with self.async_semaphore:
            yield
        if (
            request.method in self._MUTATING_METHODS
            and self._mutating_sleep_seconds > 0
        ):
            await asyncio.sleep(self._mutating_sleep_seconds)
