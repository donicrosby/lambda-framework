"""Async EventBridge publishing helper for forwarding validated events to a custom event bus."""

from __future__ import annotations

import asyncio
import json
import logging
from types import TracebackType
from typing import Any

import aioboto3

logger = logging.getLogger(__name__)

__all__ = ["EventBridgePublisher"]


class EventBridgePublisher:
    """Async wrapper around ``events:PutEvents`` for publishing to an EventBridge bus.

    The underlying ``aioboto3`` client is created lazily on the first publish,
    reused across concurrent tasks within the same invocation, and
    automatically closed when the last concurrent caller finishes.  This
    keeps the connection pool alive for the duration of the work while
    ensuring the connector is properly closed before ``asyncio.run()``
    tears down the event loop.

    Context manager usage (deterministic cleanup)::

        publisher = EventBridgePublisher(
            event_bus_name="my-function-bus",
            source="webhook.github",
        )
        async with publisher:
            await publisher.put_event("push", payload_a)
            await publisher.put_event("pull_request", payload_b)

    Direct usage (client auto-closes when the last caller finishes)::

        publisher = EventBridgePublisher(
            event_bus_name="my-function-bus",
            source="webhook.github",
        )
        await publisher.put_event("push", payload)

    Args:
        event_bus_name: Name or ARN of the target EventBridge event bus.
        source: The ``source`` field written to every event (e.g. ``"webhook.github"``).
        session: Optional pre-configured ``aioboto3.Session``.  When *None* a
            default session is created.

    """

    def __init__(
        self,
        event_bus_name: str,
        source: str,
        *,
        session: aioboto3.Session | None = None,
    ) -> None:
        """Initialise the publisher.

        Args:
            event_bus_name: Name or ARN of the target EventBridge event bus.
            source: The ``source`` field written to every event.
            session: Optional pre-configured ``aioboto3.Session``.

        """
        self._event_bus_name = event_bus_name
        self._source = source
        self._session = session or aioboto3.Session()
        self._client: Any | None = None
        self._client_ctx: Any | None = None
        self._in_context_manager = False
        self._lock = asyncio.Lock()
        self._ref_count: int = 0

    async def _acquire_client(self) -> Any:
        """Create the client if needed, increment the ref count, and return it.

        The ``asyncio.Lock`` ensures that only one task creates the client
        while concurrent callers wait.  The lock is released before any I/O
        so that API calls can proceed in parallel.

        """
        async with self._lock:
            if self._client is None:
                ctx = self._session.client("events")
                self._client = await ctx.__aenter__()
                self._client_ctx = ctx
            self._ref_count += 1
            return self._client

    async def _release_client(self) -> None:
        """Decrement the ref count and close the client when it reaches zero."""
        async with self._lock:
            self._ref_count -= 1
            if self._ref_count == 0 and not self._in_context_manager:
                await self.close()

    async def __aenter__(self) -> EventBridgePublisher:
        """Enter the async context manager, eagerly creating the client."""
        self._in_context_manager = True
        async with self._lock:
            if self._client is None:
                ctx = self._session.client("events")
                self._client = await ctx.__aenter__()
                self._client_ctx = ctx
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager, closing the client."""
        self._in_context_manager = False
        await self.close()

    async def close(self) -> None:
        """Close the underlying ``aioboto3`` client and its connection pool.

        Safe to call multiple times or when no client has been created.

        """
        if self._client_ctx is not None:
            await self._client_ctx.__aexit__(None, None, None)
            self._client = None
            self._client_ctx = None
        self._ref_count = 0

    async def put_event(
        self,
        detail_type: str,
        detail: dict[str, Any] | str,
        *,
        resources: list[str] | None = None,
        trace_header: str | None = None,
    ) -> dict[str, Any]:
        """Publish a single event to EventBridge.

        Args:
            detail_type: Free-form string describing the event (e.g. ``"push"``,
                ``"pull_request.opened"``).
            detail: Event payload. Dicts are JSON-serialised automatically.
            resources: Optional list of ARNs associated with the event.
            trace_header: Optional X-Ray trace header for distributed tracing.

        Returns:
            The raw ``PutEvents`` response from the EventBridge API.

        Raises:
            RuntimeError: If EventBridge reports any failed entries.

        """
        entry: dict[str, Any] = {
            "Source": self._source,
            "DetailType": detail_type,
            "Detail": json.dumps(detail) if isinstance(detail, dict) else detail,
            "EventBusName": self._event_bus_name,
        }
        if resources:
            entry["Resources"] = resources
        if trace_header:
            entry["TraceHeader"] = trace_header

        return await self.put_events([entry])

    async def _execute_put_events(
        self, client: Any, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Send *entries* via *client* and raise on partial failure."""
        response = await client.put_events(Entries=entries)

        failed = response.get("FailedEntryCount", 0)
        if failed:
            failed_entries = [
                e for e in response.get("Entries", []) if e.get("ErrorCode")
            ]
            logger.error(
                "EventBridge PutEvents failed for %d entries: %s",
                failed,
                failed_entries,
            )
            raise RuntimeError(
                f"EventBridge PutEvents failed for {failed} of {len(entries)} entries: "
                f"{failed_entries}"
            )

        logger.debug("Published %d event(s) to %s", len(entries), self._event_bus_name)
        return response

    async def put_events(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Publish one or more pre-built entries to EventBridge.

        Each entry must follow the shape expected by the ``PutEvents`` API
        (``Source``, ``DetailType``, ``Detail``, etc.).  This method fills in
        ``EventBusName`` and ``Source`` when not already present.

        Args:
            entries: List of PutEvents entry dicts.

        Returns:
            The raw ``PutEvents`` response from the EventBridge API.

        Raises:
            RuntimeError: If EventBridge reports any failed entries.

        """
        for entry in entries:
            entry.setdefault("EventBusName", self._event_bus_name)
            entry.setdefault("Source", self._source)

        if self._in_context_manager:
            return await self._execute_put_events(self._client, entries)

        client = await self._acquire_client()
        try:
            return await self._execute_put_events(client, entries)
        finally:
            await self._release_client()
