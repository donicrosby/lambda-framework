"""Slack error notification helper for posting structured error messages to a channel."""

from __future__ import annotations

import asyncio
import datetime
import functools
import logging
import traceback
from typing import Any

from slack_sdk import WebClient
from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

__all__ = ["SlackNotifier"]

_TRACEBACK_MAX_CHARS = 2900
_TRACEBACK_MAX_LINES = 15


def _detect_event_type(event: dict[str, Any] | None) -> str:
    """Return a human-readable label for the Lambda event type."""
    if event is None:
        return "unknown"
    if "requestContext" in event:
        return "API Gateway"
    if all(k in event for k in ("source", "detail-type", "detail")):
        return "EventBridge"
    records = event.get("Records")
    if isinstance(records, list) and records:
        src = records[0].get("eventSource", "")
        if src == "aws:sqs":
            return "SQS"
    return "unknown"


def _truncate_traceback(exc: BaseException) -> str:
    """Format a traceback string, truncated to fit Slack's block text limit."""
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_text = "".join(lines)
    tb_lines = tb_text.splitlines()
    if len(tb_lines) > _TRACEBACK_MAX_LINES:
        tb_lines = tb_lines[-_TRACEBACK_MAX_LINES:]
    tb_text = "\n".join(tb_lines)
    if len(tb_text) > _TRACEBACK_MAX_CHARS:
        tb_text = "..." + tb_text[-_TRACEBACK_MAX_CHARS:]
    return tb_text


