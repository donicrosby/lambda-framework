"""Tests for the Slack error notification module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lambda_framework.slack import (
    SlackNotifier,
    _detect_event_type,
    _format_error_blocks,
    _truncate_traceback,
)

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------


def _make_lambda_context(
    function_name: str = "my-lambda",
    request_id: str = "req-abc-123",
) -> MagicMock:
    ctx = MagicMock()
    ctx.function_name = function_name
    ctx.aws_request_id = request_id
    return ctx


API_GATEWAY_EVENT = {
    "requestContext": {"http": {"method": "POST"}},
    "body": "{}",
}

EVENTBRIDGE_EVENT = {
    "source": "webhook.github",
    "detail-type": "push",
    "detail": {"ref": "refs/heads/main"},
}

SQS_EVENT = {
    "Records": [{"eventSource": "aws:sqs", "body": "hello"}],
}


# ===========================================================================
# _detect_event_type
# ===========================================================================


class TestDetectEventType:
    """Verify the helper labels event types correctly."""

    def test_api_gateway(self):
        """Identify API Gateway events."""
        assert _detect_event_type(API_GATEWAY_EVENT) == "API Gateway"

    def test_eventbridge(self):
        """Identify EventBridge events."""
        assert _detect_event_type(EVENTBRIDGE_EVENT) == "EventBridge"

    def test_sqs(self):
        """Identify SQS events."""
        assert _detect_event_type(SQS_EVENT) == "SQS"

    def test_unknown(self):
        """Return 'unknown' for unrecognised events."""
        assert _detect_event_type({"foo": "bar"}) == "unknown"

    def test_none(self):
        """Return 'unknown' when event is None."""
        assert _detect_event_type(None) == "unknown"


# ===========================================================================
# _truncate_traceback
# ===========================================================================


class TestTruncateTraceback:
    """Verify traceback truncation respects line and character limits."""

    def test_short_traceback(self):
        """Short tracebacks are returned in full."""
        try:
            raise ValueError("boom")
        except ValueError as exc:
            result = _truncate_traceback(exc)

        assert "ValueError: boom" in result

    def test_long_traceback_truncated(self):
        """Tracebacks exceeding the character limit are prefixed with '...'."""
        try:
            raise RuntimeError("x" * 5000)
        except RuntimeError as exc:
            result = _truncate_traceback(exc)

        assert len(result) <= 3001  # 3000 + leading "..."


# ===========================================================================
# _format_error_blocks
# ===========================================================================


class TestFormatErrorBlocks:
    """Verify Block Kit output structure."""

    def test_basic_structure(self):
        """Return header, error section, traceback section, and context."""
        try:
            raise ValueError("test error")
        except ValueError as exc:
            blocks = _format_error_blocks(exc)

        assert len(blocks) == 4
        assert blocks[0]["type"] == "header"
        assert blocks[1]["type"] == "section"
        assert blocks[2]["type"] == "section"
        assert blocks[3]["type"] == "context"

    def test_header_contains_exception_type(self):
        """Header text includes the exception class name."""
        try:
            raise TypeError("bad type")
        except TypeError as exc:
            blocks = _format_error_blocks(exc)

        header_text = blocks[0]["text"]["text"]
        assert "TypeError" in header_text

    def test_context_includes_function_name_and_request_id(self):
        """Context elements include Lambda metadata when a context is provided."""
        ctx = _make_lambda_context()
        try:
            raise RuntimeError("fail")
        except RuntimeError as exc:
            blocks = _format_error_blocks(exc, context=ctx, event=SQS_EVENT)

        elements = blocks[3]["elements"]
        texts = [e["text"] for e in elements]
        assert any("SQS" in t for t in texts)
        assert any("req-abc-123" in t for t in texts)

    def test_no_context(self):
        """Gracefully handle missing context (defaults to 'lambda')."""
        try:
            raise RuntimeError("fail")
        except RuntimeError as exc:
            blocks = _format_error_blocks(exc)

        header_text = blocks[0]["text"]["text"]
        assert "lambda" in header_text


# ===========================================================================
# SlackNotifier construction & lazy clients
# ===========================================================================


class TestSlackNotifierInit:
    """Verify constructor and lazy client creation."""

    def test_clients_are_none_initially(self):
        """Clients are not created until first use."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        assert notifier._client is None
        assert notifier._async_client is None
        assert notifier._in_context_manager is False

    def test_get_client_creates_webclient(self):
        """_get_client creates a WebClient on first call."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        client = notifier._get_client()
        assert client is not None
        assert notifier._get_client() is client  # same instance

    async def test_acquire_creates_async_webclient(self):
        """_acquire_async_client creates an AsyncWebClient on first call."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        client = await notifier._acquire_async_client()
        assert client is not None
        assert notifier._async_ref_count == 1
        client2 = await notifier._acquire_async_client()
        assert client2 is client
        assert notifier._async_ref_count == 2


