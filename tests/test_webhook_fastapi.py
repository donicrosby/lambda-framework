"""Unit tests for the FastAPI webhook module."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mangum import Mangum
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from lambda_framework.webhook.fastapi import create_app


class _KwargsMiddleware(BaseHTTPMiddleware):
    """Middleware that accepts kwargs and sets a response header."""

    def __init__(self, app: Any, *, header_value: str = "default"):
        super().__init__(app)
        self.header_value = header_value

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Custom-Header"] = self.header_value
        return response


class TestCreateAppBasic:
    """Tests for create_app with no args and basic kwargs."""

    def test_create_app_returns_tuple(self):
        """create_app() with no args returns (FastAPI, Mangum) tuple."""
        app, handler = create_app()
        assert isinstance(app, FastAPI)
        assert isinstance(handler, Mangum)

    def test_create_app_with_title_passes_kwargs_to_fastapi(self):
        """create_app(title='My Service') passes kwargs to FastAPI."""
        app, handler = create_app(title="My Service")
        assert app.title == "My Service"
        assert isinstance(handler, Mangum)


class TestCreateAppWithPrebuiltApp:
    """Tests for create_app with a pre-built FastAPI instance."""

    def test_create_app_uses_provided_app(self):
        """create_app(app=existing_app) uses the provided app."""
        existing = FastAPI(title="Existing")
        app, handler = create_app(app=existing)
        assert app is existing
        assert app.title == "Existing"
        assert isinstance(handler, Mangum)

    def test_create_app_app_and_kwargs_raises_value_error(self):
        """create_app(app=existing_app, title='X') raises ValueError."""
        existing = FastAPI()
        with pytest.raises(
            ValueError,
            match="Cannot pass both a pre-built FastAPI app and fastapi_kwargs",
        ):
            create_app(app=existing, title="X")


class TestCreateAppMiddleware:
    """Tests for create_app middleware support."""

    def test_middleware_applied_in_order(self):
        """Middleware is applied in order (last added is outermost per Starlette)."""
        call_order: list[str] = []

        class First(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: Any) -> Response:
                call_order.append("first_in")
                response = await call_next(request)
                call_order.append("first_out")
                return response

        class Second(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: Any) -> Response:
                call_order.append("second_in")
                response = await call_next(request)
                call_order.append("second_out")
                return response

        app, _ = create_app(
            middleware=[
                (First, {}),
                (Second, {}),
            ],
        )
        client = TestClient(app)
        client.get("/openapi.json")
        assert call_order == ["second_in", "first_in", "first_out", "second_out"]

    def test_middleware_with_kwargs_works(self):
        """Middleware with kwargs works."""
        app, _ = create_app(
            middleware=[
                (_KwargsMiddleware, {"header_value": "custom-value"}),
            ],
        )
        client = TestClient(app)
        response = client.get("/openapi.json")
        assert response.headers.get("X-Custom-Header") == "custom-value"


class TestLazyFastApiModule:
    """Tests for lazy APP and HANDLER access from lambda_framework.webhook.fastapi."""

    def test_lazy_app_access_returns_fastapi(self):
        """Lazy APP access from lambda_framework.webhook.fastapi works."""
        import lambda_framework.webhook.fastapi as fastapi_mod

        fastapi_mod._DEFAULT_APP = None
        fastapi_mod._DEFAULT_HANDLER = None
        app = fastapi_mod.APP
        assert isinstance(app, FastAPI)

    def test_lazy_handler_access_returns_mangum(self):
        """Lazy HANDLER access works."""
        import lambda_framework.webhook.fastapi as fastapi_mod

        fastapi_mod._DEFAULT_APP = None
        fastapi_mod._DEFAULT_HANDLER = None
        handler = fastapi_mod.HANDLER
        assert isinstance(handler, Mangum)

    def test_getattr_raises_attribute_error_for_unknown_names(self):
        """__getattr__ raises AttributeError for unknown names."""
        import lambda_framework.webhook.fastapi as fastapi_mod

        with pytest.raises(
            AttributeError,
            match="module 'lambda_framework.webhook.fastapi' has no attribute 'UNKNOWN'",
        ):
            _ = fastapi_mod.UNKNOWN


class TestLazyWebhookModule:
    """Tests for backward-compatible lazy app and handler from lambda_framework.webhook."""

    def test_lazy_app_from_webhook_module(self):
        """Lazy app from lambda_framework.webhook still works (backward compat)."""
        import lambda_framework.webhook as webhook_mod

        if "app" in webhook_mod.__dict__:
            del webhook_mod.__dict__["app"]
        if "handler" in webhook_mod.__dict__:
            del webhook_mod.__dict__["handler"]
        import lambda_framework.webhook.fastapi as fastapi_mod

        fastapi_mod._DEFAULT_APP = None
        fastapi_mod._DEFAULT_HANDLER = None
        app = webhook_mod.app
        assert isinstance(app, FastAPI)

    def test_lazy_handler_from_webhook_module(self):
        """Lazy handler from lambda_framework.webhook still works (backward compat)."""
        import lambda_framework.webhook as webhook_mod

        if "app" in webhook_mod.__dict__:
            del webhook_mod.__dict__["app"]
        if "handler" in webhook_mod.__dict__:
            del webhook_mod.__dict__["handler"]
        import lambda_framework.webhook.fastapi as fastapi_mod

        fastapi_mod._DEFAULT_APP = None
        fastapi_mod._DEFAULT_HANDLER = None
        handler = webhook_mod.handler
        assert isinstance(handler, Mangum)


class TestLazyFreshState:
    """Tests that verify lazy __getattr__ works after module reload."""

    def test_lazy_app_after_reload(self):
        """Lazy APP works after module reload for fresh state."""
        import lambda_framework.webhook.fastapi as fastapi_mod

        importlib.reload(fastapi_mod)
        app = fastapi_mod.APP
        assert isinstance(app, FastAPI)

    def test_lazy_handler_after_reload(self):
        """Lazy HANDLER works after module reload for fresh state."""
        import lambda_framework.webhook.fastapi as fastapi_mod

        importlib.reload(fastapi_mod)
        handler = fastapi_mod.HANDLER
        assert isinstance(handler, Mangum)
