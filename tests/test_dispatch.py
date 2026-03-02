"""Tests for the Lambda event dispatcher."""

import asyncio
from unittest.mock import MagicMock

import pytest

from lambda_framework.dispatch import (
    _ensure_event_loop,
    _is_api_gateway_event,
    _is_authorizer_event,
    _is_eventbridge_event,
    _is_sqs_event,
    create_dispatcher,
)

# ---------------------------------------------------------------------------
# Sample events
# ---------------------------------------------------------------------------

API_GATEWAY_V1_EVENT = {
    "httpMethod": "POST",
    "path": "/webhook",
    "requestContext": {
        "resourceId": "abc123",
        "stage": "prod",
        "httpMethod": "POST",
    },
    "body": '{"action": "push"}',
    "headers": {"Content-Type": "application/json"},
}

API_GATEWAY_V2_EVENT = {
    "requestContext": {
        "http": {
            "method": "POST",
            "path": "/webhook",
        },
        "stage": "$default",
    },
    "body": '{"action": "push"}',
}

EVENTBRIDGE_EVENT = {
    "version": "0",
    "id": "12345678-1234-1234-1234-123456789012",
    "detail-type": "push",
    "source": "webhook.github",
    "account": "123456789012",
    "time": "2025-01-01T00:00:00Z",
    "region": "us-east-1",
    "resources": [],
    "detail": {"ref": "refs/heads/main", "commits": []},
}

SQS_EVENT = {
    "Records": [
        {
            "messageId": "msg-001",
            "receiptHandle": "handle",
            "body": '{"key": "value"}',
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-1:123456789012:my-queue",
        }
    ]
}

REQUEST_AUTHORIZER_EVENT = {
    "type": "REQUEST",
    "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abc123/prod/GET/resource",
    "resource": "/resource",
    "path": "/resource",
    "httpMethod": "GET",
    "headers": {"Authorization": "Bearer token123"},
    "queryStringParameters": None,
    "pathParameters": None,
    "stageVariables": None,
    "requestContext": {
        "resourceId": "abc123",
        "apiId": "api123",
        "resourcePath": "/resource",
        "httpMethod": "GET",
        "stage": "prod",
    },
}

TOKEN_AUTHORIZER_EVENT = {
    "type": "TOKEN",
    "authorizationToken": "Bearer token123",
    "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abc123/prod/GET/resource",
}


# ===========================================================================
# Event detection tests
# ===========================================================================


class TestIsApiGatewayEvent:
    """Verify _is_api_gateway_event detects v1/v2 proxy events and rejects others."""

    def test_v1_rest_api(self):
        """Accept a REST API (v1) proxy event with httpMethod at top level."""
        assert _is_api_gateway_event(API_GATEWAY_V1_EVENT) is True

    def test_v2_http_api(self):
        """Accept an HTTP API (v2) event with http key inside requestContext."""
        assert _is_api_gateway_event(API_GATEWAY_V2_EVENT) is True

    def test_rejects_eventbridge(self):
        """Reject an EventBridge event that lacks requestContext."""
        assert _is_api_gateway_event(EVENTBRIDGE_EVENT) is False

    def test_rejects_sqs(self):
        """Reject an SQS event that lacks requestContext."""
        assert _is_api_gateway_event(SQS_EVENT) is False

    def test_rejects_empty(self):
        """Reject an empty dict."""
        assert _is_api_gateway_event({}) is False


