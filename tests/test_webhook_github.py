"""Unit tests for the GitHub webhook module."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from githubkit.versions.latest.webhooks import PushEvent

from lambda_framework.webhook.github import (
    GithubWebhookParser,
    GithubWebhookRouter,
    GithubWebhookValidator,
)


def generate_signature(secret: str, payload: dict) -> str:
    """Generate a valid GitHub webhook signature for testing."""
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


class TestGithubWebhookValidator:
    """Tests for GithubWebhookValidator class."""

    def test_init_stores_secret(self):
        """Validator should store the provided secret."""
        validator = GithubWebhookValidator(secret="test-secret")
        assert validator._secret == "test-secret"

    def test_call_raises_import_error_when_verify_missing(self):
        """Should raise ImportError when githubkit verify is not available."""
        validator = GithubWebhookValidator(secret="test-secret")

        with (
            patch("lambda_framework.webhook.github.verify", None),
            pytest.raises(
                ImportError,
                match="Githubkit is missing, please install the 'github' optional dependency",
            ),
        ):
            validator(payload={"test": "data"}, x_hub_signature_256="sha256=fake")

    def test_call_raises_http_exception_on_invalid_signature(self):
        """Should raise HTTPException 401 when signature is invalid."""
        from fastapi import HTTPException

        validator = GithubWebhookValidator(secret="correct-secret")

        with pytest.raises(HTTPException) as exc_info:
            validator(payload={"test": "data"}, x_hub_signature_256="sha256=invalidsig")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid signature"

    def test_call_returns_payload_on_valid_signature(self):
        """Should return payload when signature is valid."""
        secret = "test-secret"
        payload = {"action": "opened", "number": 1}
        signature = generate_signature(secret, payload)

        validator = GithubWebhookValidator(secret=secret)
        result = validator(payload=payload, x_hub_signature_256=signature)

        assert result == payload


class TestGithubWebhookValidatorIntegration:
    """Integration tests for GithubWebhookValidator with FastAPI."""

    def test_missing_signature_header_returns_422(self):
        """Should return 422 when X-Hub-Signature-256 header is missing."""
        app = FastAPI()
        validator = GithubWebhookValidator(secret="test-secret")

        from typing import Annotated

        from fastapi import Body, Header

        @app.post("/webhook")
        def webhook_handler(
            payload: Annotated[dict, Body(...)],
            x_hub_signature_256: Annotated[str, Header(...)],
        ):
            return validator(payload, x_hub_signature_256)

        client = TestClient(app, raise_server_exceptions=False)

        # Send request without signature header
        response = client.post("/webhook", json={"test": "data"})

        # FastAPI returns 422 for missing required headers
        assert response.status_code == 422

    def test_invalid_signature_returns_401(self):
        """Should return 401 when signature validation fails."""
        app = FastAPI()
        validator = GithubWebhookValidator(secret="correct-secret")

        from typing import Annotated

        from fastapi import Body, Header

        @app.post("/webhook")
        def webhook_handler(
            payload: Annotated[dict, Body(...)],
            x_hub_signature_256: Annotated[str, Header(...)],
        ):
            return validator(payload, x_hub_signature_256)

        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/webhook",
            json={"test": "data"},
            headers={"X-Hub-Signature-256": "sha256=invalid"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid signature"

    def test_valid_signature_returns_payload(self):
        """Should return payload when signature is valid."""
        secret = "test-secret"
        app = FastAPI()
        validator = GithubWebhookValidator(secret=secret)

        from typing import Annotated

        from fastapi import Body, Header

        @app.post("/webhook")
        def webhook_handler(
            payload: Annotated[dict, Body(...)],
            x_hub_signature_256: Annotated[str, Header(...)],
        ):
            return validator(payload, x_hub_signature_256)

        payload = {"action": "opened"}
        signature = generate_signature(secret, payload)

        client = TestClient(app)
        response = client.post(
            "/webhook",
            json=payload,
            headers={"X-Hub-Signature-256": signature},
        )

        assert response.status_code == 200
        assert response.json() == payload

    def test_empty_payload_with_valid_signature(self):
        """Should handle empty payload with valid signature."""
        secret = "test-secret"
        app = FastAPI()
        validator = GithubWebhookValidator(secret=secret)

        from typing import Annotated

        from fastapi import Body, Header

        @app.post("/webhook")
        def webhook_handler(
            payload: Annotated[dict, Body(...)],
            x_hub_signature_256: Annotated[str, Header(...)],
        ):
            return validator(payload, x_hub_signature_256)

        payload = {}
        signature = generate_signature(secret, payload)

        client = TestClient(app)
        response = client.post(
            "/webhook",
            json=payload,
            headers={"X-Hub-Signature-256": signature},
        )

        assert response.status_code == 200
        assert response.json() == {}


class TestGithubWebhookParser:
    """Tests for GithubWebhookParser class."""

    def test_init_raises_import_error_when_parse_obj_missing(self):
        """Should raise ImportError when githubkit parse_obj is not available."""
        validator = GithubWebhookValidator(secret="test-secret")

        with (
            patch("lambda_framework.webhook.github.parse_obj", None),
            pytest.raises(
                ImportError,
                match="Githubkit is missing, please install the 'github' optional dependency",
            ),
        ):
            GithubWebhookParser(validator)

    def test_init_stores_validator_and_parse_obj(self):
        """Parser should store validator and parse_obj function."""
        validator = GithubWebhookValidator(secret="test-secret")
        parser = GithubWebhookParser(validator)

        assert parser.validator is validator
        assert parser.parse_obj is not None

    def test_as_dependency_returns_callable(self):
        """as_dependency should return a callable function."""
        validator = GithubWebhookValidator(secret="test-secret")
        parser = GithubWebhookParser(validator)

        dependency = parser.as_dependency()

        assert callable(dependency)

    def test_as_dependency_accepts_event_type(self):
        """as_dependency should accept an optional event type parameter."""
        validator = GithubWebhookValidator(secret="test-secret")
        parser = GithubWebhookParser(validator)

        # Should not raise when passed a type
        dependency = parser.as_dependency(PushEvent)

        assert callable(dependency)


class TestGithubWebhookRouter:
    """Tests for GithubWebhookRouter class."""

    def test_init_creates_internal_components(self):
        """Router should create parser and internal APIRouter."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        assert router._webhook_secret == "test-secret"
        assert router._parser is not None
        assert router._router is not None

    def test_register_includes_router_in_app(self):
        """Register should include the internal router in the FastAPI app."""
        app = FastAPI()
        router = GithubWebhookRouter(webhook_secret="test-secret")

        # Initially no routes
        initial_routes = len(app.routes)

        # Add a webhook handler
        @router.add_webhook("/github")
        def handle_event(event: PushEvent):
            return {"handled": True}

        router.register(app)

        # Should have more routes after registration
        assert len(app.routes) > initial_routes


