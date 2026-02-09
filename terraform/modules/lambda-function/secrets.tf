# ==============================================================================
# Secrets Manager Resources
# Creates a single secret for the Lambda function's JSON dictionary
# ==============================================================================

# Create a single secret if configured
# Note: Secret values should be set outside of Terraform (via AWS Console, CLI, or 
# a separate process) to avoid storing sensitive data in Terraform state.
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

# Output for created secret ARN (useful for setting up rotation or initial values)
locals {
  created_secret_arns = var.secret_config != null ? [aws_secretsmanager_secret.this[0].arn] : []
}