class TestIsEventBridgeEvent:
    """Verify _is_eventbridge_event requires source, detail-type, and detail."""

    def test_standard_event(self):
        """Accept a well-formed EventBridge event."""
        assert _is_eventbridge_event(EVENTBRIDGE_EVENT) is True

    def test_rejects_missing_source(self):
        """Reject when the source key is absent."""
        event = {k: v for k, v in EVENTBRIDGE_EVENT.items() if k != "source"}
        assert _is_eventbridge_event(event) is False

    def test_rejects_missing_detail_type(self):
        """Reject when the detail-type key is absent."""
        event = {k: v for k, v in EVENTBRIDGE_EVENT.items() if k != "detail-type"}
        assert _is_eventbridge_event(event) is False

    def test_rejects_missing_detail(self):
        """Reject when the detail key is absent."""
        event = {k: v for k, v in EVENTBRIDGE_EVENT.items() if k != "detail"}
        assert _is_eventbridge_event(event) is False

    def test_rejects_api_gateway(self):
        """Reject an API Gateway v1 event."""
        assert _is_eventbridge_event(API_GATEWAY_V1_EVENT) is False

    def test_rejects_empty(self):
        """Reject an empty dict."""
        assert _is_eventbridge_event({}) is False


class TestIsSqsEvent:
    """Verify _is_sqs_event checks for Records with aws:sqs eventSource."""

    def test_standard_event(self):
        """Accept a well-formed SQS event."""
        assert _is_sqs_event(SQS_EVENT) is True

    def test_rejects_empty_records(self):
        """Reject when Records is an empty list."""
        assert _is_sqs_event({"Records": []}) is False

    def test_rejects_non_sqs_records(self):
        """Reject when the first record comes from SNS, not SQS."""
        event = {"Records": [{"eventSource": "aws:sns", "Sns": {"Message": "hello"}}]}
        assert _is_sqs_event(event) is False

    def test_rejects_missing_records(self):
        """Reject when the Records key is absent."""
        assert _is_sqs_event({"foo": "bar"}) is False

    def test_rejects_non_list_records(self):
        """Reject when Records is not a list."""
        assert _is_sqs_event({"Records": "not-a-list"}) is False

    def test_rejects_empty(self):
        """Reject an empty dict."""
        assert _is_sqs_event({}) is False


class TestIsAuthorizerEvent:
    """Verify _is_authorizer_event detects REQUEST and TOKEN authorizer events."""

    def test_request_authorizer(self):
        """Accept REQUEST authorizer event."""
        assert _is_authorizer_event(REQUEST_AUTHORIZER_EVENT) is True

    def test_token_authorizer(self):
        """Accept TOKEN authorizer event."""
        assert _is_authorizer_event(TOKEN_AUTHORIZER_EVENT) is True

    def test_rejects_api_gateway(self):
        """Reject API Gateway v1 event."""
        assert _is_authorizer_event(API_GATEWAY_V1_EVENT) is False

    def test_rejects_eventbridge(self):
        """Reject EventBridge event."""
        assert _is_authorizer_event(EVENTBRIDGE_EVENT) is False

    def test_rejects_empty(self):
        """Reject empty dict."""
        assert _is_authorizer_event({}) is False


# ===========================================================================
# Dispatcher routing tests
# ===========================================================================


