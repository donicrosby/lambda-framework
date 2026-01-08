"""Lambda framework module.

Provides a base class for managing environment-specific configuration,
including secrets retrieval from AWS Secrets Manager or local environment variables.
"""

from .env_config import EnvConfigBase, SecretCacheConfig

__all__ = ["EnvConfigBase", "SecretCacheConfig"]
