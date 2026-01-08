"""Unit tests for the env_config module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from aws_secretsmanager_caching import SecretCacheConfig

from lambda_framework.env_config import EnvConfigBase


class TestEnvConfigBaseInit:
    """Tests for EnvConfigBase initialization."""

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_init_local_mode_does_not_create_cache(self, mock_get_session: MagicMock):
        """When env matches load_local_secrets_env, no secret cache should be created."""
        config = EnvConfigBase(env="dev", load_local_secrets_env="dev")

        assert config._secret_cache is None
        mock_get_session.assert_not_called()

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_init_aws_mode_creates_cache(self, mock_get_session: MagicMock):
        """When env doesn't match load_local_secrets_env, secret cache should be created."""
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.create_client.return_value = mock_client
        mock_get_session.return_value = mock_session

        config = EnvConfigBase(
            env="prod", load_local_secrets_env="dev", aws_secret_name="my-secret"
        )

        assert config._secret_cache is not None
        mock_get_session.assert_called_once()
        mock_session.create_client.assert_called_once_with("secretsmanager")

    def test_init_aws_mode_without_secret_name_raises_error(self):
        """When env doesn't match and aws_secret_name is not provided, should raise ValueError."""
        with pytest.raises(
            ValueError,
            match="Expected AWS Secret Name for secrets to be loaded from AWS Secrets Manager",
        ):
            EnvConfigBase(
                env="prod", load_local_secrets_env="dev", aws_secret_name=None
            )

    @patch("lambda_framework.env_config.SecretCache")
    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_init_with_custom_cache_config(
        self, mock_get_session: MagicMock, mock_secret_cache_class: MagicMock
    ):
        """Custom SecretCacheConfig should be passed to SecretCache."""
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.create_client.return_value = mock_client
        mock_get_session.return_value = mock_session

        custom_config = SecretCacheConfig(max_cache_size=100)

        EnvConfigBase(
            env="prod",
            load_local_secrets_env="dev",
            aws_secret_name="my-secret",
            secrets_cache_config=custom_config,
        )

        mock_secret_cache_class.assert_called_once_with(custom_config, mock_client)


class TestLoadLocalSecrets:
    """Tests for the load_local_secrets property."""

    def test_load_local_secrets_true_when_env_matches(self):
        """Should return True when env matches load_local_secrets_env."""
        config = EnvConfigBase(env="dev", load_local_secrets_env="dev")
        assert config.load_local_secrets is True

    def test_load_local_secrets_true_case_insensitive(self):
        """Should return True with case-insensitive matching."""
        config = EnvConfigBase(env="DEV", load_local_secrets_env="dev")
        assert config.load_local_secrets is True

        config2 = EnvConfigBase(env="dev", load_local_secrets_env="DEV")
        assert config2.load_local_secrets is True

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_load_local_secrets_false_when_env_differs(
        self, mock_get_session: MagicMock
    ):
        """Should return False when env doesn't match load_local_secrets_env."""
        mock_session = MagicMock()
        mock_session.create_client.return_value = MagicMock()
        mock_get_session.return_value = mock_session

        config = EnvConfigBase(
            env="prod", load_local_secrets_env="dev", aws_secret_name="my-secret"
        )
        assert config.load_local_secrets is False


class TestSecretCacheProperty:
    """Tests for the secret_cache property."""

    def test_secret_cache_is_none_in_local_mode(self):
        """Secret cache should be None when in local mode."""
        config = EnvConfigBase(env="dev", load_local_secrets_env="dev")
        assert config.secret_cache is None

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_secret_cache_is_set_in_aws_mode(self, mock_get_session: MagicMock):
        """Secret cache should be set when in AWS mode."""
        mock_session = MagicMock()
        mock_session.create_client.return_value = MagicMock()
        mock_get_session.return_value = mock_session

        config = EnvConfigBase(
            env="prod", load_local_secrets_env="dev", aws_secret_name="my-secret"
        )
        assert config.secret_cache is not None