class TestCreateDispatcher:
    """Verify the dispatcher routes each event type to the correct handler."""

    def test_routes_api_gateway_v1(self):
        """Route a REST API v1 event to the http_handler."""
        http = MagicMock(return_value={"statusCode": 200})
        handler = create_dispatcher(http_handler=http)

        result = handler(API_GATEWAY_V1_EVENT, None)

        http.assert_called_once_with(API_GATEWAY_V1_EVENT, None)
        assert result == {"statusCode": 200}

    def test_routes_api_gateway_v2(self):
        """Route an HTTP API v2 event to the http_handler."""
        http = MagicMock(return_value={"statusCode": 200})
        handler = create_dispatcher(http_handler=http)

        result = handler(API_GATEWAY_V2_EVENT, None)

        http.assert_called_once_with(API_GATEWAY_V2_EVENT, None)
        assert result == {"statusCode": 200}

    def test_routes_eventbridge(self):
        """Route an EventBridge event to the eventbridge_handler."""
        eb = MagicMock(return_value="processed")
        handler = create_dispatcher(eventbridge_handler=eb)

        result = handler(EVENTBRIDGE_EVENT, None)

        eb.assert_called_once_with(EVENTBRIDGE_EVENT, None)
        assert result == "processed"

    def test_routes_sqs(self):
        """Route an SQS event to the sqs_handler."""
        sqs = MagicMock(return_value={"batchItemFailures": []})
        handler = create_dispatcher(sqs_handler=sqs)

        result = handler(SQS_EVENT, None)

        sqs.assert_called_once_with(SQS_EVENT, None)
        assert result == {"batchItemFailures": []}

    def test_raises_for_unknown_event(self):
        """Raise ValueError for an event that matches no known type."""
        handler = create_dispatcher()

        with pytest.raises(ValueError, match="Unrecognised event type"):
            handler({"unknown": "event"}, None)

    def test_raises_when_http_handler_missing(self):
        """Raise ValueError when an API Gateway event arrives with no http_handler."""
        handler = create_dispatcher()

        with pytest.raises(ValueError, match="no http_handler"):
            handler(API_GATEWAY_V1_EVENT, None)

    def test_raises_when_eventbridge_handler_missing(self):
        """Raise ValueError when an EventBridge event arrives with no handler."""
        handler = create_dispatcher()

        with pytest.raises(ValueError, match="no eventbridge_handler"):
            handler(EVENTBRIDGE_EVENT, None)

    def test_raises_when_sqs_handler_missing(self):
        """Raise ValueError when an SQS event arrives with no sqs_handler."""
        handler = create_dispatcher()

        with pytest.raises(ValueError, match="no sqs_handler"):
            handler(SQS_EVENT, None)

    def test_all_handlers_registered(self):
        """Each event type reaches the correct handler when all are registered."""
        http = MagicMock(return_value="http")
        eb = MagicMock(return_value="eb")
        sqs = MagicMock(return_value="sqs")
        handler = create_dispatcher(
            http_handler=http,
            eventbridge_handler=eb,
            sqs_handler=sqs,
        )

        assert handler(API_GATEWAY_V1_EVENT, None) == "http"
        assert handler(EVENTBRIDGE_EVENT, None) == "eb"
        assert handler(SQS_EVENT, None) == "sqs"

        http.assert_called_once()
        eb.assert_called_once()
        sqs.assert_called_once()


