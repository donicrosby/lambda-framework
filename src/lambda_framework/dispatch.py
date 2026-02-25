"""Lambda event dispatcher for routing between API Gateway, EventBridge, and SQS events."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["create_dispatcher"]

EventHandler = Callable[[dict[str, Any], Any], Any]


def _is_api_gateway_event(event: dict[str, Any]) -> bool:
    """Detect API Gateway REST (v1) or HTTP API (v2) proxy events."""
    if "requestContext" not in event:
        return False
    if "httpMethod" in event:
        return True
    rc = event.get("requestContext", {})
    return "http" in rc


def _is_eventbridge_event(event: dict[str, Any]) -> bool:
    return all(k in event for k in ("source", "detail-type", "detail"))


def _is_sqs_event(event: dict[str, Any]) -> bool:
    records = event.get("Records")
    if not isinstance(records, list) or not records:
        return False
    return records[0].get("eventSource") == "aws:sqs"


def _ensure_event_loop() -> None:
    """Guarantee an asyncio event loop is attached to the current thread.

    Python 3.10+ raises ``RuntimeError`` from ``asyncio.get_event_loop()``
    when no loop has been set.  Libraries such as Mangum call that function
    internally, so we must ensure a loop exists before handing off control.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _invoke(handler: EventHandler, event: dict[str, Any], context: Any) -> Any:
    """Call *handler* and bridge async results to sync for the Lambda runtime."""
    result = handler(event, context)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def _dispatch(
    event: dict[str, Any],
    context: Any,
    *,
    http_handler: EventHandler | None,
    eventbridge_handler: EventHandler | None,
    sqs_handler: EventHandler | None,
) -> Any:
    """Route *event* to the matching sub-handler."""
    if _is_api_gateway_event(event):
        if http_handler is None:
            raise ValueError(
                "Received API Gateway event but no http_handler is registered"
            )
        logger.debug("Dispatching to http_handler")
        _ensure_event_loop()
        return http_handler(event, context)

    if _is_eventbridge_event(event):
        if eventbridge_handler is None:
            raise ValueError(
                "Received EventBridge event but no eventbridge_handler is registered"
            )
        logger.debug("Dispatching to eventbridge_handler")
        return _invoke(eventbridge_handler, event, context)

    if _is_sqs_event(event):
        if sqs_handler is None:
            raise ValueError("Received SQS event but no sqs_handler is registered")
        logger.debug("Dispatching to sqs_handler")
        return _invoke(sqs_handler, event, context)

    raise ValueError(f"Unrecognised event type, top-level keys: {sorted(event.keys())}")


def create_dispatcher(
    *,
    http_handler: EventHandler | None = None,
    eventbridge_handler: EventHandler | None = None,
    sqs_handler: EventHandler | None = None,
    error_notifier: Any | None = None,
) -> EventHandler:
    """Build a Lambda handler that routes events to the appropriate sub-handler.

    Handlers may be sync or async.  Async handlers (coroutine functions or
    functions that return an awaitable) are automatically executed via
    ``asyncio.run()`` so the returned dispatcher is always Lambda-compatible.

    Args:
        http_handler: Handler for API Gateway proxy events (e.g. Mangum).
        eventbridge_handler: Handler for EventBridge events (sync or async).
        sqs_handler: Handler for SQS batch events (sync or async).
        error_notifier: Optional object with a ``send_error(exc, *, context,
            event)`` method (e.g. :class:`~lambda_framework.slack.SlackNotifier`).
            When provided, unhandled exceptions from any sub-handler are
            reported via this notifier before being re-raised.

    Returns:
        A Lambda-compatible handler ``(event, context) -> response``.

    Raises:
        ValueError: If the event type cannot be identified or no handler is
            registered for the detected event type.

    """

    def handler(event: dict[str, Any], context: Any) -> Any:
        try:
            return _dispatch(
                event,
                context,
                http_handler=http_handler,
                eventbridge_handler=eventbridge_handler,
                sqs_handler=sqs_handler,
            )
        except Exception as exc:
            if error_notifier is not None:
                try:
                    error_notifier.send_error(exc, context=context, event=event)
                except Exception:
                    logger.exception("error_notifier.send_error failed")
            raise

    return handler
