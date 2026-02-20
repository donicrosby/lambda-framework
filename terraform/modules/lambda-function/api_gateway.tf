# ==============================================================================
# API Gateway REST API (v1) - Proxy pass-through to Lambda
# All paths are forwarded via {proxy+}; Lambda handles routing and CORS.
# ==============================================================================

resource "aws_api_gateway_rest_api" "this" {
  count = var.api_gateway.enabled ? 1 : 0

  name        = "${var.function_name}-api"
  description = "REST API for Lambda function ${var.function_name}"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.tags
}

# ==============================================================================
# {proxy+} catch-all resource — forwards every path to Lambda
# ==============================================================================

resource "aws_api_gateway_resource" "proxy" {
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.this[0].id
  parent_id   = aws_api_gateway_rest_api.this[0].root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" { #trivy:ignore:AVD-AWS-0004 -- Auth handled in Lambda via webhook signature verification (e.g. HMAC)
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id   = aws_api_gateway_rest_api.this[0].id
  resource_id   = aws_api_gateway_resource.proxy[0].id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy" {
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id             = aws_api_gateway_rest_api.this[0].id
  resource_id             = aws_api_gateway_resource.proxy[0].id
  http_method             = aws_api_gateway_method.proxy[0].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.lambda_function.invoke_arn
}

# ==============================================================================
# Root resource (/) — handles requests to the base URL
# ==============================================================================

resource "aws_api_gateway_method" "root" { #trivy:ignore:AVD-AWS-0004 -- Auth handled in Lambda via webhook signature verification (e.g. HMAC)
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id   = aws_api_gateway_rest_api.this[0].id
  resource_id   = aws_api_gateway_rest_api.this[0].root_resource_id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "root" {
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id             = aws_api_gateway_rest_api.this[0].id
  resource_id             = aws_api_gateway_rest_api.this[0].root_resource_id
  http_method             = aws_api_gateway_method.root[0].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.lambda_function.invoke_arn
}

# ==============================================================================
# Deployment & Stage
# ==============================================================================

resource "aws_api_gateway_deployment" "this" {
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.this[0].id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy[0].id,
      aws_api_gateway_method.proxy[0].id,
      aws_api_gateway_integration.proxy[0].id,
      aws_api_gateway_method.root[0].id,
      aws_api_gateway_integration.root[0].id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  count = var.api_gateway.enabled ? 1 : 0

  deployment_id        = aws_api_gateway_deployment.this[0].id
  rest_api_id          = aws_api_gateway_rest_api.this[0].id
  stage_name           = var.api_gateway.stage_name
  xray_tracing_enabled = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway[0].arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      resourcePath     = "$context.resourcePath"
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

# ==============================================================================
# Throttling (applied to all methods via stage-level settings)
# ==============================================================================

resource "aws_api_gateway_method_settings" "all" { #trivy:ignore:AVD-AWS-0190 #trivy:ignore:AVD-AWS-0002 -- Caching disabled intentionally; webhook requests must always reach Lambda
  count = var.api_gateway.enabled ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.this[0].id
  stage_name  = aws_api_gateway_stage.this[0].stage_name
  method_path = "*/*"

  settings {
    throttling_burst_limit = var.api_gateway.throttling.burst_limit
    throttling_rate_limit  = var.api_gateway.throttling.rate_limit
  }
}

# ==============================================================================
# Lambda Permission for API Gateway
# CIS Lambda.1: Uses source_arn condition to prevent unauthorized invocations
# ==============================================================================

resource "aws_lambda_permission" "api_gateway" {
  count = var.api_gateway.enabled ? 1 : 0

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = local.lambda_function.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this[0].execution_arn}/*/*"
}
