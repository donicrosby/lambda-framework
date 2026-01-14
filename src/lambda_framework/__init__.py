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
)

__all__ = [
    "EnvConfigBase",
    "SecretCacheConfig",
    "GithubWebhookRouter",
    "GithubWebhookValidator",
    "GithubWebhookParser",
    "fastapi",
]

# Optional cache module (requires redis package)
try:
    from .cache import CacheInfo, async_redis_cache

    __all__.extend(["async_redis_cache", "CacheInfo"])
except ImportError:
    async_redis_cache = None  # type: ignore[assignment,misc]
    CacheInfo = None  # type: ignore[assignment,misc]

try:
    import githubkit  # noqa: F401

    from .github import LambdaThrottler  # noqa: F401

    __all__.extend(["LambdaThrottler", "githubkit"])  # noqa: F401
except ImportError:
    LambdaThrottler = None  # type: ignore[assignment,misc]
    githubkit = None  # type: ignore[assignment,misc]
