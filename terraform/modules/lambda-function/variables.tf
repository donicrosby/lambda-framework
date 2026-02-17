# ==============================================================================
# Required Variables
# ==============================================================================

variable "function_name" {
  description = "Name of the Lambda function. Must be unique within the AWS account and region."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9-_]+$", var.function_name))
    error_message = "Function name must contain only alphanumeric characters, hyphens, and underscores."
  }

  validation {
    condition     = length(var.function_name) <= 64
    error_message = "Function name must be 64 characters or less."
  }
}

variable "image_uri" {
  description = "ECR image URI for the Lambda function. Must be a valid ECR URI with tag or digest."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/.+", var.image_uri))
    error_message = "Image URI must be a valid ECR repository URI."
  }
}

variable "tags" {
  description = "Tags to apply to all resources. Must include 'Environment' key for CIS compliance."
  type        = map(string)

  validation {
    condition     = contains(keys(var.tags), "Environment")
    error_message = "Tags must include 'Environment' key for CIS compliance (Lambda.6)."
  }
}

# ==============================================================================
# IAM Configuration
# ==============================================================================

variable "existing_execution_role_arn" {
  description = "ARN of an existing IAM role to use for Lambda execution. If not provided, a new role will be created with least-privilege permissions."
  type        = string
  default     = null

  validation {
    condition     = var.existing_execution_role_arn == null || can(regex("^arn:aws:iam::[0-9]+:role/.+", var.existing_execution_role_arn))
    error_message = "Must be a valid IAM role ARN or null."
  }
}

variable "additional_iam_policies" {
  description = "List of additional IAM policy ARNs to attach to the Lambda execution role. Only used when creating a new role."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for arn in var.additional_iam_policies : can(regex("^arn:aws:iam::", arn))])
    error_message = "All values must be valid IAM policy ARNs."
  }
}

variable "additional_inline_policies" {
  description = "Map of additional inline IAM policies to attach to the Lambda execution role. Key is policy name, value is policy JSON."
  type        = map(string)
  default     = {}
}

# ==============================================================================
# Lifecycle Configuration
# ==============================================================================

variable "image_managed_externally" {
  description = "If true, Terraform will ignore changes to image_uri, allowing CI/CD pipelines to update the container image independently. When false, Terraform manages the full image lifecycle."
  type        = bool
  default     = false
}

# ==============================================================================
# Lambda Function Configuration
# ==============================================================================

variable "description" {
  description = "Description of the Lambda function."
  type        = string
  default     = ""
}

variable "memory_size" {
  description = "Amount of memory in MB allocated to the Lambda function."
  type        = number
  default     = 256

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240
    error_message = "Memory size must be between 128 MB and 10240 MB."
  }
}

variable "timeout" {
  description = "Maximum execution time for the Lambda function in seconds."
  type        = number
  default     = 30

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 900
    error_message = "Timeout must be between 1 and 900 seconds."
  }
}

variable "reserved_concurrent_executions" {
  description = "Reserved concurrent executions for this function. Set to -1 for unreserved, 0 to disable."
  type        = number
  default     = -1

  validation {
    condition     = var.reserved_concurrent_executions >= -1
    error_message = "Reserved concurrent executions must be -1 (unreserved) or >= 0."
  }
}

variable "architectures" {
  description = "Instruction set architecture for the Lambda function. Valid values are x86_64 or arm64."
  type        = list(string)
  default     = ["arm64"]

  validation {
    condition     = length(var.architectures) == 1 && contains(["x86_64", "arm64"], var.architectures[0])
    error_message = "Architecture must be either x86_64 or arm64."
  }
}

variable "image_config" {
  description = "Container image configuration overrides."
  type = object({
    command           = optional(list(string))
    entry_point       = optional(list(string))
    working_directory = optional(string)
  })
  default = null
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "ephemeral_storage_size" {
  description = "Size of the /tmp directory in MB."
  type        = number
  default     = 512

  validation {
    condition     = var.ephemeral_storage_size >= 512 && var.ephemeral_storage_size <= 10240
    error_message = "Ephemeral storage size must be between 512 MB and 10240 MB."
  }
}

# ==============================================================================
# Tracing Configuration (CIS Lambda.7)
# ==============================================================================

variable "tracing_config_mode" {
  description = "X-Ray tracing mode. Valid values are PassThrough or Active. CIS Lambda.7 recommends Active."
  type        = string
  default     = "Active"

  validation {
    condition     = contains(["PassThrough", "Active"], var.tracing_config_mode)
    error_message = "Tracing mode must be either PassThrough or Active."
  }
}

# ==============================================================================
# VPC Configuration (CIS Lambda.3, Lambda.5)
# ==============================================================================

variable "vpc_config" {
  description = "VPC configuration for the Lambda function. Set to null to run outside VPC. When enabled, subnets should span multiple AZs for CIS Lambda.5 compliance."
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null

  validation {
    condition     = var.vpc_config == null || (length(var.vpc_config.subnet_ids) >= 2 && length(var.vpc_config.security_group_ids) >= 1)
    error_message = "VPC config requires at least 2 subnets (for multi-AZ, CIS Lambda.5) and 1 security group."
  }
}

# ==============================================================================
# Secrets Manager Configuration
# ==============================================================================

variable "secrets_manager_arns" {
  description = "List of existing Secrets Manager secret ARNs to grant read access to."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for arn in var.secrets_manager_arns : can(regex("^arn:aws:secretsmanager:", arn))])
    error_message = "All values must be valid Secrets Manager ARNs."
  }
}

