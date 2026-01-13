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

_THROTTLE_KEY = "github-request-limit"


class LambdaThrottler(BaseThrottler):
    """Lambda throttler."""

    _MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, max_concurrency: int, valkey_url: str) -> None:
        """Initialize the throttler."""
        self.max_concurrency = max_concurrency
        self._valkey_url = valkey_url
        self._valkey: Redis | None = None
        self._aiovalkey: AIORedis | None = None
        self._semaphore: Semaphore | None = None
        self._async_semaphore: AIOSemaphore | None = None

    @property
    def semaphore(self) -> Semaphore:
        """Get the semaphore."""
        if self._semaphore is None:
            self._valkey = Redis.from_url(url=self._valkey_url)
            self._semaphore = Semaphore(
                value=self.max_concurrency, key=_THROTTLE_KEY, masters={self._valkey}
            )
        return self._semaphore

    @property
    def async_semaphore(self) -> AIOSemaphore:
        """Get the async semaphore."""
        if self._async_semaphore is None:
            self._aiovalkey = AIORedis.from_url(url=self._valkey_url)
            self._async_semaphore = AIOSemaphore(
                value=self.max_concurrency, key=_THROTTLE_KEY, masters={self._aiovalkey}
            )
        return self._async_semaphore

    @override
    @contextmanager
    def aquire(self, request: httpx.Request) -> Generator[None, Any, Any]:
        """Acquire a semaphore for the request."""
        with self.semaphore:
            yield
        if request.method in self._MUTATING_METHODS:
            time.sleep(1)

    @override
    @asynccontextmanager
    async def aquire_async(self, request: httpx.Request) -> AsyncGenerator[None, Any]:
        """Acquire a semaphore for the request."""
        async with self.async_semaphore:
            yield
        if request.method in self._MUTATING_METHODS:
            await asyncio.sleep(1)