class TestGetSecret:
    """Tests for the get_secret method."""

    @patch.dict("os.environ", {"MY_SECRET": "secret-value"})
    def test_get_secret_local_mode_returns_env_var(self):
        """In local mode, should return the value from environment variable."""
        config = EnvConfigBase(env="dev", load_local_secrets_env="dev")

        result = config.get_secret("MY_SECRET")

        assert result == "secret-value"

    @patch.dict("os.environ", {}, clear=True)
    def test_get_secret_local_mode_raises_when_env_var_missing(self):
        """In local mode, should raise ValueError when env var is not set."""
        config = EnvConfigBase(env="dev", load_local_secrets_env="dev")

        with pytest.raises(
            ValueError,
            match="Expected secret MISSING_SECRET to be set in environment variables",
        ):
            config.get_secret("MISSING_SECRET")

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_get_secret_aws_mode_returns_secret_from_cache(
        self, mock_get_session: MagicMock
    ):
        """In AWS mode, should return the secret from the cache."""
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.create_client.return_value = mock_client
        mock_get_session.return_value = mock_session

        config = EnvConfigBase(
            env="prod", load_local_secrets_env="dev", aws_secret_name="my-aws-secret"
        )

        # Mock the secret cache response
        secrets_data = {"MY_SECRET": "aws-secret-value", "OTHER_SECRET": "other-value"}
        assert config._secret_cache is not None
        config._secret_cache.get_secret_binary = MagicMock(
            return_value=json.dumps(secrets_data).encode()
        )

        result = config.get_secret("MY_SECRET")

        assert result == "aws-secret-value"
        config._secret_cache.get_secret_binary.assert_called_once_with("my-aws-secret")

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_get_secret_aws_mode_raises_when_secret_missing(
        self, mock_get_session: MagicMock
    ):
        """In AWS mode, should raise ValueError when secret is not in cache."""
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.create_client.return_value = mock_client
        mock_get_session.return_value = mock_session

        config = EnvConfigBase(
            env="prod", load_local_secrets_env="dev", aws_secret_name="my-aws-secret"
        )

        # Mock the secret cache response without the requested secret
        secrets_data = {"OTHER_SECRET": "other-value"}
        assert config._secret_cache is not None
        config._secret_cache.get_secret_binary = MagicMock(
            return_value=json.dumps(secrets_data).encode()
        )

        with pytest.raises(
            ValueError,
            match="Expected secret MISSING_SECRET to be set in AWS Secrets Manager",
        ):
            config.get_secret("MISSING_SECRET")

    @patch("lambda_framework.env_config.botocore.session.get_session")
    def test_get_secret_aws_mode_converts_non_string_to_string(
        self, mock_get_session: MagicMock
    ):
        """In AWS mode, should convert non-string secret values to strings."""
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.create_client.return_value = mock_client
        mock_get_session.return_value = mock_session

        config = EnvConfigBase(
            env="prod", load_local_secrets_env="dev", aws_secret_name="my-aws-secret"
        )

        # Mock the secret cache response with a numeric value
        secrets_data = {"NUMERIC_SECRET": 12345}
        assert config._secret_cache is not None
        config._secret_cache.get_secret_binary = MagicMock(
            return_value=json.dumps(secrets_data).encode()
        )

        result = config.get_secret("NUMERIC_SECRET")

        assert result == "12345"
        assert isinstance(result, str)

    def test_get_secret_raises_when_cache_is_none_unexpectedly(self):
        """Should raise ValueError if cache is None when trying to get secret from AWS."""
        config = EnvConfigBase(env="dev", load_local_secrets_env="dev")
        # Simulate switching environments without reinitializing
        config._env = "prod"
        config._load_local_secrets_env = "dev"

        with pytest.raises(
            ValueError,
            match="Expected secret cache to be setup when loading secrets from AWS Secrets Manager",
        ):
            config.get_secret("SOME_SECRET")
