# ==============================================================================
# AWS Lambda Function
# Container-based Lambda with CIS benchmark compliance
# ==============================================================================

resource "aws_lambda_function" "this" {
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
    # Prevent accidental deletion of the function
    prevent_destroy = false

    # Ignore changes to image_uri if managed externally (CI/CD)
    # Uncomment if you want Terraform to not update the image
    # ignore_changes = [image_uri]
  }
}

# ==============================================================================
# Lambda Function URL (Alternative to API Gateway for simple use cases)
# Disabled by default - API Gateway provides more control
# ==============================================================================

# Uncomment to enable Lambda Function URL as an alternative to API Gateway
# resource "aws_lambda_function_url" "this" {
#   count = var.enable_function_url ? 1 : 0
#
#   function_name      = aws_lambda_function.this.function_name
#   authorization_type = "AWS_IAM"  # or "NONE" for public access (not recommended)
#
#   cors {
#     allow_origins = ["*"]
#     allow_methods = ["POST"]
#     allow_headers = ["Content-Type", "X-Hub-Signature-256"]
#     max_age       = 300
#   }
# }
