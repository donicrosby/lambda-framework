"""Webhook module."""

from .fastapi import create_app
from .github import GithubWebhookParser, GithubWebhookRouter, GithubWebhookValidator

__all__ = [
    "create_app",
    "GithubWebhookRouter",
    "GithubWebhookValidator",
    "GithubWebhookParser",
]


def __getattr__(name: str):
    """Backward-compatible lazy access to ``app`` and ``handler``."""
    if name in ("app", "handler"):
        from . import fastapi as _fastapi

        if name == "app":
            return _fastapi.APP
        return _fastapi.HANDLER
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