class TestCreateDispatcherAuthorizer:
    """Verify the dispatcher routes authorizer events to authorizer_handler."""

    def test_routes_request_authorizer(self):
        """Route REQUEST authorizer event to authorizer_handler."""
        auth = MagicMock(return_value={"principalId": "user123", "policyDocument": {}})
        handler = create_dispatcher(authorizer_handler=auth)

        result = handler(REQUEST_AUTHORIZER_EVENT, None)

        auth.assert_called_once_with(REQUEST_AUTHORIZER_EVENT, None)
        assert result == {"principalId": "user123", "policyDocument": {}}

    def test_routes_token_authorizer(self):
        """Route TOKEN authorizer event to authorizer_handler."""
        auth = MagicMock(return_value={"principalId": "user456", "policyDocument": {}})
        handler = create_dispatcher(authorizer_handler=auth)

        result = handler(TOKEN_AUTHORIZER_EVENT, None)

        auth.assert_called_once_with(TOKEN_AUTHORIZER_EVENT, None)
        assert result == {"principalId": "user456", "policyDocument": {}}

    def test_raises_when_authorizer_handler_missing(self):
        """Raise ValueError when authorizer event arrives with no handler."""
        handler = create_dispatcher()

        with pytest.raises(ValueError, match="no authorizer_handler"):
            handler(REQUEST_AUTHORIZER_EVENT, None)

    def test_request_authorizer_not_misrouted_to_http(self):
        """REQUEST with requestContext is NOT routed to http_handler."""
        http = MagicMock(return_value={"statusCode": 200})
        auth = MagicMock(return_value={"principalId": "ok", "policyDocument": {}})
        handler = create_dispatcher(http_handler=http, authorizer_handler=auth)

        result = handler(REQUEST_AUTHORIZER_EVENT, None)

        auth.assert_called_once()
        http.assert_not_called()
        assert result == {"principalId": "ok", "policyDocument": {}}

    def test_async_authorizer_handler(self):
        """Async authorizer handler works via asyncio.run."""

        async def async_auth(event, context):
            return {"principalId": event["type"], "policyDocument": {}}

        handler = create_dispatcher(authorizer_handler=async_auth)
        result = handler(REQUEST_AUTHORIZER_EVENT, None)

        assert result == {"principalId": "REQUEST", "policyDocument": {}}

    def test_authorizer_with_error_notifier(self):
        """error_notifier fires on authorizer errors."""
        notifier = MagicMock()
        failing_auth = MagicMock(side_effect=RuntimeError("auth boom"))
        ctx = MagicMock()

        handler = create_dispatcher(
            authorizer_handler=failing_auth,
            error_notifier=notifier,
        )

        with pytest.raises(RuntimeError, match="auth boom"):
            handler(REQUEST_AUTHORIZER_EVENT, ctx)

        notifier.send_error.assert_called_once()
        call_kwargs = notifier.send_error.call_args
        assert isinstance(call_kwargs[0][0], RuntimeError)
        assert call_kwargs[1]["context"] is ctx
        assert call_kwargs[1]["event"] is REQUEST_AUTHORIZER_EVENT

    def test_all_handlers_including_authorizer(self):
        """All 4 handlers registered, each routes correctly."""
        http = MagicMock(return_value="http")
        eb = MagicMock(return_value="eb")
        sqs = MagicMock(return_value="sqs")
        auth = MagicMock(return_value="auth")
        handler = create_dispatcher(
            http_handler=http,
            eventbridge_handler=eb,
            sqs_handler=sqs,
            authorizer_handler=auth,
        )

        assert handler(API_GATEWAY_V1_EVENT, None) == "http"
        assert handler(EVENTBRIDGE_EVENT, None) == "eb"
        assert handler(SQS_EVENT, None) == "sqs"
        assert handler(REQUEST_AUTHORIZER_EVENT, None) == "auth"

        http.assert_called_once()
        eb.assert_called_once()
        sqs.assert_called_once()
        auth.assert_called_once()

    def test_passes_context_through(self):
        """Forward the Lambda context object to the sub-handler unchanged."""
        http = MagicMock(return_value="ok")
        handler = create_dispatcher(http_handler=http)
        fake_context = MagicMock()

        handler(API_GATEWAY_V1_EVENT, fake_context)

        http.assert_called_once_with(API_GATEWAY_V1_EVENT, fake_context)


# ===========================================================================
# Async handler bridging tests
# ===========================================================================


class TestAsyncHandlerBridging:
    """Verify async handlers are bridged to sync via asyncio.run for the Lambda runtime."""

    def test_async_eventbridge_handler(self):
        """Run an async eventbridge_handler through asyncio.run transparently."""

        async def async_eb(event, context):
            return {"processed": event["detail-type"]}

        handler = create_dispatcher(eventbridge_handler=async_eb)
        result = handler(EVENTBRIDGE_EVENT, None)

        assert result == {"processed": "push"}

    def test_async_sqs_handler(self):
        """Run an async sqs_handler through asyncio.run transparently."""

        async def async_sqs(event, context):
            return {"batchItemFailures": [], "count": len(event["Records"])}

        handler = create_dispatcher(sqs_handler=async_sqs)
        result = handler(SQS_EVENT, None)

        assert result == {"batchItemFailures": [], "count": 1}

    def test_sync_eventbridge_handler_still_works(self):
        """A plain sync handler is called without asyncio.run."""

        def sync_eb(event, context):
            return "sync-result"

        handler = create_dispatcher(eventbridge_handler=sync_eb)
        result = handler(EVENTBRIDGE_EVENT, None)

        assert result == "sync-result"

    def test_http_handler_called_directly_without_invoke_bridge(self):
        """HTTP path should not go through _invoke (Mangum handles its own async)."""
        http = MagicMock(return_value="direct")
        handler = create_dispatcher(http_handler=http)

        result = handler(API_GATEWAY_V1_EVENT, None)

        assert result == "direct"
        http.assert_called_once()