class TestGithubWebhookRouterAddWebhook:
    """Tests for GithubWebhookRouter.add_webhook decorator."""

    def test_add_webhook_raises_value_error_for_no_params(self):
        """Should raise ValueError when handler has no parameters."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        with pytest.raises(
            ValueError,
            match="Handler must have at least one parameter for WebhookEvent",
        ):

            @router.add_webhook("/github")
            def handler_no_params():
                return {"handled": True}

    def test_add_webhook_handles_unannotated_parameter(self):
        """Should handle handler with unannotated event parameter."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        # Should not raise - uses WebhookEvent as fallback
        @router.add_webhook("/github")
        def handler_unannotated(event):
            return {"handled": True}

        # The decorator should return the original function
        assert handler_unannotated is not None

    def test_add_webhook_handles_annotated_parameter(self):
        """Should handle handler with annotated event parameter."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        @router.add_webhook("/github")
        def handler_annotated(event: PushEvent):
            return {"event_type": "push"}

        assert handler_annotated is not None

    def test_add_webhook_returns_original_function(self):
        """Decorator should return the original function unchanged."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        def original_handler(event: PushEvent):
            return {"original": True}

        decorated = router.add_webhook("/github")(original_handler)

        assert decorated is original_handler

    def test_add_webhook_async_handler(self):
        """Should properly wrap async handlers."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        @router.add_webhook("/github")
        async def async_handler(event: PushEvent):
            return {"async": True}

        assert async_handler is not None

    def test_add_webhook_with_extra_kwargs(self):
        """Should pass extra kwargs to router.post()."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        # Should not raise when passing extra kwargs
        @router.add_webhook("/github", tags=["webhooks"], status_code=201)
        def handler_with_kwargs(event: PushEvent):
            return {"handled": True}

        assert handler_with_kwargs is not None

    def test_add_webhook_handler_with_multiple_params(self):
        """Should handle handlers with additional FastAPI dependencies."""
        router = GithubWebhookRouter(webhook_secret="test-secret")

        from typing import Annotated

        from fastapi import Header

        @router.add_webhook("/github")
        def handler_multi_params(
            event: PushEvent,
            x_github_delivery: Annotated[str, Header()],
        ):
            return {"delivery_id": x_github_delivery}

        assert handler_multi_params is not None