# ===========================================================================
# Lifecycle management (async close / context manager)
# ===========================================================================


class TestSlackNotifierLifecycle:
    """Verify async context manager and async_close behaviour."""

    async def test_async_close_closes_session(self):
        """async_close() closes the underlying aiohttp session."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_client = MagicMock()
        mock_client.session = mock_session
        notifier._async_client = mock_client
        notifier._async_ref_count = 1

        await notifier.async_close()

        mock_session.close.assert_awaited_once()
        assert notifier._async_client is None
        assert notifier._async_ref_count == 0

    async def test_async_close_is_idempotent(self):
        """Calling async_close() when no client exists is a no-op."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        await notifier.async_close()
        assert notifier._async_client is None

    async def test_async_close_skips_already_closed_session(self):
        """async_close() does not close an already-closed session."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        mock_session = AsyncMock()
        mock_session.closed = True
        mock_client = MagicMock()
        mock_client.session = mock_session
        notifier._async_client = mock_client

        await notifier.async_close()

        mock_session.close.assert_not_awaited()
        assert notifier._async_client is None

    async def test_context_manager_sets_flag(self):
        """Entering context manager sets _in_context_manager flag."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        async with notifier as n:
            assert n is notifier
            assert notifier._in_context_manager is True
        assert notifier._in_context_manager is False

    async def test_context_manager_closes_on_exit(self):
        """Exiting context manager calls async_close."""
        notifier = SlackNotifier(token="xoxb-test", channel="#test")
        with patch.object(
            notifier, "async_close", new_callable=AsyncMock
        ) as mock_close:
            async with notifier:
                pass
            mock_close.assert_awaited_once()

    async def test_send_message_closes_after_call(self):
        """One-shot async_send_message closes the client when done."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = AsyncMock()
        notifier._async_client = mock_client

        await notifier.async_send_message("hello")

        mock_client.chat_postMessage.assert_awaited_once()
        assert notifier._async_client is None
        assert notifier._async_ref_count == 0

    async def test_send_message_preserves_client_in_context_manager(self):
        """async_send_message reuses self._async_client inside context manager."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = AsyncMock()
        notifier._async_client = mock_client

        async with notifier:
            await notifier.async_send_message("hello")
            mock_client.chat_postMessage.assert_awaited_once()


# ===========================================================================
# send_message / send_error (sync)
# ===========================================================================


