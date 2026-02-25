"""Tests for the async EventBridge publisher."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lambda_framework.eventbridge import EventBridgePublisher

BUS_NAME = "my-function-bus"
SOURCE = "webhook.github"


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
        with patch("lambda_framework.eventbridge.aioboto3.Session") as mock_sess:
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
            assert publisher._owns_client is True

        ctx.__aexit__.assert_awaited_once()
        assert publisher._client is None
        assert publisher._owns_client is False

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


class TestLazyClientCreation:
    """Verify a client is created lazily on first call and reused thereafter."""

    async def test_creates_client_on_first_call(
        self, publisher, mock_session, mock_client
    ):
        """Create the client the first time put_event is called."""
        assert publisher._client is None

        await publisher.put_event("push", {"k": "v"})

        assert publisher._client is mock_client
        mock_session.client.assert_called_once_with("events")

    async def test_reuses_client_on_second_call(
        self, publisher, mock_session, mock_client
    ):
        """Reuse the same client for a second put_event call."""
        await publisher.put_event("a", {})
        await publisher.put_event("b", {})

        mock_session.client.assert_called_once()
        assert mock_client.put_events.await_count == 2