# ===========================================================================
# error_notifier integration tests
# ===========================================================================


class TestErrorNotifier:
    """Verify the error_notifier parameter in create_dispatcher."""

    def test_notifier_called_on_handler_error(self):
        """When a handler raises, error_notifier.send_error is invoked."""
        notifier = MagicMock()
        failing_eb = MagicMock(side_effect=RuntimeError("handler boom"))
        ctx = MagicMock()

        handler = create_dispatcher(
            eventbridge_handler=failing_eb,
            error_notifier=notifier,
        )

        with pytest.raises(RuntimeError, match="handler boom"):
            handler(EVENTBRIDGE_EVENT, ctx)

        notifier.send_error.assert_called_once()
        call_kwargs = notifier.send_error.call_args
        assert isinstance(call_kwargs[0][0], RuntimeError)
        assert call_kwargs[1]["context"] is ctx
        assert call_kwargs[1]["event"] is EVENTBRIDGE_EVENT

    def test_original_exception_still_raised(self):
        """The original exception propagates even when a notifier is set."""
        notifier = MagicMock()
        handler = create_dispatcher(error_notifier=notifier)

        with pytest.raises(ValueError, match="Unrecognised event type"):
            handler({"unknown": "event"}, None)

    def test_notifier_not_called_on_success(self):
        """No notification when the handler succeeds."""
        notifier = MagicMock()
        http = MagicMock(return_value={"statusCode": 200})
        handler = create_dispatcher(http_handler=http, error_notifier=notifier)

        result = handler(API_GATEWAY_V1_EVENT, None)

        assert result == {"statusCode": 200}
        notifier.send_error.assert_not_called()

    def test_notifier_failure_does_not_mask_original(self):
        """If send_error itself raises, the original exception still propagates."""
        notifier = MagicMock()
        notifier.send_error.side_effect = ConnectionError("Slack unreachable")
        failing_sqs = MagicMock(side_effect=ValueError("sqs fail"))

        handler = create_dispatcher(
            sqs_handler=failing_sqs,
            error_notifier=notifier,
        )

        with pytest.raises(ValueError, match="sqs fail"):
            handler(SQS_EVENT, None)

    def test_notifier_with_missing_handler_error(self):
        """Notifier fires on ValueError for missing handler registration."""
        notifier = MagicMock()
        handler = create_dispatcher(error_notifier=notifier)

        with pytest.raises(ValueError, match="no http_handler"):
            handler(API_GATEWAY_V1_EVENT, None)

        notifier.send_error.assert_called_once()

    def test_no_notifier_default(self):
        """Without error_notifier, errors propagate as before."""
        handler = create_dispatcher()

        with pytest.raises(ValueError, match="Unrecognised event type"):
            handler({"nope": True}, None)


# ===========================================================================
# _ensure_event_loop tests
# ===========================================================================


class TestEnsureEventLoop:
    """Verify _ensure_event_loop creates a loop when none exists (Python 3.10+)."""

    def test_creates_loop_when_none_set(self):
        """A new loop is created and set when the thread has no current loop."""
        asyncio.set_event_loop(None)
        _ensure_event_loop()
        loop = asyncio.get_event_loop()
        assert loop is not None
        assert not loop.is_closed()
        loop.close()

    def test_preserves_existing_loop(self):
        """An already-set loop is left untouched."""
        existing = asyncio.new_event_loop()
        asyncio.set_event_loop(existing)
        try:
            _ensure_event_loop()
            assert asyncio.get_event_loop() is existing
        finally:
            existing.close()

    def test_http_dispatch_works_without_preexisting_loop(self):
        """The dispatcher can invoke http_handler even with no event loop set."""
        asyncio.set_event_loop(None)
        http = MagicMock(return_value={"statusCode": 200})
        handler = create_dispatcher(http_handler=http)

        result = handler(API_GATEWAY_V1_EVENT, None)

        assert result == {"statusCode": 200}
        http.assert_called_once()
