"""Lambda framework module.

Provides a base class for managing environment-specific configuration,
including secrets retrieval from AWS Secrets Manager or local environment variables.
"""

import fastapi

from .env_config import EnvConfigBase, SecretCacheConfig
from .webhook import (
    GithubWebhookParser,
    GithubWebhookRouter,
    GithubWebhookValidator,
    githubkit,
)

__all__ = [
    "EnvConfigBase",
    "SecretCacheConfig",
    "GithubWebhookRouter",
    "GithubWebhookValidator",
    "GithubWebhookParser",
    "fastapi",
]

if githubkit is not None:
    __all__.append("githubkit")