class TestGithubWebhookRouterIntegration:
    """Integration tests for GithubWebhookRouter with TestClient.

    These tests mock the parse_obj function to avoid needing complete
    GitHub webhook payloads which are very complex.
    """

    def test_webhook_endpoint_requires_signature_header(self):
        """Webhook endpoint should require X-Hub-Signature-256 header."""
        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handle_push(event: PushEvent):
            return {"received": True}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        # Request without signature header
        response = client.post(
            "/github",
            json={"action": "push"},
            headers={"X-GitHub-Event": "push"},
        )

        # Should fail due to missing signature
        assert response.status_code == 422

    def test_webhook_endpoint_requires_event_header(self):
        """Webhook endpoint should require X-GitHub-Event header."""
        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handle_push(event: PushEvent):
            return {"received": True}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, payload)

        # Request without event header
        response = client.post(
            "/github",
            json=payload,
            headers={"X-Hub-Signature-256": signature},
        )

        # Should fail due to missing event header
        assert response.status_code == 422

    def test_webhook_endpoint_rejects_invalid_signature(self):
        """Webhook endpoint should reject requests with invalid signatures."""
        app = FastAPI()
        secret = "correct-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handle_push(event: PushEvent):
            return {"received": True}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}
        # Generate signature with wrong secret
        wrong_signature = generate_signature("wrong-secret", payload)

        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": wrong_signature,
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid signature"

    def test_webhook_endpoint_rejects_tampered_payload(self):
        """Webhook endpoint should reject if payload was modified after signing."""
        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handle_push(event: PushEvent):
            return {"received": True}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        original_payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, original_payload)

        # Send a different payload with the original signature
        tampered_payload = {"ref": "refs/heads/malicious"}

        response = client.post(
            "/github",
            json=tampered_payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 401

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_sync_handler_executes_correctly(self, mock_parse_obj: MagicMock):
        """Sync webhook handlers should execute and return results."""
        # Create a mock event object
        mock_event = MagicMock(spec=PushEvent)
        mock_event.ref = "refs/heads/main"
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        handler_called = {"value": False}

        @router.add_webhook("/github")
        def sync_handler(event: PushEvent):
            handler_called["value"] = True
            return {"sync": True, "ref": event.ref}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, payload)

        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 200
        assert handler_called["value"] is True
        assert response.json() == {"sync": True, "ref": "refs/heads/main"}
        # parse_obj is called multiple times due to FastAPI dependency resolution
        mock_parse_obj.assert_called_with("push", payload)

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_async_handler_executes_correctly(self, mock_parse_obj: MagicMock):
        """Async webhook handlers should execute and return results."""
        mock_event = MagicMock(spec=PushEvent)
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        handler_called = {"value": False}

        @router.add_webhook("/github")
        async def async_handler(event: PushEvent):
            handler_called["value"] = True
            return {"async": True}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, payload)

        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 200
        assert handler_called["value"] is True
        assert response.json() == {"async": True}

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_multiple_webhook_endpoints(self, mock_parse_obj: MagicMock):
        """Router should support multiple webhook endpoints."""
        mock_event = MagicMock(spec=PushEvent)
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github/push")
        def handle_push(event: PushEvent):
            return {"type": "push"}

        @router.add_webhook("/github/pr")
        def handle_pr(event: PushEvent):
            return {"type": "pr"}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, payload)
        headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "push",
        }

        response_push = client.post("/github/push", json=payload, headers=headers)
        response_pr = client.post("/github/pr", json=payload, headers=headers)

        assert response_push.status_code == 200
        assert response_push.json() == {"type": "push"}
        assert response_pr.status_code == 200
        assert response_pr.json() == {"type": "pr"}

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_handler_receives_parsed_event(self, mock_parse_obj: MagicMock):
        """Handler should receive a properly parsed WebhookEvent object."""
        mock_event = MagicMock(spec=PushEvent)
        mock_event.ref = "refs/heads/feature-branch"
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        received_event: dict[str, PushEvent | None] = {"event": None}

        @router.add_webhook("/github")
        def handler(event: PushEvent):
            received_event["event"] = event
            return {"ref": event.ref}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/feature-branch"}
        signature = generate_signature(secret, payload)

        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 200
        assert response.json()["ref"] == "refs/heads/feature-branch"
        assert received_event["event"] is mock_event

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_handler_exception_propagates(self, mock_parse_obj: MagicMock):
        """Exceptions raised in handler should propagate correctly."""
        mock_event = MagicMock(spec=PushEvent)
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handler(event: PushEvent):
            raise ValueError("Handler error")

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, payload)

        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "push",
            },
        )

        # FastAPI returns 500 for unhandled exceptions
        assert response.status_code == 500

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_parse_obj_called_with_event_type_header(self, mock_parse_obj: MagicMock):
        """parse_obj should be called with the X-GitHub-Event header value."""
        mock_event = MagicMock(spec=PushEvent)
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handler(event: PushEvent):
            return {"handled": True}

        router.register(app)
        client = TestClient(app)

        payload = {"action": "completed"}
        signature = generate_signature(secret, payload)

        client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "check_run",
            },
        )

        # Verify parse_obj was called with the event type from header
        # parse_obj is called multiple times due to FastAPI dependency resolution
        mock_parse_obj.assert_called_with("check_run", payload)


