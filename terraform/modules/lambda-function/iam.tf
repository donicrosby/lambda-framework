# ==============================================================================
# IAM Role and Policies for Lambda Function
# Follows least-privilege principle with scoped permissions
# ==============================================================================

locals {
  create_role = var.existing_execution_role_arn == null
  role_arn    = local.create_role ? aws_iam_role.lambda[0].arn : var.existing_execution_role_arn
  role_name   = local.create_role ? aws_iam_role.lambda[0].name : null

  # Collect all secret ARNs (existing + created)
  all_secret_arns = concat(
    var.secrets_manager_arns,
    var.secret_config != null ? [aws_secretsmanager_secret.this[0].arn] : []
  )
}

# ==============================================================================
# Lambda Execution Role
# ==============================================================================

data "aws_iam_policy_document" "lambda_assume_role" {
  count = local.create_role ? 1 : 0

  statement {
    sid     = "LambdaAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  count = local.create_role ? 1 : 0

  name        = "${var.function_name}-execution-role"
  description = "Execution role for Lambda function ${var.function_name}"

  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role[0].json

  tags = var.tags
}

# ==============================================================================
# CloudWatch Logs Policy (Scoped to specific log group)
# ==============================================================================

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "cloudwatch_logs" {
  count = local.create_role ? 1 : 0

  statement {
    sid    = "CloudWatchLogsAccess"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "${aws_cloudwatch_log_group.lambda.arn}:*"
    ]
  }
}

resource "aws_iam_role_policy" "cloudwatch_logs" {
  count = local.create_role ? 1 : 0

  name   = "cloudwatch-logs"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.cloudwatch_logs[0].json
}

# ==============================================================================
# X-Ray Tracing Policy (CIS Lambda.7)
# ==============================================================================

data "aws_iam_policy_document" "xray" {
  count = local.create_role && var.tracing_config_mode == "Active" ? 1 : 0

  statement {
    sid    = "XRayTracingAccess"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "xray" {
  count = local.create_role && var.tracing_config_mode == "Active" ? 1 : 0

  name   = "xray-tracing"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.xray[0].json
}

# ==============================================================================
# Secrets Manager Policy (Scoped to specific secrets)
# ==============================================================================

data "aws_iam_policy_document" "secrets_manager" {
  count = local.create_role && length(local.all_secret_arns) > 0 ? 1 : 0

  statement {
    sid    = "SecretsManagerAccess"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = local.all_secret_arns
  }

  # KMS decrypt permission if CMK is used for secrets
  dynamic "statement" {
    for_each = var.secrets_kms_key_arn != null ? [1] : []
    content {
      sid    = "SecretsKMSDecrypt"
      effect = "Allow"
      actions = [
        "kms:Decrypt"
      ]
      resources = [var.secrets_kms_key_arn]
      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["secretsmanager.${data.aws_region.current.id}.amazonaws.com"]
      }
    }
  }
}

resource "aws_iam_role_policy" "secrets_manager" {
  count = local.create_role && length(local.all_secret_arns) > 0 ? 1 : 0

  name   = "secrets-manager"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.secrets_manager[0].json
}

# ==============================================================================
# VPC Execution Policy (Scoped ENI permissions)
# ==============================================================================

data "aws_iam_policy_document" "vpc" {
  count = local.create_role && var.vpc_config != null ? 1 : 0

  statement {
    sid    = "VPCNetworkInterfaceCreate"
    effect = "Allow"
    actions = [
      "ec2:CreateNetworkInterface"
    ]
    resources = flatten([
      ["arn:aws:ec2:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:network-interface/*"],
      [for subnet_id in var.vpc_config.subnet_ids : "arn:aws:ec2:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:subnet/${subnet_id}"],
      [for sg_id in var.vpc_config.security_group_ids : "arn:aws:ec2:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:security-group/${sg_id}"],
    ])
  }

  statement {
    sid    = "VPCNetworkInterfaceDescribe"
    effect = "Allow"
    actions = [
      "ec2:DescribeNetworkInterfaces"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "VPCNetworkInterfaceDelete"
    effect = "Allow"
    actions = [
      "ec2:DeleteNetworkInterface"
    ]
    resources = flatten([
      ["arn:aws:ec2:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:network-interface/*"],
      [for subnet_id in var.vpc_config.subnet_ids : "arn:aws:ec2:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:subnet/${subnet_id}"],
      [for sg_id in var.vpc_config.security_group_ids : "arn:aws:ec2:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:security-group/${sg_id}"],
    ])
  }
}

resource "aws_iam_role_policy" "vpc" {
  count = local.create_role && var.vpc_config != null ? 1 : 0

  name   = "vpc-execution"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.vpc[0].json
}

# ==============================================================================
# SQS Policy (for SQS trigger)
# ==============================================================================

data "aws_iam_policy_document" "sqs" {
  count = local.create_role && var.sqs_trigger.enabled ? 1 : 0

  statement {
    sid    = "SQSReceiveMessages"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]
    resources = [
      var.sqs_trigger.existing_queue_arn != null ? var.sqs_trigger.existing_queue_arn : aws_sqs_queue.trigger[0].arn
    ]
  }

  # If SQS uses KMS encryption
  dynamic "statement" {
    for_each = var.sqs_trigger.kms_key_id != null ? [1] : []
    content {
      sid    = "SQSKMSDecrypt"
      effect = "Allow"
      actions = [
        "kms:Decrypt"
      ]
      resources = [var.sqs_trigger.kms_key_id]
      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["sqs.${data.aws_region.current.id}.amazonaws.com"]
      }
    }
  }
}

resource "aws_iam_role_policy" "sqs" {
  count = local.create_role && var.sqs_trigger.enabled ? 1 : 0

  name   = "sqs-trigger"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.sqs[0].json
}

# ==============================================================================
# Dead Letter Queue Policy
# ==============================================================================

data "aws_iam_policy_document" "dlq" {
  count = local.create_role && var.dead_letter_config != null ? 1 : 0

  statement {
    sid    = "DeadLetterQueueAccess"
    effect = "Allow"
    actions = can(regex("^arn:aws:sqs:", var.dead_letter_config.target_arn)) ? [
      "sqs:SendMessage"
      ] : [
      "sns:Publish"
    ]
    resources = [var.dead_letter_config.target_arn]
  }
}

resource "aws_iam_role_policy" "dlq" {
  count = local.create_role && var.dead_letter_config != null ? 1 : 0

  name   = "dead-letter-queue"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.dlq[0].json
}

# ==============================================================================
# Additional Policy Attachments
# ==============================================================================

resource "aws_iam_role_policy_attachment" "additional" {
  for_each = local.create_role ? toset(var.additional_iam_policies) : toset([])

  role       = aws_iam_role.lambda[0].name
  policy_arn = each.value
}

resource "aws_iam_role_policy" "additional_inline" {
  for_each = local.create_role ? var.additional_inline_policies : {}

  name   = each.key
  role   = aws_iam_role.lambda[0].id
  policy = each.value
}
