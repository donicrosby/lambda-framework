# lambda-function

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.6.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 5.0.0 |
| <a name="requirement_null"></a> [null](#requirement\_null) | >= 4.0.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 5.0.0 |
| <a name="provider_null"></a> [null](#provider\_null) | >= 4.0.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_apigatewayv2_api.http](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/apigatewayv2_api) | resource |
| [aws_apigatewayv2_integration.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/apigatewayv2_integration) | resource |
| [aws_apigatewayv2_route.routes](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/apigatewayv2_route) | resource |
| [aws_apigatewayv2_stage.default](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/apigatewayv2_stage) | resource |
| [aws_cloudwatch_event_rule.trigger](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_target.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_target) | resource |
| [aws_cloudwatch_log_group.api_gateway](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_log_group.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_iam_role.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.additional_inline](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.cloudwatch_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.dlq](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.secrets_manager](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.sqs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.vpc](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.xray](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy_attachment.additional](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_lambda_event_source_mapping.sqs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_event_source_mapping) | resource |
| [aws_lambda_function.ci_managed](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_function.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_permission.api_gateway](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_lambda_permission.eventbridge](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_secretsmanager_secret.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret_version.this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_sqs_queue.dlq](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue) | resource |
| [aws_sqs_queue.trigger](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue) | resource |
| [aws_sqs_queue_policy.trigger](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue_policy) | resource |
| [null_resource.multi_az_check](https://registry.terraform.io/providers/hashicorp/null/latest/docs/resources/resource) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_iam_policy_document.cloudwatch_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.dlq](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.lambda_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.secrets_manager](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.sqs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.vpc](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.xray](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |
| [aws_subnet.selected](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/subnet) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_additional_iam_policies"></a> [additional\_iam\_policies](#input\_additional\_iam\_policies) | List of additional IAM policy ARNs to attach to the Lambda execution role. Only used when creating a new role. | `list(string)` | `[]` | no |
| <a name="input_additional_inline_policies"></a> [additional\_inline\_policies](#input\_additional\_inline\_policies) | Map of additional inline IAM policies to attach to the Lambda execution role. Key is policy name, value is policy JSON. | `map(string)` | `{}` | no |
| <a name="input_api_gateway"></a> [api\_gateway](#input\_api\_gateway) | API Gateway HTTP API configuration for the Lambda function. | <pre>object({<br/>    enabled    = bool<br/>    stage_name = optional(string, "prod")<br/>    routes = optional(list(object({<br/>      method = string<br/>      path   = string<br/>    })), [{ method = "POST", path = "/webhook" }])<br/>    throttling = optional(object({<br/>      burst_limit = optional(number, 100)<br/>      rate_limit  = optional(number, 50)<br/>    }), {})<br/>    cors = optional(object({<br/>      allow_origins     = optional(list(string), ["*"])<br/>      allow_methods     = optional(list(string), ["POST", "OPTIONS"])<br/>      allow_headers     = optional(list(string), ["Content-Type", "X-Hub-Signature-256"])<br/>      expose_headers    = optional(list(string), [])<br/>      max_age           = optional(number, 300)<br/>      allow_credentials = optional(bool, false)<br/>    }), null)<br/>  })</pre> | <pre>{<br/>  "enabled": false<br/>}</pre> | no |
| <a name="input_application_log_level"></a> [application\_log\_level](#input\_application\_log\_level) | Application log level for structured logging. Valid values are TRACE, DEBUG, INFO, WARN, ERROR, FATAL. | `string` | `"INFO"` | no |
| <a name="input_architectures"></a> [architectures](#input\_architectures) | Instruction set architecture for the Lambda function. Valid values are x86\_64 or arm64. | `list(string)` | <pre>[<br/>  "arm64"<br/>]</pre> | no |
| <a name="input_dead_letter_config"></a> [dead\_letter\_config](#input\_dead\_letter\_config) | Dead letter queue configuration for failed invocations. | <pre>object({<br/>    target_arn = string<br/>  })</pre> | `null` | no |
| <a name="input_description"></a> [description](#input\_description) | Description of the Lambda function. | `string` | `""` | no |
| <a name="input_environment_variables"></a> [environment\_variables](#input\_environment\_variables) | Environment variables for the Lambda function. | `map(string)` | `{}` | no |
| <a name="input_ephemeral_storage_size"></a> [ephemeral\_storage\_size](#input\_ephemeral\_storage\_size) | Size of the /tmp directory in MB. | `number` | `512` | no |
| <a name="input_eventbridge_trigger"></a> [eventbridge\_trigger](#input\_eventbridge\_trigger) | EventBridge trigger configuration for the Lambda function. | <pre>object({<br/>    enabled        = bool<br/>    schedule       = optional(string)<br/>    event_pattern  = optional(string)<br/>    description    = optional(string, "EventBridge rule for Lambda trigger")<br/>    event_bus_name = optional(string, "default")<br/>  })</pre> | <pre>{<br/>  "enabled": false<br/>}</pre> | no |
| <a name="input_existing_execution_role_arn"></a> [existing\_execution\_role\_arn](#input\_existing\_execution\_role\_arn) | ARN of an existing IAM role to use for Lambda execution. If not provided, a new role will be created with least-privilege permissions. | `string` | `null` | no |
| <a name="input_function_name"></a> [function\_name](#input\_function\_name) | Name of the Lambda function. Must be unique within the AWS account and region. | `string` | n/a | yes |
| <a name="input_image_config"></a> [image\_config](#input\_image\_config) | Container image configuration overrides. | <pre>object({<br/>    command           = optional(list(string))<br/>    entry_point       = optional(list(string))<br/>    working_directory = optional(string)<br/>  })</pre> | `null` | no |
| <a name="input_image_managed_externally"></a> [image\_managed\_externally](#input\_image\_managed\_externally) | If true, Terraform will ignore changes to image\_uri, allowing CI/CD pipelines to update the container image independently. When false, Terraform manages the full image lifecycle. | `bool` | `false` | no |
| <a name="input_image_uri"></a> [image\_uri](#input\_image\_uri) | ECR image URI for the Lambda function. Must be a valid ECR URI with tag or digest. | `string` | n/a | yes |
| <a name="input_log_format"></a> [log\_format](#input\_log\_format) | CloudWatch log format. Valid values are Text or JSON. | `string` | `"JSON"` | no |
| <a name="input_log_kms_key_arn"></a> [log\_kms\_key\_arn](#input\_log\_kms\_key\_arn) | ARN of KMS key for CloudWatch log encryption. If not provided, logs use AWS managed encryption. | `string` | `null` | no |
| <a name="input_log_retention_days"></a> [log\_retention\_days](#input\_log\_retention\_days) | CloudWatch log retention period in days. | `number` | `14` | no |
| <a name="input_memory_size"></a> [memory\_size](#input\_memory\_size) | Amount of memory in MB allocated to the Lambda function. | `number` | `256` | no |
| <a name="input_reserved_concurrent_executions"></a> [reserved\_concurrent\_executions](#input\_reserved\_concurrent\_executions) | Reserved concurrent executions for this function. Set to -1 for unreserved, 0 to disable. | `number` | `-1` | no |
| <a name="input_secret_config"></a> [secret\_config](#input\_secret\_config) | Configuration for a single Secrets Manager secret (JSON dictionary). Set to null to skip creation. | <pre>object({<br/>    name                    = string<br/>    description             = optional(string, "")<br/>    kms_key_id              = optional(string)<br/>    recovery_window_in_days = optional(number, 30)<br/>  })</pre> | `null` | no |
| <a name="input_secret_value"></a> [secret\_value](#input\_secret\_value) | Key-value pairs for the secret value. Will be JSON-encoded and stored as the secret version. Only used when secret\_config is also provided. Note: this value will be stored in Terraform state. | `map(string)` | `null` | no |
| <a name="input_secrets_kms_key_arn"></a> [secrets\_kms\_key\_arn](#input\_secrets\_kms\_key\_arn) | ARN of KMS key used to encrypt secrets. Required for kms:Decrypt permissions if secrets use a CMK. | `string` | `null` | no |
| <a name="input_secrets_manager_arns"></a> [secrets\_manager\_arns](#input\_secrets\_manager\_arns) | List of existing Secrets Manager secret ARNs to grant read access to. | `list(string)` | `[]` | no |
| <a name="input_sqs_trigger"></a> [sqs\_trigger](#input\_sqs\_trigger) | SQS trigger configuration for the Lambda function. | <pre>object({<br/>    enabled                    = bool<br/>    existing_queue_arn         = optional(string)<br/>    batch_size                 = optional(number, 10)<br/>    maximum_batching_window    = optional(number, 0)<br/>    visibility_timeout_seconds = optional(number, 300)<br/>    message_retention_seconds  = optional(number, 345600)<br/>    receive_wait_time_seconds  = optional(number, 20)<br/>    kms_key_id                 = optional(string)<br/>    create_dlq                 = optional(bool, true)<br/>    dlq_max_receive_count      = optional(number, 3)<br/>    function_response_types    = optional(list(string), ["ReportBatchItemFailures"])<br/>    maximum_concurrency        = optional(number)<br/>    filtering_criteria         = optional(string)<br/>  })</pre> | <pre>{<br/>  "enabled": false<br/>}</pre> | no |
| <a name="input_system_log_level"></a> [system\_log\_level](#input\_system\_log\_level) | System log level for Lambda runtime logging. Valid values are DEBUG, INFO, WARN. | `string` | `"WARN"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to apply to all resources. Must include 'Environment' key for CIS compliance. | `map(string)` | n/a | yes |
| <a name="input_timeout"></a> [timeout](#input\_timeout) | Maximum execution time for the Lambda function in seconds. | `number` | `30` | no |
| <a name="input_tracing_config_mode"></a> [tracing\_config\_mode](#input\_tracing\_config\_mode) | X-Ray tracing mode. Valid values are PassThrough or Active. CIS Lambda.7 recommends Active. | `string` | `"Active"` | no |
| <a name="input_vpc_config"></a> [vpc\_config](#input\_vpc\_config) | VPC configuration for the Lambda function. Set to null to run outside VPC. When enabled, subnets should span multiple AZs for CIS Lambda.5 compliance. | <pre>object({<br/>    subnet_ids         = list(string)<br/>    security_group_ids = list(string)<br/>  })</pre> | `null` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_all_secret_arns"></a> [all\_secret\_arns](#output\_all\_secret\_arns) | All secret ARNs the Lambda function has access to (created + existing) |
| <a name="output_api_gateway_execution_arn"></a> [api\_gateway\_execution\_arn](#output\_api\_gateway\_execution\_arn) | Execution ARN of the API Gateway HTTP API |
| <a name="output_api_gateway_id"></a> [api\_gateway\_id](#output\_api\_gateway\_id) | ID of the API Gateway HTTP API |
| <a name="output_api_gateway_stage_name"></a> [api\_gateway\_stage\_name](#output\_api\_gateway\_stage\_name) | Name of the API Gateway stage |
| <a name="output_api_gateway_url"></a> [api\_gateway\_url](#output\_api\_gateway\_url) | URL of the API Gateway HTTP API endpoint |
| <a name="output_created_secret_arns"></a> [created\_secret\_arns](#output\_created\_secret\_arns) | ARN of the secret created by this module |
| <a name="output_created_secret_version_id"></a> [created\_secret\_version\_id](#output\_created\_secret\_version\_id) | Version ID of the secret value created by this module |
| <a name="output_eventbridge_rule_arn"></a> [eventbridge\_rule\_arn](#output\_eventbridge\_rule\_arn) | ARN of the EventBridge rule |
| <a name="output_eventbridge_rule_name"></a> [eventbridge\_rule\_name](#output\_eventbridge\_rule\_name) | Name of the EventBridge rule |
| <a name="output_execution_role_arn"></a> [execution\_role\_arn](#output\_execution\_role\_arn) | ARN of the Lambda execution role |
| <a name="output_execution_role_name"></a> [execution\_role\_name](#output\_execution\_role\_name) | Name of the Lambda execution role (null if using existing role) |
| <a name="output_function_arn"></a> [function\_arn](#output\_function\_arn) | ARN of the Lambda function |
| <a name="output_function_name"></a> [function\_name](#output\_function\_name) | Name of the Lambda function |
| <a name="output_function_qualified_arn"></a> [function\_qualified\_arn](#output\_function\_qualified\_arn) | Qualified ARN of the Lambda function (includes version) |
| <a name="output_function_version"></a> [function\_version](#output\_function\_version) | Latest published version of the Lambda function |
| <a name="output_invoke_arn"></a> [invoke\_arn](#output\_invoke\_arn) | Invoke ARN of the Lambda function (for API Gateway) |
| <a name="output_log_group_arn"></a> [log\_group\_arn](#output\_log\_group\_arn) | ARN of the CloudWatch log group |
| <a name="output_log_group_name"></a> [log\_group\_name](#output\_log\_group\_name) | Name of the CloudWatch log group |
| <a name="output_sqs_dlq_arn"></a> [sqs\_dlq\_arn](#output\_sqs\_dlq\_arn) | ARN of the SQS dead letter queue |
| <a name="output_sqs_dlq_url"></a> [sqs\_dlq\_url](#output\_sqs\_dlq\_url) | URL of the SQS dead letter queue |
| <a name="output_sqs_queue_arn"></a> [sqs\_queue\_arn](#output\_sqs\_queue\_arn) | ARN of the SQS trigger queue |
| <a name="output_sqs_queue_url"></a> [sqs\_queue\_url](#output\_sqs\_queue\_url) | URL of the SQS trigger queue |
| <a name="output_subnet_availability_zones"></a> [subnet\_availability\_zones](#output\_subnet\_availability\_zones) | Availability zones of the configured subnets |
| <a name="output_vpc_config"></a> [vpc\_config](#output\_vpc\_config) | VPC configuration applied to the Lambda function |
<!-- END_TF_DOCS -->