def _format_error_blocks(
    exc: BaseException,
    context: Any | None = None,
    event: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build Slack Block Kit blocks describing an error.

    Args:
        exc: The exception that was raised.
        context: The Lambda context object (if available).
        event: The raw Lambda event dict (if available).

    Returns:
        A list of Slack block dicts suitable for ``chat.postMessage``.

    """
    exc_type = type(exc).__qualname__
    func_name = getattr(context, "function_name", None) or "lambda"
    request_id = getattr(context, "aws_request_id", None)
    event_type = _detect_event_type(event)
    timestamp = datetime.datetime.now(tz=datetime.UTC).isoformat()
    tb_text = _truncate_traceback(exc)

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":rotating_light: {exc_type} in {func_name}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Error:* {exc}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{tb_text}```",
            },
        },
    ]

    context_elements: list[dict[str, Any]] = [
        {"type": "mrkdwn", "text": f"*Event type:* {event_type}"},
        {"type": "mrkdwn", "text": f"*Timestamp:* {timestamp}"},
    ]
    if request_id:
        context_elements.append(
            {"type": "mrkdwn", "text": f"*Request ID:* {request_id}"}
        )

    blocks.append({"type": "context", "elements": context_elements})
    return blocks


class SlackNotifier:
    """Send structured error (or arbitrary) messages to a Slack channel.

    Uses lazy client initialisation so creating the notifier is cheap.  Both
    synchronous and asynchronous methods are provided.

    Direct usage::

        notifier = SlackNotifier(token="xoxb-...", channel="#alerts")
        try:
            do_work()
        except Exception as exc:
            notifier.send_error(exc, context=lambda_context, event=event)
            raise

    Decorator usage::

        notifier = SlackNotifier(token="xoxb-...", channel="#alerts")

        @notifier.error_handler
        async def my_handler(event, context):
            ...

    Args:
        token: A Slack Bot User OAuth token (``xoxb-...``).
        channel: The channel ID or name to post messages to.
        username: Optional display name for the bot message.
        icon_emoji: Optional emoji for the bot avatar (e.g. ``":warning:"``).

    """

    def __init__(
        self,
        token: str,
        channel: str,
        *,
        username: str | None = None,
        icon_emoji: str | None = None,
    ) -> None:
        """Initialise the notifier.

        Args:
            token: Slack Bot User OAuth token.
            channel: Target channel ID or name.
            username: Optional display name for messages.
            icon_emoji: Optional emoji for the bot avatar.

        """
        self._token = token
        self._channel = channel
        self._username = username
        self._icon_emoji = icon_emoji
        self._client: WebClient | None = None
        self._async_client: AsyncWebClient | None = None
        self._in_context_manager = False

    def _get_client(self) -> WebClient:
        """Return the sync ``WebClient``, creating it on first access."""
        if self._client is None:
            self._client = WebClient(token=self._token)
        return self._client

    def _get_async_client(self) -> AsyncWebClient:
        """Return the async ``AsyncWebClient``, creating it on first access."""
        if self._async_client is None:
            self._async_client = AsyncWebClient(token=self._token)
        return self._async_client

    def _base_kwargs(self) -> dict[str, Any]:
        """Build keyword arguments shared by every ``chat_postMessage`` call."""
        kwargs: dict[str, Any] = {"channel": self._channel}
        if self._username:
            kwargs["username"] = self._username
        if self._icon_emoji:
            kwargs["icon_emoji"] = self._icon_emoji
        return kwargs

    # -- lifecycle management ----------------------------------------------

    async def __aenter__(self) -> SlackNotifier:
        """Enter the async context manager for client reuse without leaks."""
        self._in_context_manager = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: type[BaseException] | None,
    ) -> None:
        """Exit the async context manager, closing the async client session."""
        self._in_context_manager = False
        await self.async_close()

    async def async_close(self) -> None:
        """Close the underlying ``aiohttp.ClientSession`` held by the async client.

        Safe to call multiple times or when no async client has been created.

        """
        if self._async_client is not None:
            session = getattr(self._async_client, "session", None)
            if session is not None and not session.closed:
                await session.close()
            self._async_client = None

    # -- public sync API ---------------------------------------------------

    def send_message(
        self,
        text: str,
        *,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Post a message to the configured Slack channel (sync).

        Args:
            text: Fallback / notification text.
            blocks: Optional Block Kit blocks for rich formatting.

        """
        client = self._get_client()
        kwargs = self._base_kwargs()
        kwargs["text"] = text
        if blocks:
            kwargs["blocks"] = blocks
        client.chat_postMessage(**kwargs)

    def send_error(
        self,
        exc: BaseException,
        *,
        context: Any | None = None,
        event: dict[str, Any] | None = None,
    ) -> None:
        """Format and post an error notification to Slack (sync).

        Failures to deliver the message are logged and swallowed so that a
        Slack outage does not mask the original error.

        Args:
            exc: The exception that occurred.
            context: Lambda context object (provides function name, request ID).
            event: Raw Lambda event dict (used to detect event type).

        """
        try:
            blocks = _format_error_blocks(exc, context=context, event=event)
            fallback = f"{type(exc).__qualname__}: {exc}"
            self.send_message(fallback, blocks=blocks)
        except Exception:
            logger.exception("Failed to send error notification to Slack")

    # -- public async API --------------------------------------------------

    async def async_send_message(
        self,
        text: str,
        *,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Post a message to the configured Slack channel (async).

        Args:
            text: Fallback / notification text.
            blocks: Optional Block Kit blocks for rich formatting.

        """
        client = self._get_async_client()
        kwargs = self._base_kwargs()
        kwargs["text"] = text
        if blocks:
            kwargs["blocks"] = blocks
        try:
            await client.chat_postMessage(**kwargs)
        finally:
            if not self._in_context_manager:
                await self.async_close()

    async def async_send_error(
        self,
        exc: BaseException,
        *,
        context: Any | None = None,
        event: dict[str, Any] | None = None,
    ) -> None:
        """Format and post an error notification to Slack (async).

        Failures to deliver the message are logged and swallowed so that a
        Slack outage does not mask the original error.

        Args:
            exc: The exception that occurred.
            context: Lambda context object (provides function name, request ID).
            event: Raw Lambda event dict (used to detect event type).

        """
        try:
            blocks = _format_error_blocks(exc, context=context, event=event)
            fallback = f"{type(exc).__qualname__}: {exc}"
            await self.async_send_message(fallback, blocks=blocks)
        except Exception:
            logger.exception("Failed to send error notification to Slack")

    # -- decorator ---------------------------------------------------------

    def error_handler(self, func):  # noqa: D401
        """Catch exceptions from *func*, send a Slack notification, and re-raise.

        Works with both sync and async handlers.  The wrapped function's
        signature is preserved.

        Example::

            @notifier.error_handler
            async def my_handler(event, context):
                ...

        """
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    _ctx = kwargs.get("context", args[1] if len(args) > 1 else None)
                    _evt = kwargs.get("event", args[0] if args else None)
                    await self.async_send_error(exc, context=_ctx, event=_evt)
                    raise

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                _ctx = kwargs.get("context", args[1] if len(args) > 1 else None)
                _evt = kwargs.get("event", args[0] if args else None)
                self.send_error(exc, context=_ctx, event=_evt)
                raise

        return sync_wrapper