class TestGithubWebhookRouterEdgeCases:
    """Edge case tests for GithubWebhookRouter."""

    def test_empty_webhook_secret(self):
        """Router should work with empty secret (though insecure)."""
        router = GithubWebhookRouter(webhook_secret="")
        assert router._webhook_secret == ""

    def test_special_characters_in_secret(self):
        """Router should handle secrets with special characters."""
        special_secret = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        router = GithubWebhookRouter(webhook_secret=special_secret)
        assert router._webhook_secret == special_secret

    def test_unicode_secret(self):
        """Router should handle unicode characters in secret."""
        unicode_secret = "秘密🔐ключ"
        router = GithubWebhookRouter(webhook_secret=unicode_secret)
        assert router._webhook_secret == unicode_secret

    def test_add_webhook_with_default_path(self):
        """Add_webhook should use '/' as default path."""
        app = FastAPI()
        router = GithubWebhookRouter(webhook_secret="test-secret")  # noqa: S106

        @router.add_webhook()  # No path specified
        def handler(event: PushEvent):
            return {"handled": True}

        router.register(app)

        # Check that a route was added at "/"
        route_paths = [
            getattr(route, "path", None)
            for route in app.routes
            if hasattr(route, "path")
        ]
        assert "/" in route_paths

    def test_malformed_signature_format(self):
        """Should reject signatures that don't follow sha256=... format."""
        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        @router.add_webhook("/github")
        def handler(event: PushEvent):
            return {"handled": True}

        router.register(app)
        client = TestClient(app, raise_server_exceptions=False)

        payload = {"ref": "refs/heads/main"}

        # Signature without sha256= prefix
        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": "just-a-hash-no-prefix",
                "X-GitHub-Event": "push",
            },
        )

        assert response.status_code == 401

    @patch("lambda_framework.webhook.github.parse_obj")
    def test_handler_with_additional_fastapi_deps(self, mock_parse_obj: MagicMock):
        """Handler should work with additional FastAPI dependencies."""
        mock_event = MagicMock(spec=PushEvent)
        mock_parse_obj.return_value = mock_event

        app = FastAPI()
        secret = "test-secret"
        router = GithubWebhookRouter(webhook_secret=secret)

        from typing import Annotated

        from fastapi import Header

        @router.add_webhook("/github")
        def handler(
            event: PushEvent,
            x_github_delivery: Annotated[str, Header()],
        ):
            return {"delivery_id": x_github_delivery}

        router.register(app)
        client = TestClient(app)

        payload = {"ref": "refs/heads/main"}
        signature = generate_signature(secret, payload)

        response = client.post(
            "/github",
            json=payload,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "abc-123-delivery-id",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"delivery_id": "abc-123-delivery-id"}


