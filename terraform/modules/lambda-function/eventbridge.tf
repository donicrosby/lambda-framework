# ==============================================================================
# EventBridge Configuration
# ==============================================================================

locals {
  create_event_bus = var.eventbridge_trigger.create_event_bus
  event_bus_name = (
    local.create_event_bus
    ? aws_cloudwatch_event_bus.this[0].name
    : var.eventbridge_trigger.event_bus_name
  )
  event_bus_arn = (
    local.create_event_bus
    ? aws_cloudwatch_event_bus.this[0].arn
    : null
  )
}

# ==============================================================================
# Custom Event Bus
# ==============================================================================

resource "aws_cloudwatch_event_bus" "this" {
  count = local.create_event_bus ? 1 : 0

  name              = "${var.function_name}-bus"
  event_source_name = var.eventbridge_trigger.partner_event_source_name

  tags = var.tags
}

# Event bus policy: restrict to account and deny insecure access
resource "aws_cloudwatch_event_bus_policy" "this" {
  count = local.create_event_bus && var.eventbridge_trigger.partner_event_source_name == null ? 1 : 0

  event_bus_name = aws_cloudwatch_event_bus.this[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowAccountPutEvents"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "events:PutEvents"
        Resource  = aws_cloudwatch_event_bus.this[0].arn
      }
    ]
  })
}

# ==============================================================================
# Event Archive (optional replay capability)
# ==============================================================================

resource "aws_cloudwatch_event_archive" "this" {
  count = local.create_event_bus && var.eventbridge_trigger.archive_retention_days != null ? 1 : 0

  name             = "${var.function_name}-archive"
  event_source_arn = aws_cloudwatch_event_bus.this[0].arn
  retention_days   = var.eventbridge_trigger.archive_retention_days
  event_pattern    = var.eventbridge_trigger.event_pattern
}

# ==============================================================================
# Schema Discovery (optional)
# ==============================================================================

resource "aws_schemas_discoverer" "this" {
  count = local.create_event_bus && var.eventbridge_trigger.enable_schema_discovery ? 1 : 0

  source_arn  = aws_cloudwatch_event_bus.this[0].arn
  description = "Schema discoverer for ${var.function_name} event bus"

  tags = var.tags
}

# ==============================================================================
# EventBridge Trigger Rule
# ==============================================================================

resource "aws_cloudwatch_event_rule" "trigger" {
  count = var.eventbridge_trigger.enabled ? 1 : 0

  name                = "${var.function_name}-trigger"
  description         = var.eventbridge_trigger.description
  event_bus_name      = local.event_bus_name
  schedule_expression = var.eventbridge_trigger.schedule
  event_pattern       = var.eventbridge_trigger.event_pattern

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "lambda" {
  count = var.eventbridge_trigger.enabled ? 1 : 0

  rule           = aws_cloudwatch_event_rule.trigger[0].name
  event_bus_name = local.event_bus_name
  target_id      = "${var.function_name}-target"
  arn            = local.lambda_function.arn
}

# Lambda permission for EventBridge
# CIS Lambda.1: Uses source_arn condition to prevent unauthorized invocations
resource "aws_lambda_permission" "eventbridge" {
  count = var.eventbridge_trigger.enabled ? 1 : 0

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = local.lambda_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.trigger[0].arn
}
