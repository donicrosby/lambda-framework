"""FastAPI module."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI
from mangum import Mangum

__all__ = ["create_app"]

MiddlewareConfig = tuple[type, dict[str, Any]]


def create_app(
    app: FastAPI | None = None,
    *,
    middleware: Sequence[MiddlewareConfig] | None = None,
    **fastapi_kwargs: Any,
) -> tuple[FastAPI, Mangum]:
    """Create a configured FastAPI app and Mangum handler.

    Accepts either a pre-built FastAPI instance OR keyword arguments
    forwarded to ``FastAPI()``.  Middleware is registered before the
    Mangum handler is created.  Mangum instantiation is deferred to
    this call, avoiding the Python 3.12+ ``asyncio.get_event_loop()``
    deprecation warning.

    Args:
        app: Optional pre-built FastAPI application.  When provided,
            *fastapi_kwargs* must be empty.
        middleware: Optional sequence of ``(MiddlewareClass, kwargs_dict)``
            tuples.  Each middleware is added via ``app.add_middleware()``.
        **fastapi_kwargs: Keyword arguments forwarded to ``FastAPI()``.

    Returns:
        A ``(app, handler)`` tuple of the FastAPI application and the
        Mangum Lambda handler.

    Raises:
        ValueError: If both *app* and *fastapi_kwargs* are provided.

    """
    if app is not None and fastapi_kwargs:
        raise ValueError("Cannot pass both a pre-built FastAPI app and fastapi_kwargs")

    if app is None:
        app = FastAPI(**fastapi_kwargs)

    if middleware:
        for mw_class, mw_kwargs in middleware:
            app.add_middleware(mw_class, **mw_kwargs)

    handler = Mangum(app)
    return app, handler


_DEFAULT_APP: FastAPI | None = None
_DEFAULT_HANDLER: Mangum | None = None


def __getattr__(name: str) -> Any:
    """Lazy initialization of APP and HANDLER for backward compatibility."""
    global _DEFAULT_APP, _DEFAULT_HANDLER  # noqa: PLW0603
    if name in ("APP", "HANDLER"):
        if _DEFAULT_APP is None:
            _DEFAULT_APP, _DEFAULT_HANDLER = create_app()
        if name == "APP":
            return _DEFAULT_APP
        return _DEFAULT_HANDLER
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
