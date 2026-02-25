"""Async EventBridge publishing helper for forwarding validated events to a custom event bus."""

from __future__ import annotations

import json
import logging
from types import TracebackType
from typing import Any

import aioboto3

logger = logging.getLogger(__name__)

__all__ = ["EventBridgePublisher"]


class EventBridgePublisher:
    """Async wrapper around ``events:PutEvents`` for publishing to an EventBridge bus.

    Can be used as an async context manager for efficient client reuse across
    multiple publishes, or called directly (a new client is created per call).

    Context manager usage (preferred for multiple publishes)::

        publisher = EventBridgePublisher(
            event_bus_name="my-function-bus",
            source="webhook.github",
        )
        async with publisher:
            await publisher.put_event("push", payload_a)
            await publisher.put_event("pull_request", payload_b)

    Direct usage (convenient for single publishes)::

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
        self._owns_client = False

    async def __aenter__(self) -> EventBridgePublisher:
        """Enter the async context manager, creating a reusable client."""
        ctx = self._session.client("events")
        self._client = await ctx.__aenter__()
        self._owns_client = True
        self._client_ctx = ctx
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager, closing the client."""
        if self._owns_client and hasattr(self, "_client_ctx"):
            await self._client_ctx.__aexit__(exc_type, exc_val, exc_tb)
            self._client = None
            self._owns_client = False

    async def _get_client(self) -> Any:
        """Return the active client, creating a one-shot client if needed."""
        if self._client is not None:
            return self._client
        ctx = self._session.client("events")
        client = await ctx.__aenter__()
        self._client = client
        self._client_ctx = ctx
        self._owns_client = True
        return client

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

        client = await self._get_client()
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
