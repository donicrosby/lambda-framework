"""Tests for the async EventBridge publisher."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lambda_framework.eventbridge import EventBridgePublisher, EventBridgeRouter

BUS_NAME = "my-function-bus"
SOURCE = "webhook.github"

SAMPLE_EB_EVENT = {
    "version": "0",
    "id": "12345678-1234-1234-1234-123456789012",
    "detail-type": "vuln-sync",
    "source": "my-app",
    "account": "123456789012",
    "time": "2025-01-01T00:00:00Z",
    "region": "us-east-1",
    "resources": [],
    "detail": {"project": "my-project"},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    """Create an AsyncMock that behaves like an aioboto3 EventBridge client."""
    client = AsyncMock()
    client.put_events = AsyncMock(
        return_value={"FailedEntryCount": 0, "Entries": [{"EventId": "evt-1"}]}
    )
    return client


@pytest.fixture
def mock_session(mock_client):
    """Return an aioboto3.Session mock whose .client() yields an async context manager."""
    session = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.client.return_value = ctx
    return session


@pytest.fixture
def publisher(mock_session):
    """Build an EventBridgePublisher wired to the mock session."""
    return EventBridgePublisher(BUS_NAME, SOURCE, session=mock_session)


# ===========================================================================
# Constructor tests
# ===========================================================================


class TestInit:
    """Verify EventBridgePublisher constructor and session handling."""

    def test_stores_config(self):
        """Store event_bus_name and source from constructor args."""
        pub = EventBridgePublisher("bus", "src")
        assert pub._event_bus_name == "bus"
        assert pub._source == "src"

    def test_creates_default_session(self):
        """Create an aioboto3.Session when none is provided."""
        with patch("lambda_framework.eventbridge._aioboto3.Session") as mock_sess:
            EventBridgePublisher("bus", "src")
            mock_sess.assert_called_once()

    def test_accepts_custom_session(self, mock_session):
        """Use the caller-supplied session instead of creating a new one."""
        pub = EventBridgePublisher("bus", "src", session=mock_session)
        assert pub._session is mock_session


# ===========================================================================
# put_event tests
# ===========================================================================


class TestPutEvent:
    """Verify put_event builds a correct entry and delegates to put_events."""

    async def test_publishes_dict_detail(self, publisher, mock_client):
        """JSON-serialise a dict detail and populate all required entry fields."""
        detail = {"ref": "refs/heads/main", "commits": []}

        await publisher.put_event("push", detail)

        mock_client.put_events.assert_awaited_once()
        entries = mock_client.put_events.call_args.kwargs["Entries"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["Source"] == SOURCE
        assert entry["DetailType"] == "push"
        assert entry["Detail"] == json.dumps(detail)
        assert entry["EventBusName"] == BUS_NAME

    async def test_publishes_string_detail(self, publisher, mock_client):
        """Pass a pre-serialised string detail through unchanged."""
        raw = '{"already": "serialised"}'

        await publisher.put_event("custom", raw)

        entries = mock_client.put_events.call_args.kwargs["Entries"]
        assert entries[0]["Detail"] == raw

    async def test_includes_resources(self, publisher, mock_client):
        """Attach resource ARNs to the entry when provided."""
        resources = ["arn:aws:s3:::my-bucket"]

        await publisher.put_event("push", {"key": "val"}, resources=resources)

        entry = mock_client.put_events.call_args.kwargs["Entries"][0]
        assert entry["Resources"] == resources

    async def test_includes_trace_header(self, publisher, mock_client):
        """Attach an X-Ray TraceHeader to the entry when provided."""
        header = "Root=1-abc-def"

        await publisher.put_event("push", {"k": "v"}, trace_header=header)

        entry = mock_client.put_events.call_args.kwargs["Entries"][0]
        assert entry["TraceHeader"] == header

    async def test_returns_response(self, publisher, mock_client):
        """Return the raw PutEvents response to the caller."""
        expected = {"FailedEntryCount": 0, "Entries": [{"EventId": "e-1"}]}
        mock_client.put_events.return_value = expected

        result = await publisher.put_event("push", {"k": "v"})

        assert result == expected


# ===========================================================================
# put_events tests
# ===========================================================================


class TestPutEvents:
    """Verify put_events sends entries to EventBridge and handles failures."""

    async def test_fills_defaults(self, publisher, mock_client):
        """Set EventBusName and Source on entries that lack them."""
        entries = [
            {"DetailType": "a", "Detail": "{}"},
            {"DetailType": "b", "Detail": "{}"},
        ]

        await publisher.put_events(entries)

        for entry in mock_client.put_events.call_args.kwargs["Entries"]:
            assert entry["EventBusName"] == BUS_NAME
            assert entry["Source"] == SOURCE

    async def test_preserves_explicit_values(self, publisher, mock_client):
        """Do not overwrite Source or EventBusName when already set."""
        entries = [
            {
                "Source": "custom.source",
                "DetailType": "test",
                "Detail": "{}",
                "EventBusName": "other-bus",
            }
        ]

        await publisher.put_events(entries)

        entry = mock_client.put_events.call_args.kwargs["Entries"][0]
        assert entry["Source"] == "custom.source"
        assert entry["EventBusName"] == "other-bus"

    async def test_raises_on_failed_entries(self, publisher, mock_client):
        """Raise RuntimeError when FailedEntryCount is non-zero."""
        mock_client.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [
                {"EventId": "e-1"},
                {"ErrorCode": "InternalFailure", "ErrorMessage": "boom"},
            ],
        }

        with pytest.raises(RuntimeError, match="failed for 1 of 2"):
            await publisher.put_events(
                [
                    {"DetailType": "a", "Detail": "{}"},
                    {"DetailType": "b", "Detail": "{}"},
                ]
            )

    async def test_success_with_zero_failures(self, publisher, mock_client):
        """Return the full response when all entries succeed."""
        mock_client.put_events.return_value = {
            "FailedEntryCount": 0,
            "Entries": [{"EventId": "e-1"}, {"EventId": "e-2"}],
        }

        result = await publisher.put_events(
            [{"DetailType": "a", "Detail": "{}"}, {"DetailType": "b", "Detail": "{}"}]
        )

        assert result["FailedEntryCount"] == 0
        assert len(result["Entries"]) == 2


# ===========================================================================
# Async context manager tests
# ===========================================================================


class TestAsyncContextManager:
    """Verify async-with creates a reusable client and cleans up on exit."""

    async def test_creates_and_closes_client(self, publisher, mock_session):
        """Create the client on enter and close it on exit."""
        ctx = mock_session.client.return_value

        async with publisher:
            assert publisher._client is not None
            assert publisher._in_context_manager is True

        ctx.__aexit__.assert_awaited_once()
        assert publisher._client is None
        assert publisher._in_context_manager is False

    async def test_reuses_client_across_calls(
        self, publisher, mock_session, mock_client
    ):
        """Use the same client for multiple publishes inside async-with."""
        async with publisher:
            await publisher.put_event("a", {"k": "1"})
            await publisher.put_event("b", {"k": "2"})

        assert mock_client.put_events.await_count == 2
        mock_session.client.assert_called_once()


# ===========================================================================
# Lazy client creation (no context manager)
# ===========================================================================


class TestRefCountedLifecycle:
    """Verify ref-counted client lifecycle outside the context manager."""

    async def test_creates_and_closes_per_call(
        self, publisher, mock_session, mock_client
    ):
        """One-shot call creates the client and closes it when done."""
        assert publisher._client is None

        await publisher.put_event("push", {"k": "v"})

        assert publisher._client is None
        assert publisher._ref_count == 0
        mock_session.client.assert_called_once_with("events")
        ctx = mock_session.client.return_value
        ctx.__aexit__.assert_awaited_once()

    async def test_sequential_calls_recreate_client(
        self, publisher, mock_session, mock_client
    ):
        """Sequential calls each create and close their own client."""
        await publisher.put_event("a", {})
        await publisher.put_event("b", {})

        assert mock_session.client.call_count == 2
        assert mock_client.put_events.await_count == 2
        assert publisher._ref_count == 0

    async def test_concurrent_calls_share_single_client(
        self, publisher, mock_session, mock_client
    ):
        """Concurrent calls share a single client via ref counting."""

        async def yielding_put_events(**kwargs):
            await asyncio.sleep(0)
            return {"FailedEntryCount": 0, "Entries": [{"EventId": "evt-1"}]}

        mock_client.put_events.side_effect = yielding_put_events

        await asyncio.gather(
            publisher.put_event("a", {}),
            publisher.put_event("b", {}),
            publisher.put_event("c", {}),
        )

        mock_session.client.assert_called_once()
        assert mock_client.put_events.await_count == 3
        assert publisher._client is None
        assert publisher._ref_count == 0

    async def test_client_closed_after_put_events_failure(
        self, publisher, mock_session, mock_client
    ):
        """Client is closed even when put_events raises (ref count drops to 0)."""
        mock_client.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorCode": "InternalFailure", "ErrorMessage": "boom"}],
        }

        with pytest.raises(RuntimeError, match="failed for 1 of 1"):
            await publisher.put_events([{"DetailType": "a", "Detail": "{}"}])

        assert publisher._client is None
        assert publisher._ref_count == 0


class TestClose:
    """Verify the public close() method."""

    async def test_close_exits_client_context(self, publisher, mock_session):
        """close() exits the underlying aioboto3 client context manager."""
        ctx = mock_session.client.return_value
        publisher._client = "sentinel"
        publisher._client_ctx = ctx
        publisher._ref_count = 1

        await publisher.close()

        ctx.__aexit__.assert_awaited_once_with(None, None, None)
        assert publisher._client is None
        assert publisher._client_ctx is None
        assert publisher._ref_count == 0

    async def test_close_is_idempotent(self, publisher):
        """Calling close() when no client exists is a no-op."""
        await publisher.close()
        assert publisher._client is None


# ===========================================================================
# EventBridgeRouter tests
# ===========================================================================


class TestEventBridgeRouterInit:
    """Verify EventBridgeRouter constructor."""

    def test_empty_router(self):
        """Router starts with no handlers."""
        router = EventBridgeRouter()
        assert router._handlers == {}
        assert router._default_handler is None

    def test_default_handler(self):
        """default_handler is stored."""

        def fallback(event, context):
            return "fallback"

        router = EventBridgeRouter(default_handler=fallback)
        assert router._default_handler is fallback


class TestEventBridgeRouterOn:
    """Verify the on() decorator registers handlers."""

    def test_register_handler(self):
        """on() registers a handler for the given detail-type."""
        router = EventBridgeRouter()

        @router.on("vuln-sync")
        def handle_vuln(event, context):
            return "ok"

        assert router._handlers["vuln-sync"] is handle_vuln

    def test_register_multiple_handlers(self):
        """Multiple detail-types can be registered."""
        router = EventBridgeRouter()

        @router.on("vuln-sync")
        def handle_vuln(event, context):
            pass

        @router.on("codeowner-to-jira-team")
        def handle_codeowner(event, context):
            pass

        assert "vuln-sync" in router._handlers
        assert "codeowner-to-jira-team" in router._handlers

    def test_duplicate_detail_type_raises(self):
        """ValueError when registering duplicate detail-type."""
        router = EventBridgeRouter()

        @router.on("vuln-sync")
        def first(event, context):
            pass

        with pytest.raises(ValueError, match="already registered for detail-type"):

            @router.on("vuln-sync")
            def second(event, context):
                pass

    def test_returns_original_function(self):
        """Decorator returns the function unchanged."""
        router = EventBridgeRouter()

        def my_handler(event, context):
            return "result"

        decorated = router.on("vuln-sync")(my_handler)
        assert decorated is my_handler


class TestEventBridgeRouterDispatch:
    """Verify dispatch routes events to handlers."""

    def test_dispatch_to_registered_handler(self):
        """Routes to the correct handler for the detail-type."""
        router = EventBridgeRouter()
        handler = MagicMock(return_value="done")

        @router.on("vuln-sync")
        def handle_vuln(event, context):
            return handler(event, context)

        context = MagicMock()
        result = router.dispatch(SAMPLE_EB_EVENT, context)

        handler.assert_called_once_with(SAMPLE_EB_EVENT, context)
        assert result == "done"

    def test_dispatch_async_handler(self):
        """Async handler is executed via asyncio.run()."""
        router = EventBridgeRouter()
        received = []

        @router.on("vuln-sync")
        async def handle_vuln(event, context):
            received.append((event, context))
            return "async-ok"

        context = MagicMock()
        result = router.dispatch(SAMPLE_EB_EVENT, context)

        assert received == [(SAMPLE_EB_EVENT, context)]
        assert result == "async-ok"

    def test_dispatch_unknown_detail_type_returns_none(self, caplog):
        """Logs warning and returns None when no handler matches."""
        router = EventBridgeRouter()
        event = {**SAMPLE_EB_EVENT, "detail-type": "unknown-type"}
        context = MagicMock()

        result = router.dispatch(event, context)

        assert result is None
        assert "No handler registered for detail-type" in caplog.text

    def test_dispatch_to_default_handler(self):
        """Falls back to default when no match."""
        default = MagicMock(return_value="default-result")
        router = EventBridgeRouter(default_handler=default)
        event = {**SAMPLE_EB_EVENT, "detail-type": "unknown-type"}
        context = MagicMock()

        result = router.dispatch(event, context)

        default.assert_called_once_with(event, context)
        assert result == "default-result"

    def test_dispatch_passes_event_and_context(self):
        """Handler receives both event and context."""
        router = EventBridgeRouter()
        received_event = None
        received_context = None

        @router.on("vuln-sync")
        def handle_vuln(event, context):
            nonlocal received_event, received_context
            received_event = event
            received_context = context
            return "ok"

        context = MagicMock()
        router.dispatch(SAMPLE_EB_EVENT, context)

        assert received_event == SAMPLE_EB_EVENT
        assert received_context is context

    def test_dispatch_multiple_handlers_routes_correctly(self):
        """Register 3 handlers; each routes to the correct one."""
        router = EventBridgeRouter()

        @router.on("vuln-sync")
        def handle_vuln(event, context):
            return "vuln"

        @router.on("codeowner-to-jira-team")
        def handle_codeowner(event, context):
            return "codeowner"

        @router.on("other-type")
        def handle_other(event, context):
            return "other"

        context = MagicMock()

        r1 = router.dispatch(SAMPLE_EB_EVENT, context)
        r2 = router.dispatch(
            {**SAMPLE_EB_EVENT, "detail-type": "codeowner-to-jira-team"}, context
        )
        r3 = router.dispatch({**SAMPLE_EB_EVENT, "detail-type": "other-type"}, context)

        assert r1 == "vuln"
        assert r2 == "codeowner"
        assert r3 == "other"
