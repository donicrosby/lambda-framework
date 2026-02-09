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

  name                      = "${var.function_name}-trigger-dlq"
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = var.sqs_trigger.kms_key_id

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
        Sid    = "AllowAccountAccess"
        Effect = "Allow"
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
  function_name    = local.lambda_function.arn
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
