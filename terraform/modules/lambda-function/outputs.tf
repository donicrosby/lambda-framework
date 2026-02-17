# ==============================================================================
# Module Outputs
# ==============================================================================

# ==============================================================================
# Lambda Function Outputs
# ==============================================================================

output "function_arn" {
  description = "ARN of the Lambda function"
  value       = local.lambda_function.arn
}

output "function_name" {
  description = "Name of the Lambda function"
  value       = local.lambda_function.function_name
}

output "function_qualified_arn" {
  description = "Qualified ARN of the Lambda function (includes version)"
  value       = local.lambda_function.qualified_arn
}

output "invoke_arn" {
  description = "Invoke ARN of the Lambda function (for API Gateway)"
  value       = local.lambda_function.invoke_arn
}

output "function_version" {
  description = "Latest published version of the Lambda function"
  value       = local.lambda_function.version
}

# ==============================================================================
# IAM Outputs
# ==============================================================================

output "execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = local.role_arn
}

output "execution_role_name" {
  description = "Name of the Lambda execution role (null if using existing role)"
  value       = local.role_name
}

# ==============================================================================
# CloudWatch Logs Outputs
# ==============================================================================

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "log_group_arn" {
  description = "ARN of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.lambda.arn
}

# ==============================================================================
# API Gateway Outputs
# ==============================================================================

output "api_gateway_id" {
  description = "ID of the API Gateway HTTP API"
  value       = var.api_gateway.enabled ? aws_apigatewayv2_api.http[0].id : null
}

output "api_gateway_url" {
  description = "URL of the API Gateway HTTP API endpoint"
  value       = var.api_gateway.enabled ? aws_apigatewayv2_stage.default[0].invoke_url : null
}

output "api_gateway_execution_arn" {
  description = "Execution ARN of the API Gateway HTTP API"
  value       = var.api_gateway.enabled ? aws_apigatewayv2_api.http[0].execution_arn : null
}

output "api_gateway_stage_name" {
  description = "Name of the API Gateway stage"
  value       = var.api_gateway.enabled ? aws_apigatewayv2_stage.default[0].name : null
}

# ==============================================================================
# SQS Outputs
# ==============================================================================

output "sqs_queue_url" {
  description = "URL of the SQS trigger queue"
  value       = var.sqs_trigger.enabled && var.sqs_trigger.existing_queue_arn == null ? aws_sqs_queue.trigger[0].url : null
}

output "sqs_queue_arn" {
  description = "ARN of the SQS trigger queue"
  value       = var.sqs_trigger.enabled ? (var.sqs_trigger.existing_queue_arn != null ? var.sqs_trigger.existing_queue_arn : aws_sqs_queue.trigger[0].arn) : null
}

output "sqs_dlq_url" {
  description = "URL of the SQS dead letter queue"
  value       = var.sqs_trigger.enabled && var.sqs_trigger.existing_queue_arn == null && var.sqs_trigger.create_dlq ? aws_sqs_queue.dlq[0].url : null
}

output "sqs_dlq_arn" {
  description = "ARN of the SQS dead letter queue"
  value       = var.sqs_trigger.enabled && var.sqs_trigger.existing_queue_arn == null && var.sqs_trigger.create_dlq ? aws_sqs_queue.dlq[0].arn : null
}

# ==============================================================================
# EventBridge Outputs
# ==============================================================================

output "eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule"
  value       = var.eventbridge_trigger.enabled ? aws_cloudwatch_event_rule.trigger[0].arn : null
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = var.eventbridge_trigger.enabled ? aws_cloudwatch_event_rule.trigger[0].name : null
}

# ==============================================================================
# Secrets Manager Outputs
# ==============================================================================

output "created_secret_arns" {
  description = "ARN of the secret created by this module"
  value       = local.created_secret_arns
}

output "all_secret_arns" {
  description = "All secret ARNs the Lambda function has access to (created + existing)"
  value       = local.all_secret_arns
}

output "created_secret_version_id" {
  description = "Version ID of the secret value created by this module"
  value       = var.secret_config != null && var.secret_value != null ? aws_secretsmanager_secret_version.this[0].version_id : null
}

# ==============================================================================
# VPC Outputs
# ==============================================================================

output "vpc_config" {
  description = "VPC configuration applied to the Lambda function"
  value       = var.vpc_config
}

output "subnet_availability_zones" {
  description = "Availability zones of the configured subnets"
  value       = local.subnet_azs
}
