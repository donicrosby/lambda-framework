# ==============================================================================
# Lambda Function Triggers
# Supports API Gateway HTTP API, SQS, and EventBridge
# ==============================================================================

# ==============================================================================
# API Gateway HTTP API (v2) - Preferred for webhooks
# ==============================================================================

resource "aws_apigatewayv2_api" "http" {
  count = var.api_gateway.enabled ? 1 : 0

  name          = "${var.function_name}-api"
  protocol_type = "HTTP"
  description   = "HTTP API for Lambda function ${var.function_name}"

  # CORS configuration
  dynamic "cors_configuration" {
    for_each = var.api_gateway.cors != null ? [var.api_gateway.cors] : []
    content {
      allow_origins     = cors_configuration.value.allow_origins
      allow_methods     = cors_configuration.value.allow_methods
      allow_headers     = cors_configuration.value.allow_headers
      expose_headers    = cors_configuration.value.expose_headers
      max_age           = cors_configuration.value.max_age
      allow_credentials = cors_configuration.value.allow_credentials
    }
  }

  tags = var.tags
}

resource "aws_apigatewayv2_stage" "default" {
  count = var.api_gateway.enabled ? 1 : 0

  api_id      = aws_apigatewayv2_api.http[0].id
  name        = var.api_gateway.stage_name
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = var.api_gateway.throttling.burst_limit
    throttling_rate_limit  = var.api_gateway.throttling.rate_limit
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway[0].arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      protocol         = "$context.protocol"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  count = var.api_gateway.enabled ? 1 : 0

  name              = "/aws/apigateway/${var.function_name}-api"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_kms_key_arn

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "lambda" {
  count = var.api_gateway.enabled ? 1 : 0

  api_id                 = aws_apigatewayv2_api.http[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.this.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = var.api_gateway.enabled ? { for idx, route in var.api_gateway.routes : "${route.method}-${route.path}" => route } : {}

  api_id    = aws_apigatewayv2_api.http[0].id
  route_key = "${each.value.method} ${each.value.path}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[0].id}"
}

# Lambda permission for API Gateway
# CIS Lambda.1: Uses source_arn condition to prevent unauthorized invocations
resource "aws_lambda_permission" "api_gateway" {
  count = var.api_gateway.enabled ? 1 : 0

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http[0].execution_arn}/*/*"
}

# ==============================================================================
# SQS Trigger
# ==============================================================================

resource "aws_sqs_queue" "trigger" {
  count = var.sqs_trigger.enabled && var.sqs_trigger.existing_queue_arn == null ? 1 : 0

  name                       = "${var.function_name}-trigger-queue"
  visibility_timeout_seconds = var.sqs_trigger.visibility_timeout_seconds
  message_retention_seconds  = var.sqs_trigger.message_retention_seconds
  receive_wait_time_seconds  = var.sqs_trigger.receive_wait_time_seconds
  kms_master_key_id          = var.sqs_trigger.kms_key_id

  # Redrive policy for DLQ
  dynamic "redrive_policy" {
    for_each = var.sqs_trigger.create_dlq ? [1] : []
    content {
      deadLetterTargetArn = aws_sqs_queue.dlq[0].arn
      maxReceiveCount     = var.sqs_trigger.dlq_max_receive_count
    }
  }

  tags = var.tags
}

resource "aws_sqs_queue" "dlq" {
  count = var.sqs_trigger.enabled && var.sqs_trigger.existing_queue_arn == null && var.sqs_trigger.create_dlq ? 1 : 0

  name                       = "${var.function_name}-trigger-dlq"
  message_retention_seconds  = 1209600 # 14 days
  kms_master_key_id          = var.sqs_trigger.kms_key_id

  tags = var.tags
}

# SQS Queue Policy to prevent public access (CIS compliance)
resource "aws_sqs_queue_policy" "trigger" {
  count = var.sqs_trigger.enabled && var.sqs_trigger.existing_queue_arn == null ? 1 : 0

  queue_url = aws_sqs_queue.trigger[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyUnsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sqs:*"
        Resource  = aws_sqs_queue.trigger[0].arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid       = "AllowAccountAccess"
        Effect    = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "sqs:*"
        Resource = aws_sqs_queue.trigger[0].arn
      }
    ]
  })
}

# Lambda event source mapping for SQS
resource "aws_lambda_event_source_mapping" "sqs" {
  count = var.sqs_trigger.enabled ? 1 : 0

  event_source_arn = var.sqs_trigger.existing_queue_arn != null ? var.sqs_trigger.existing_queue_arn : aws_sqs_queue.trigger[0].arn
  function_name    = aws_lambda_function.this.arn
  batch_size       = var.sqs_trigger.batch_size

  maximum_batching_window_in_seconds = var.sqs_trigger.maximum_batching_window

  function_response_types = var.sqs_trigger.function_response_types

  dynamic "scaling_config" {
    for_each = var.sqs_trigger.maximum_concurrency != null ? [1] : []
    content {
      maximum_concurrency = var.sqs_trigger.maximum_concurrency
    }
  }

  dynamic "filter_criteria" {
    for_each = var.sqs_trigger.filtering_criteria != null ? [1] : []
    content {
      filter {
        pattern = var.sqs_trigger.filtering_criteria
      }
    }
  }
}

# ==============================================================================
# EventBridge Trigger
# ==============================================================================

resource "aws_cloudwatch_event_rule" "trigger" {
  count = var.eventbridge_trigger.enabled ? 1 : 0

  name                = "${var.function_name}-trigger"
  description         = var.eventbridge_trigger.description
  event_bus_name      = var.eventbridge_trigger.event_bus_name
  schedule_expression = var.eventbridge_trigger.schedule
  event_pattern       = var.eventbridge_trigger.event_pattern

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "lambda" {
  count = var.eventbridge_trigger.enabled ? 1 : 0

  rule           = aws_cloudwatch_event_rule.trigger[0].name
  event_bus_name = var.eventbridge_trigger.event_bus_name
  target_id      = "${var.function_name}-target"
  arn            = aws_lambda_function.this.arn
}

# Lambda permission for EventBridge
# CIS Lambda.1: Uses source_arn condition to prevent unauthorized invocations
resource "aws_lambda_permission" "eventbridge" {
  count = var.eventbridge_trigger.enabled ? 1 : 0

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.trigger[0].arn
}
