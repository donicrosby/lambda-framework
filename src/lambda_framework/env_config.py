"""Environment configuration module for Lambda functions.

Provides a base class for managing environment-specific configuration,
including secrets retrieval from AWS Secrets Manager or local environment variables.
"""

import json
import os
from typing import Any

import botocore
import botocore.session
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig

__all__ = ["EnvConfigBase", "SecretCacheConfig"]


class EnvConfigBase:
    """Base class for environment configuration management.

    Handles secret retrieval from either local environment variables (for development)
    or AWS Secrets Manager (for non-development environments).
    """

    def __init__(
        self,
        env: str,
        load_local_secrets_env: str = "dev",
        aws_secret_name: str | None = None,
        secrets_cache_config: SecretCacheConfig | None = None,
    ):
        """Initialize the environment configuration.

        Args:
            env: The current environment name (e.g., 'dev', 'staging', 'prod').
            load_local_secrets_env: The environment name that triggers local secret loading.
                Defaults to 'dev'.
            aws_secret_name: The name of the AWS Secrets Manager secret.
                Required when not loading local secrets.
            secrets_cache_config: Optional configuration for the secrets cache.

        Raises:
            ValueError: If aws_secret_name is not provided when loading from AWS Secrets Manager.

        """
        self._env = env
        self._load_local_secrets_env = load_local_secrets_env
        self._aws_secret_name = aws_secret_name
        self._parsed_secrets: dict[str, Any] | None = None
        if not self.load_local_secrets:
            if self._aws_secret_name is None:
                raise ValueError(
                    "Expected AWS Secret Name for secrets to be loaded from AWS Secrets Manager"
                )
            self._secret_cache = self._setup_secret_cache(secrets_cache_config)
        else:
            self._secret_cache = None

    @staticmethod
    def _setup_secret_cache(config: SecretCacheConfig | None = None) -> SecretCache:
        secrets_client = botocore.session.get_session().create_client("secretsmanager")
        if config is None:
            config = SecretCacheConfig()
        return SecretCache(config, secrets_client)

    @property
    def load_local_secrets(self) -> bool:
        """Whether secrets should be loaded from local environment variables."""
        return self._env.lower() == self._load_local_secrets_env.lower()

    @property
    def secret_cache(self) -> SecretCache | None:
        """The AWS Secrets Manager cache instance, or None if loading local secrets."""
        return self._secret_cache

    def _get_parsed_secrets(self) -> dict[str, Any]:
        """Retrieve and cache the parsed secrets dictionary from AWS Secrets Manager.

        Returns:
            The parsed secrets dictionary.

        Raises:
            ValueError: If the secret cache is not configured.

        """
        if self._parsed_secrets is not None:
            return self._parsed_secrets

        if self._secret_cache is None:
            raise ValueError(
                "Expected secret cache to be setup when loading secrets from AWS Secrets Manager"
            )
        raw_secret: str = self._secret_cache.get_secret_string(self._aws_secret_name)
        parsed: dict[str, Any] = json.loads(raw_secret)
        self._parsed_secrets = parsed
        return parsed

    def get_secret(self, secret_name: str) -> str:
        """Retrieve a secret by name.

        Args:
            secret_name: The name of the secret to retrieve.

        Returns:
            The secret value as a string.

        Raises:
            ValueError: If the secret is not found in environment variables or AWS Secrets Manager,
                or if the secret cache is not configured when loading from AWS.

        """
        if self.load_local_secrets:
            secret_value = os.getenv(secret_name)
            if secret_value is None:
                raise ValueError(
                    f"Expected secret {secret_name} to be set in environment variables"
                )
            return secret_value

        secrets_dict = self._get_parsed_secrets()
        secret_value = secrets_dict.get(secret_name)
        if secret_value is None:
            raise ValueError(
                f"Expected secret {secret_name} to be set in AWS Secrets Manager"
            )
        return str(secret_value)
