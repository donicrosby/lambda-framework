# Lambda Framework

A Python framework for managing environment-specific configuration in AWS Lambda functions, with built-in support for secrets management via AWS Secrets Manager.

## Features

- **Environment-aware configuration**: Automatically switches between local and AWS-based secret retrieval based on environment
- **Development-friendly**: Load secrets from local environment variables during development
- **Production-ready**: Secure secrets retrieval from AWS Secrets Manager with caching for non-development environments
- **Type-safe**: Full type hints and `py.typed` marker for IDE support

## Installation

```bash
pip install lambda-framework
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add lambda-framework
```

## Quick Start

### 1. Create your configuration class

Extend `EnvConfigBase` to create a configuration class for your Lambda function:

```python
from lambda_framework import EnvConfigBase

class MyLambdaConfig(EnvConfigBase):
    def __init__(self, env: str):
        super().__init__(
            env=env,
            load_local_secrets_env="dev",  # Environment that uses local secrets
            aws_secret_name="my-lambda/secrets",  # AWS Secrets Manager secret name
        )
    
    @property
    def database_url(self) -> str:
        return self.get_secret("DATABASE_URL")
    
    @property
    def api_key(self) -> str:
        return self.get_secret("API_KEY")
```

### 2. Use in your Lambda handler

```python
import os

def handler(event, context):
    env = os.environ.get("ENVIRONMENT", "dev")
    config = MyLambdaConfig(env=env)
    
    # Secrets are automatically loaded from the appropriate source
    db_url = config.database_url
    api_key = config.api_key
    
    # ... rest of your Lambda logic
```

## Components

### `EnvConfigBase`

The base class for environment configuration management. Handles secret retrieval from either local environment variables (for development) or AWS Secrets Manager (for production environments).

#### Constructor Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `env` | `str` | Yes | - | Current environment name (e.g., `'dev'`, `'staging'`, `'prod'`) |
| `load_local_secrets_env` | `str` | No | `'dev'` | Environment name that triggers local secret loading |
| `aws_secret_name` | `str \| None` | Conditional | `None` | AWS Secrets Manager secret name. **Required** when not loading local secrets |
| `secrets_cache_config` | `SecretCacheConfig \| None` | No | `None` | Optional configuration for the AWS secrets cache |

#### Properties

- **`load_local_secrets`** (`bool`): Whether secrets should be loaded from local environment variables
- **`secret_cache`** (`SecretCache | None`): The AWS Secrets Manager cache instance, or `None` if loading local secrets

#### Methods

- **`get_secret(secret_name: str) -> str`**: Retrieve a secret by name from either local environment or AWS Secrets Manager

### `SecretCacheConfig`

Re-exported from [`aws-secretsmanager-caching`](https://github.com/aws/aws-secretsmanager-caching-python) for customizing cache behavior (TTL, max cache size, etc.).

```python
from lambda_framework import EnvConfigBase, SecretCacheConfig

# Custom cache configuration
cache_config = SecretCacheConfig(
    secret_refresh_interval=3600,  # Refresh secrets every hour
    secret_version_stage_refresh_interval=3600,
)

config = MyLambdaConfig(
    env="prod",
    aws_secret_name="my-secret",
    secrets_cache_config=cache_config,
)
```

## How It Works

### Development Mode (`env == load_local_secrets_env`)

When the current environment matches `load_local_secrets_env` (default: `'dev'`):
- Secrets are loaded from **local environment variables**
- No AWS credentials required
- Ideal for local development and testing

```bash
# Set secrets as environment variables
export DATABASE_URL="postgresql://localhost:5432/mydb"
export API_KEY="dev-api-key"
```

### Production Mode (any other environment)

When running in staging, production, or any non-development environment:
- Secrets are loaded from **AWS Secrets Manager**
- Secrets are cached for performance using `aws-secretsmanager-caching`
- Requires appropriate IAM permissions

Your AWS Secrets Manager secret should be stored as a JSON object:

```json
{
  "DATABASE_URL": "postgresql://prod-db:5432/mydb",
  "API_KEY": "prod-api-key-abc123"
}
```

## AWS IAM Permissions

For production environments, your Lambda function needs the following IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:my-lambda/secrets-*"
    }
  ]
}
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/lambda-framework.git
cd lambda-framework

# Install dependencies with uv
uv sync

# Install pre-commit hooks
pre-commit install
```

### Running Lints

```bash
uv run ruff check src/
uv run ruff format src/
```
