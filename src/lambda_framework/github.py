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

    def __init__(
        self,
        max_concurrency: int,
        valkey_url: str | None = None,
        valkey: Redis | None = None,
        aiovalkey: AIORedis | None = None,
    ) -> None:
        """Initialize the throttler."""
        self.max_concurrency = max_concurrency
        self._valkey_url: str | None = valkey_url
        self._valkey: Redis | None = valkey
        self._aiovalkey: AIORedis | None = aiovalkey
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
                key=_THROTTLE_KEY,
                masters={self._get_valkey()},
            )
        return self._semaphore

    @property
    def async_semaphore(self) -> AIOSemaphore:
        """Get the async semaphore."""
        if self._async_semaphore is None:
            self._async_semaphore = AIOSemaphore(
                value=self.max_concurrency,
                key=_THROTTLE_KEY,
                masters={self._get_aiovalkey()},
            )
        return self._async_semaphore

    @override
    @contextmanager
    def acquire(self, request: httpx.Request) -> Generator[None, Any, Any]:
        with self.semaphore:
            yield
        if request.method in self._MUTATING_METHODS:
            time.sleep(1)

    @override
    @asynccontextmanager
    async def async_acquire(self, request: httpx.Request) -> AsyncGenerator[None, Any]:
        async with self.async_semaphore:
            yield
        if request.method in self._MUTATING_METHODS:
            await asyncio.sleep(1)
