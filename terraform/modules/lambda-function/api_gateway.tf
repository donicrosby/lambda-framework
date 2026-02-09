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
  integration_uri        = local.lambda_function.invoke_arn
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
  function_name = local.lambda_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http[0].execution_arn}/*/*"
}
