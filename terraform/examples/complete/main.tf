# ==============================================================================
# Complete Example: Lambda Function with All Features
# ==============================================================================
# This example demonstrates all features of the lambda-function module:
# - Container-based Lambda from ECR
# - API Gateway HTTP API trigger
# - SQS trigger with DLQ
# - EventBridge scheduled trigger
# - VPC connectivity
# - Secrets Manager integration
# - KMS encryption
# - X-Ray tracing
# ==============================================================================

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0, < 6.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "lambda-framework"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

# ==============================================================================
# Variables
# ==============================================================================

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "webhook-handler"
}

variable "image_tag" {
  description = "Docker image tag (typically git SHA from CI)"
  type        = string
  default     = "latest"
}

# ==============================================================================
# Data Sources
# ==============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ==============================================================================
# KMS Key for Encryption
# ==============================================================================

resource "aws_kms_key" "lambda" {
  description             = "KMS key for Lambda function encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccountAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${data.aws_region.current.name}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "${var.function_name}-kms"
    Environment = var.environment
  }
}

resource "aws_kms_alias" "lambda" {
  name          = "alias/${var.function_name}"
  target_key_id = aws_kms_key.lambda.key_id
}

# ==============================================================================
# VPC Configuration (Example using default VPC)
# In production, use dedicated private subnets
# ==============================================================================

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Note: In production, use private subnets with NAT Gateway
# This example uses default VPC subnets for demonstration
data "aws_subnet" "selected" {
  for_each = toset(slice(data.aws_subnets.private.ids, 0, min(2, length(data.aws_subnets.private.ids))))
  id       = each.value
}

resource "aws_security_group" "lambda" {
  name        = "${var.function_name}-sg"
  description = "Security group for Lambda function"
  vpc_id      = data.aws_vpc.default.id

  # Egress only - Lambda doesn't need ingress
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name        = "${var.function_name}-sg"
    Environment = var.environment
  }
}

# ==============================================================================
# ECR Repository (for container images)
# ==============================================================================

resource "aws_ecr_repository" "lambda" {
  name                 = var.function_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.lambda.arn
  }

  tags = {
    Name        = var.function_name
    Environment = var.environment
  }
}

resource "aws_ecr_lifecycle_policy" "lambda" {
  repository = aws_ecr_repository.lambda.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ==============================================================================
# Lambda Function Module
# ==============================================================================

module "lambda" {
  source = "../../modules/lambda-function"

  # Required parameters
  function_name = "${var.function_name}-${var.environment}"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.image_tag}"

  tags = {
    Name        = var.function_name
    Environment = var.environment
    Service     = "webhook-handler"
  }

  # Function configuration
  description   = "GitHub webhook handler for ${var.environment}"
  memory_size   = 512
  timeout       = 60
  architectures = ["arm64"]

  # Optional: Override container command
  image_config = {
    command = ["app.handler"]
  }

  # Environment variables
  environment_variables = {
    ENVIRONMENT     = var.environment
    LOG_LEVEL       = var.environment == "prod" ? "INFO" : "DEBUG"
    AWS_SECRET_NAME = "${var.function_name}/${var.environment}/secrets"
  }

  # VPC Configuration (CIS Lambda.3, Lambda.5)
  vpc_config = {
    subnet_ids         = [for s in data.aws_subnet.selected : s.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  # Secrets Manager - Create new secrets
  create_secrets = true
  secrets = {
    "${var.function_name}/${var.environment}/secrets" = {
      description = "Secrets for ${var.function_name} in ${var.environment}"
      kms_key_id  = aws_kms_key.lambda.arn
    }
  }
  secrets_kms_key_arn = aws_kms_key.lambda.arn

  # Logging
  log_retention_days    = var.environment == "prod" ? 90 : 14
  log_kms_key_arn       = aws_kms_key.lambda.arn
  log_format            = "JSON"
  application_log_level = var.environment == "prod" ? "INFO" : "DEBUG"
  system_log_level      = "WARN"

  # X-Ray tracing (CIS Lambda.7)
  tracing_config_mode = "Active"

  # Reserved concurrency (prevent runaway costs)
  reserved_concurrent_executions = var.environment == "prod" ? 100 : 10

  # API Gateway HTTP API trigger
  api_gateway = {
    enabled    = true
    stage_name = var.environment
    routes = [
      { method = "POST", path = "/webhook" },
      { method = "POST", path = "/webhook/github" }
    ]
    throttling = {
      burst_limit = var.environment == "prod" ? 500 : 50
      rate_limit  = var.environment == "prod" ? 200 : 20
    }
    cors = {
      allow_origins = var.environment == "prod" ? ["https://github.com"] : ["*"]
      allow_methods = ["POST", "OPTIONS"]
      allow_headers = ["Content-Type", "X-Hub-Signature-256", "X-GitHub-Event"]
    }
  }

  # SQS trigger (for async processing)
  sqs_trigger = {
    enabled                    = true
    batch_size                 = 10
    maximum_batching_window    = 5
    visibility_timeout_seconds = 300
    create_dlq                 = true
    dlq_max_receive_count      = 3
    kms_key_id                 = aws_kms_key.lambda.id
  }

  # EventBridge trigger (scheduled tasks)
  eventbridge_trigger = {
    enabled     = true
    schedule    = "rate(5 minutes)"
    description = "Scheduled invocation for health checks"
  }
}

# ==============================================================================
# Outputs
# ==============================================================================

output "function_arn" {
  description = "ARN of the Lambda function"
  value       = module.lambda.function_arn
}

output "function_name" {
  description = "Name of the Lambda function"
  value       = module.lambda.function_name
}

output "api_gateway_url" {
  description = "URL of the API Gateway endpoint"
  value       = module.lambda.api_gateway_url
}

output "webhook_endpoint" {
  description = "Full webhook endpoint URL"
  value       = module.lambda.api_gateway_url != null ? "${module.lambda.api_gateway_url}/webhook" : null
}

output "sqs_queue_url" {
  description = "URL of the SQS queue for async processing"
  value       = module.lambda.sqs_queue_url
}

output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.lambda.repository_url
}

output "execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = module.lambda.execution_role_arn
}

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = module.lambda.log_group_name
}

output "secret_arns" {
  description = "ARNs of secrets the Lambda has access to"
  value       = module.lambda.all_secret_arns
}