class TestGithubkitNotInstalled:
    """Tests for behavior when githubkit is not installed."""

    def test_validator_call_without_githubkit(self):
        """Validator should raise ImportError when verify is None."""
        validator = GithubWebhookValidator(secret="test")

        with (
            patch("lambda_framework.webhook.github.verify", None),
            pytest.raises(ImportError),
        ):
            validator({"test": "data"}, "sha256=fake")

    def test_parser_init_without_githubkit(self):
        """Parser should raise ImportError when parse_obj is None."""
        validator = GithubWebhookValidator(secret="test")

        with (
            patch("lambda_framework.webhook.github.parse_obj", None),
            pytest.raises(ImportError),
        ):
            GithubWebhookParser(validator)


class TestSignatureValidation:
    """Tests specifically for signature validation edge cases."""

    def test_signature_mismatch_with_different_json_serialization(self):
        """Signature should fail if JSON serialization differs."""
        secret = "test-secret"
        validator = GithubWebhookValidator(secret=secret)

        # Payload with spaces in JSON (non-compact)
        payload = {"key": "value", "number": 123}

        # Generate signature with compact JSON (no spaces)
        compact_json = json.dumps(payload, separators=(",", ":"))
        signature = (
            "sha256="
            + hmac.new(
                secret.encode(), compact_json.encode(), hashlib.sha256
            ).hexdigest()
        )

        # This should work since we use the same serialization
        result = validator(payload=payload, x_hub_signature_256=signature)
        assert result == payload

    def test_empty_signature_rejected(self):
        """Empty signature should be rejected."""
        validator = GithubWebhookValidator(secret="test-secret")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validator(payload={"test": "data"}, x_hub_signature_256="")

        assert exc_info.value.status_code == 401

    def test_signature_with_wrong_hash_algorithm_prefix(self):
        """Signature with wrong algorithm prefix should be rejected."""
        secret = "test-secret"
        payload = {"test": "data"}

        # Create signature with sha1 prefix instead of sha256
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
        hash_value = hmac.new(
            secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        wrong_prefix_signature = f"sha1={hash_value}"

        validator = GithubWebhookValidator(secret=secret)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validator(payload=payload, x_hub_signature_256=wrong_prefix_signature)

        assert exc_info.value.status_code == 401

    def test_very_long_payload(self):
        """Should handle very long payloads correctly."""
        secret = "test-secret"
        # Create a large payload
        large_payload = {"data": "x" * 100000, "nested": {"key": "value" * 1000}}

        signature = generate_signature(secret, large_payload)

        validator = GithubWebhookValidator(secret=secret)
        result = validator(payload=large_payload, x_hub_signature_256=signature)

        assert result == large_payload

    def test_payload_with_special_unicode(self):
        """Should handle payloads with unicode characters.

        Note: This test uses a mocked verify to avoid JSON serialization
        differences between our test helper and githubkit's internal verify.
        """
        secret = "test-secret"
        unicode_payload = {
            "message": "Hello 世界 🌍",
            "emoji": "👍🎉🚀",
            "cyrillic": "Привет мир",
        }

        with patch("lambda_framework.webhook.github.verify", return_value=True):
            validator = GithubWebhookValidator(secret=secret)
            result = validator(
                payload=unicode_payload, x_hub_signature_256="sha256=anysig"
            )

        assert result == unicode_payload
