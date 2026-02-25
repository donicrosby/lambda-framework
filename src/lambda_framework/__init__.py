"""Lambda framework module.

Provides a base class for managing environment-specific configuration,
including secrets retrieval from AWS Secrets Manager or local environment variables.
"""

from .dispatch import create_dispatcher
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
    "create_dispatcher",
]

# Optional eventbridge module (requires aioboto3 package)
try:
    from .eventbridge import EventBridgePublisher

    __all__.append("EventBridgePublisher")
except ImportError:
    EventBridgePublisher = None  # type: ignore[assignment,misc]

# Optional cache module (requires redis package)
try:
    from .cache import CacheInfo, async_redis_cache

    __all__.extend(["async_redis_cache", "CacheInfo"])
except ImportError:
    async_redis_cache = None  # type: ignore[assignment,misc]
    CacheInfo = None  # type: ignore[assignment,misc]

# Optional github module (requires githubkit package)
try:
    from .github import LambdaThrottler

    __all__.append("LambdaThrottler")
except ImportError:
    LambdaThrottler = None  # type: ignore[assignment,misc]
