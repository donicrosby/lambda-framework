# ==============================================================================
# Secrets Manager Resources
# Creates a single secret for the Lambda function's JSON dictionary
# ==============================================================================

# Warn if secret_value is set without secret_config (value would be silently ignored)
check "secret_value_requires_config" {
  assert {
    condition     = var.secret_value == null || var.secret_config != null
    error_message = "var.secret_value is set but var.secret_config is null — the secret value will not be created. Provide secret_config to create the secret, or remove secret_value."
  }
}

# Create a single secret if configured
resource "aws_secretsmanager_secret" "this" {
  count = var.secret_config != null ? 1 : 0

  name        = var.secret_config.name
  description = var.secret_config.description
  kms_key_id  = var.secret_config.kms_key_id

  recovery_window_in_days = var.secret_config.recovery_window_in_days

  tags = merge(var.tags, {
    Name           = var.secret_config.name
    LambdaFunction = var.function_name
  })
}

# Set the secret value if provided
# Note: This stores the secret value in Terraform state. Ensure state is encrypted.
resource "aws_secretsmanager_secret_version" "this" {
  count = var.secret_config != null && var.secret_value != null ? 1 : 0

  secret_id     = aws_secretsmanager_secret.this[0].id
  secret_string = jsonencode(var.secret_value)
}

# Output for created secret ARN (useful for setting up rotation or initial values)
locals {
  created_secret_arns = var.secret_config != null ? [aws_secretsmanager_secret.this[0].arn] : []
}
