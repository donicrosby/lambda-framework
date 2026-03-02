# ==============================================================================
# CloudWatch Log Group for Lambda Function
# Supports optional KMS encryption for CIS compliance
# ==============================================================================

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_kms_key_arn

  tags = merge(var.tags, {
    Name = "/aws/lambda/${var.function_name}"
  })
}