class TestSendMessageSync:
    """Verify synchronous Slack message posting."""

    def test_send_message_calls_chat_post_message(self):
        """send_message invokes chat_postMessage with correct kwargs."""
        notifier = SlackNotifier(
            token="xoxb-test",
            channel="#alerts",
            username="Bot",
            icon_emoji=":robot_face:",
        )
        mock_client = MagicMock()
        notifier._client = mock_client

        notifier.send_message("hello", blocks=[{"type": "section"}])

        mock_client.chat_postMessage.assert_called_once_with(
            channel="#alerts",
            username="Bot",
            icon_emoji=":robot_face:",
            text="hello",
            blocks=[{"type": "section"}],
        )

    def test_send_error_posts_formatted_blocks(self):
        """send_error sends Block Kit formatted error."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = MagicMock()
        notifier._client = mock_client

        try:
            raise ValueError("test boom")
        except ValueError as exc:
            notifier.send_error(exc, context=_make_lambda_context())

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#alerts"
        assert "blocks" in call_kwargs
        assert "ValueError: test boom" in call_kwargs["text"]

    def test_send_error_swallows_slack_failures(self):
        """Slack API errors are logged, not propagated."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = RuntimeError("Slack is down")
        notifier._client = mock_client

        try:
            raise ValueError("original error")
        except ValueError as exc:
            notifier.send_error(exc)


# ===========================================================================
# async_send_message / async_send_error
# ===========================================================================


class TestSendMessageAsync:
    """Verify asynchronous Slack message posting."""

    async def test_async_send_message(self):
        """async_send_message invokes async chat_postMessage."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = AsyncMock()
        notifier._async_client = mock_client

        await notifier.async_send_message("async hello")

        mock_client.chat_postMessage.assert_awaited_once_with(
            channel="#alerts",
            text="async hello",
        )

    async def test_async_send_error(self):
        """async_send_error sends Block Kit formatted error."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = AsyncMock()
        notifier._async_client = mock_client

        try:
            raise TypeError("async boom")
        except TypeError as exc:
            await notifier.async_send_error(exc)

        mock_client.chat_postMessage.assert_awaited_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert "TypeError: async boom" in call_kwargs["text"]

    async def test_async_send_error_swallows_slack_failures(self):
        """Async Slack API errors are logged, not propagated."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = RuntimeError("Slack is down")
        notifier._async_client = mock_client

        try:
            raise ValueError("original")
        except ValueError as exc:
            await notifier.async_send_error(exc)


# ===========================================================================
# error_handler decorator
# ===========================================================================


class TestErrorHandlerDecorator:
    """Verify the error_handler decorator catches, notifies, and re-raises."""

    def test_sync_decorator_re_raises(self):
        """Sync decorated function re-raises after notifying."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")

        with patch.object(notifier, "send_error") as mock_send:

            @notifier.error_handler
            def my_handler(event, context):
                raise RuntimeError("handler failed")

            with pytest.raises(RuntimeError, match="handler failed"):
                my_handler({"key": "val"}, _make_lambda_context())

            mock_send.assert_called_once()
            exc_arg = mock_send.call_args[0][0]
            assert isinstance(exc_arg, RuntimeError)

    def test_sync_decorator_passes_through_on_success(self):
        """Sync decorated function returns normally when no error."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")

        with patch.object(notifier, "send_error") as mock_send:

            @notifier.error_handler
            def my_handler(event, context):
                return "ok"

            result = my_handler({}, None)
            assert result == "ok"
            mock_send.assert_not_called()

    async def test_async_decorator_re_raises(self):
        """Async decorated function re-raises after notifying."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")

        with (
            patch.object(
                notifier, "async_send_error", new_callable=AsyncMock
            ) as mock_send,
        ):

            @notifier.error_handler
            async def my_handler(event, context):
                raise ValueError("async handler failed")

            with pytest.raises(ValueError, match="async handler failed"):
                await my_handler(EVENTBRIDGE_EVENT, _make_lambda_context())

            mock_send.assert_awaited_once()

    async def test_async_decorator_passes_through_on_success(self):
        """Async decorated function returns normally when no error."""
        notifier = SlackNotifier(token="xoxb-test", channel="#alerts")

        with (
            patch.object(
                notifier, "async_send_error", new_callable=AsyncMock
            ) as mock_send,
        ):

            @notifier.error_handler
            async def my_handler(event, context):
                return "async ok"

            result = await my_handler({}, None)
            assert result == "async ok"
            mock_send.assert_not_awaited()
