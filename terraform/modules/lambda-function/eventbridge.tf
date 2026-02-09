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
