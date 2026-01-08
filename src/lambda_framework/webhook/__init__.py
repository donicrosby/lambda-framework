"""Webhook module."""

from .fastapi import APP as app
from .fastapi import HANDLER as handler
from .github import GithubWebhookParser, GithubWebhookRouter, GithubWebhookValidator

try:
    import githubkit
except ImportError:
    githubkit = None

__all__ = [
    "app",
    "handler",
    "GithubWebhookRouter",
    "GithubWebhookValidator",
    "GithubWebhookParser",
    "githubkit",
]
