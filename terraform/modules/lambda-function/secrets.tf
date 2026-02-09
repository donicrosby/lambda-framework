# ==============================================================================
# Secrets Manager Resources
# Supports both creating new secrets and referencing existing ones
# ==============================================================================

# Create new secrets if enabled
# Note: Secret values should be set outside of Terraform (via AWS Console, CLI, or 
# a separate process) to avoid storing sensitive data in Terraform state.
resource "aws_secretsmanager_secret" "this" {
  for_each = var.create_secrets ? var.secrets : {}

  name        = each.key
  description = each.value.description
  kms_key_id  = each.value.kms_key_id

  recovery_window_in_days = each.value.recovery_window_in_days

  tags = merge(var.tags, {
    Name           = each.key
    ManagedBy      = "terraform"
    LambdaFunction = var.function_name
  })
}

# Output for created secret ARNs (useful for setting up rotation or initial values)
locals {
  created_secret_arns = [for secret in aws_secretsmanager_secret.this : secret.arn]
}
