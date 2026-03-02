# ==============================================================================
# AWS Lambda Function
# Container-based Lambda with CIS benchmark compliance
#
# Two resource definitions are used (dual-resource pattern) because Terraform
# lifecycle blocks only accept literal values — variables and expressions are
# not supported. The var.image_managed_externally toggle controls which
# resource is created; the other is skipped via count.
# ==============================================================================

locals {
  # Unified reference regardless of which resource variant is active
  lambda_function = var.image_managed_externally ? aws_lambda_function.ci_managed[0] : aws_lambda_function.this[0]
}

# ------------------------------------------------------------------------------
# Terraform-managed image (default)
# Created when var.image_managed_externally = false
# ------------------------------------------------------------------------------

resource "aws_lambda_function" "this" {
  count = var.image_managed_externally ? 0 : 1

  function_name = var.function_name
  description   = var.description
  role          = local.role_arn
  package_type  = "Image"
  image_uri     = var.image_uri

  # Performance configuration
  memory_size = var.memory_size
  timeout     = var.timeout

  # Architecture (arm64 recommended for cost/performance)
  architectures = var.architectures

  # Reserved concurrent executions (helps prevent runaway costs)
  reserved_concurrent_executions = var.reserved_concurrent_executions

  # Ephemeral storage configuration
  ephemeral_storage {
    size = var.ephemeral_storage_size
  }

  # Container image configuration overrides
  dynamic "image_config" {
    for_each = var.image_config != null ? [var.image_config] : []
    content {
      command           = image_config.value.command
      entry_point       = image_config.value.entry_point
      working_directory = image_config.value.working_directory
    }
  }

  # Environment variables
  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }

  # VPC configuration (CIS Lambda.3, Lambda.5)
  dynamic "vpc_config" {
    for_each = var.vpc_config != null ? [var.vpc_config] : []
    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  # X-Ray tracing (CIS Lambda.7)
  tracing_config {
    mode = var.tracing_config_mode
  }

  # Advanced logging configuration
  logging_config {
    log_format            = var.log_format
    application_log_level = var.log_format == "JSON" ? var.application_log_level : null
    system_log_level      = var.log_format == "JSON" ? var.system_log_level : null
    log_group             = aws_cloudwatch_log_group.lambda.name
  }

  # Dead letter queue configuration
  dynamic "dead_letter_config" {
    for_each = var.dead_letter_config != null ? [var.dead_letter_config] : []
    content {
      target_arn = dead_letter_config.value.target_arn
    }
  }

  # Tags (CIS Lambda.6)
  tags = merge(var.tags, {
    Name = var.function_name
  })
}

# ------------------------------------------------------------------------------
# CI/CD-managed image
# Created when var.image_managed_externally = true
# Ignores changes to image_uri so CI/CD pipelines can update it independently
# ------------------------------------------------------------------------------

resource "aws_lambda_function" "ci_managed" {
  count = var.image_managed_externally ? 1 : 0

  function_name = var.function_name
  description   = var.description
  role          = local.role_arn
  package_type  = "Image"
  image_uri     = var.image_uri

  # Performance configuration
  memory_size = var.memory_size
  timeout     = var.timeout

  # Architecture (arm64 recommended for cost/performance)
  architectures = var.architectures

  # Reserved concurrent executions (helps prevent runaway costs)
  reserved_concurrent_executions = var.reserved_concurrent_executions

  # Ephemeral storage configuration
  ephemeral_storage {
    size = var.ephemeral_storage_size
  }

  # Container image configuration overrides
  dynamic "image_config" {
    for_each = var.image_config != null ? [var.image_config] : []
    content {
      command           = image_config.value.command
      entry_point       = image_config.value.entry_point
      working_directory = image_config.value.working_directory
    }
  }

  # Environment variables
  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }

  # VPC configuration (CIS Lambda.3, Lambda.5)
  dynamic "vpc_config" {
    for_each = var.vpc_config != null ? [var.vpc_config] : []
    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  # X-Ray tracing (CIS Lambda.7)
  tracing_config {
    mode = var.tracing_config_mode
  }

  # Advanced logging configuration
  logging_config {
    log_format            = var.log_format
    application_log_level = var.log_format == "JSON" ? var.application_log_level : null
    system_log_level      = var.log_format == "JSON" ? var.system_log_level : null
    log_group             = aws_cloudwatch_log_group.lambda.name
  }

  # Dead letter queue configuration
  dynamic "dead_letter_config" {
    for_each = var.dead_letter_config != null ? [var.dead_letter_config] : []
    content {
      target_arn = dead_letter_config.value.target_arn
    }
  }

  # Tags (CIS Lambda.6)
  tags = merge(var.tags, {
    Name = var.function_name
  })

  lifecycle {
    ignore_changes = [image_uri]
  }
}