variable "secret_config" {
  description = "Configuration for a single Secrets Manager secret (JSON dictionary). Set to null to skip creation."
  type = object({
    name                    = string
    description             = optional(string, "")
    kms_key_id              = optional(string)
    recovery_window_in_days = optional(number, 30)
  })
  default = null
}

variable "secret_value" {
  description = "Key-value pairs for the secret value. Will be JSON-encoded and stored as the secret version. Only used when secret_config is also provided. Note: this value will be stored in Terraform state."
  type        = map(string)
  default     = null
  sensitive   = true
}

variable "secrets_kms_key_arn" {
  description = "ARN of KMS key used to encrypt secrets. Required for kms:Decrypt permissions if secrets use a CMK."
  type        = string
  default     = null
}

# ==============================================================================
# Logging Configuration
# ==============================================================================

variable "log_retention_days" {
  description = "CloudWatch log retention period in days."
  type        = number
  default     = 14

  validation {
    condition     = contains([0, 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "Log retention days must be a valid CloudWatch Logs retention value."
  }
}

variable "log_kms_key_arn" {
  description = "ARN of KMS key for CloudWatch log encryption. If not provided, logs use AWS managed encryption."
  type        = string
  default     = null
}

variable "log_format" {
  description = "CloudWatch log format. Valid values are Text or JSON."
  type        = string
  default     = "JSON"

  validation {
    condition     = contains(["Text", "JSON"], var.log_format)
    error_message = "Log format must be either Text or JSON."
  }
}

variable "application_log_level" {
  description = "Application log level for structured logging. Valid values are TRACE, DEBUG, INFO, WARN, ERROR, FATAL."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"], var.application_log_level)
    error_message = "Application log level must be one of: TRACE, DEBUG, INFO, WARN, ERROR, FATAL."
  }
}

variable "system_log_level" {
  description = "System log level for Lambda runtime logging. Valid values are DEBUG, INFO, WARN."
  type        = string
  default     = "WARN"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARN"], var.system_log_level)
    error_message = "System log level must be one of: DEBUG, INFO, WARN."
  }
}

# ==============================================================================
# Dead Letter Queue Configuration
# ==============================================================================

variable "dead_letter_config" {
  description = "Dead letter queue configuration for failed invocations."
  type = object({
    target_arn = string
  })
  default = null

  validation {
    condition     = var.dead_letter_config == null || can(regex("^arn:aws:(sqs|sns):", var.dead_letter_config.target_arn))
    error_message = "Dead letter target must be an SQS queue or SNS topic ARN."
  }
}

# ==============================================================================
# API Gateway HTTP API Trigger
# ==============================================================================

variable "api_gateway" {
  description = "API Gateway HTTP API configuration for the Lambda function."
  type = object({
    enabled    = bool
    stage_name = optional(string, "prod")
    routes = optional(list(object({
      method = string
      path   = string
    })), [{ method = "POST", path = "/webhook" }])
    throttling = optional(object({
      burst_limit = optional(number, 100)
      rate_limit  = optional(number, 50)
    }), {})
    cors = optional(object({
      allow_origins     = optional(list(string), ["*"])
      allow_methods     = optional(list(string), ["POST", "OPTIONS"])
      allow_headers     = optional(list(string), ["Content-Type", "X-Hub-Signature-256"])
      expose_headers    = optional(list(string), [])
      max_age           = optional(number, 300)
      allow_credentials = optional(bool, false)
    }), null)
  })
  default = {
    enabled = false
  }
}

# ==============================================================================
# SQS Trigger
# ==============================================================================

variable "sqs_trigger" {
  description = "SQS trigger configuration for the Lambda function."
  type = object({
    enabled                    = bool
    existing_queue_arn         = optional(string)
    batch_size                 = optional(number, 10)
    maximum_batching_window    = optional(number, 0)
    visibility_timeout_seconds = optional(number, 300)
    message_retention_seconds  = optional(number, 345600)
    receive_wait_time_seconds  = optional(number, 20)
    kms_key_id                 = optional(string)
    create_dlq                 = optional(bool, true)
    dlq_max_receive_count      = optional(number, 3)
    function_response_types    = optional(list(string), ["ReportBatchItemFailures"])
    maximum_concurrency        = optional(number)
    filtering_criteria         = optional(string)
  })
  default = {
    enabled = false
  }

  validation {
    condition     = !var.sqs_trigger.enabled || var.sqs_trigger.batch_size >= 1 && var.sqs_trigger.batch_size <= 10000
    error_message = "SQS batch size must be between 1 and 10000."
  }
}

# ==============================================================================
# EventBridge Trigger
# ==============================================================================

variable "eventbridge_trigger" {
  description = "EventBridge trigger configuration for the Lambda function."
  type = object({
    enabled        = bool
    schedule       = optional(string)
    event_pattern  = optional(string)
    description    = optional(string, "EventBridge rule for Lambda trigger")
    event_bus_name = optional(string, "default")
  })
  default = {
    enabled = false
  }

  validation {
    condition     = !var.eventbridge_trigger.enabled || var.eventbridge_trigger.schedule != null || var.eventbridge_trigger.event_pattern != null
    error_message = "EventBridge trigger requires either a schedule expression or event pattern."
  }
}
