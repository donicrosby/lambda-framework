# Lambda Framework Terraform Module

This Terraform/OpenTofu module deploys container-based AWS Lambda functions with CIS benchmark compliance, least-privilege IAM, and configurable triggers.

## Features

- **Container-based Lambda**: Deploy Lambda functions from pre-built ECR container images
- **CIS Benchmark Compliance**: Implements Lambda.1, Lambda.3, Lambda.5, Lambda.6, and Lambda.7 controls
- **Least-Privilege IAM**: Scoped permissions for CloudWatch Logs, Secrets Manager, VPC, X-Ray
- **Multiple Triggers**: API Gateway REST API (proxy pass-through), SQS, and EventBridge
- **Optional VPC Support**: Deploy Lambda in VPC for private resource access
- **Secrets Manager Integration**: Create or reference existing secrets
- **KMS Encryption**: Optional encryption for logs, secrets, and SQS

## CIS Benchmark Compliance

| Control | Description | Implementation |
|---------|-------------|----------------|
| Lambda.1 | Prohibit public access | `source_arn` conditions on all permissions |
| Lambda.3 | VPC placement | Optional `vpc_config` variable |
| Lambda.5 | Multi-AZ deployment | Requires 2+ subnets in different AZs |
| Lambda.6 | Proper tagging | Required `tags` with `Environment` key |
| Lambda.7 | X-Ray tracing | Enabled by default (`tracing_config_mode = "Active"`) |

## Prerequisites

1. **OpenTofu/Terraform**: Version 1.6.0 or later
2. **AWS Provider**: Version 5.x
3. **Pre-built Container Image**: Image must exist in ECR before deployment
4. **AWS Credentials**: Configured with appropriate permissions

## Usage

### Minimal Example

```hcl
module "lambda" {
  source = "./modules/lambda-function"

  function_name = "my-webhook-handler"
  image_uri     = "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0"

  tags = {
    Environment = "prod"
    Service     = "webhooks"
  }
}
```

### With API Gateway

```hcl
module "lambda" {
  source = "./modules/lambda-function"

  function_name = "github-webhook"
  image_uri     = "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0"

  tags = {
    Environment = "prod"
  }

  api_gateway = {
    enabled    = true
    stage_name = "prod"
    throttling = {
      burst_limit = 100
      rate_limit  = 50
    }
  }
}

output "webhook_url" {
  value = module.lambda.api_gateway_url
}
```

### With VPC and Secrets Manager

```hcl
module "lambda" {
  source = "./modules/lambda-function"

  function_name = "vpc-lambda"
  image_uri     = "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0"

  tags = {
    Environment = "prod"
  }

  # VPC Configuration (CIS Lambda.3, Lambda.5)
  vpc_config = {
    subnet_ids         = ["subnet-abc123", "subnet-def456"]  # Must be in different AZs
    security_group_ids = ["sg-xyz789"]
  }

  # Reference existing secrets
  secrets_manager_arns = [
    "arn:aws:secretsmanager:us-east-1:123456789:secret:my-app/prod"
  ]
  secrets_kms_key_arn = "arn:aws:kms:us-east-1:123456789:key/abc123"

  environment_variables = {
    AWS_SECRET_NAME = "my-app/prod"
    ENVIRONMENT     = "prod"
  }
}
```

### With SQS Trigger

```hcl
module "lambda" {
  source = "./modules/lambda-function"

  function_name = "queue-processor"
  image_uri     = "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0"

  tags = {
    Environment = "prod"
  }

  sqs_trigger = {
    enabled                = true
    batch_size             = 10
    maximum_batching_window = 5
    create_dlq             = true
    dlq_max_receive_count  = 3
  }
}

output "queue_url" {
  value = module.lambda.sqs_queue_url
}
```

### Using Existing IAM Role

```hcl
module "lambda" {
  source = "./modules/lambda-function"

  function_name = "custom-role-lambda"
  image_uri     = "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0"

  tags = {
    Environment = "prod"
  }

  # Use existing IAM role instead of creating a new one
  existing_execution_role_arn = "arn:aws:iam::123456789:role/my-custom-lambda-role"
}
```

## CI/CD Integration

Since Env0 doesn't support Docker builds during deployment, container images must be pre-built in CI (e.g., GitHub Actions).

### GitHub Actions Workflow

Add this job to your `.github/workflows/ci.yml`:

```yaml
build-and-push:
  runs-on: ubuntu-latest
  permissions:
    id-token: write
    contents: read
  steps:
    - uses: actions/checkout@v4
    
    - uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
        aws-region: us-east-1
    
    - uses: aws-actions/amazon-ecr-login@v2
      id: login-ecr
    
    - name: Build and push
      env:
        ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
        ECR_REPOSITORY: my-lambda-app
        IMAGE_TAG: ${{ github.sha }}
      run: |
        docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
        docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
        
        # Also tag as latest for dev environments
        docker tag $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG $ECR_REGISTRY/$ECR_REPOSITORY:latest
        docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest
```

### Env0 Configuration

In your Env0 environment, set the `image_tag` variable to the git SHA:

```hcl
variable "image_tag" {
  description = "Docker image tag from CI"
  type        = string
}

module "lambda" {
  source = "./modules/lambda-function"
  
  image_uri = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  # ...
}
```

## Input Variables

### Required

| Name | Description | Type |
|------|-------------|------|
| `function_name` | Name of the Lambda function | `string` |
| `image_uri` | ECR image URI (must be pre-built) | `string` |
| `tags` | Tags including required `Environment` key | `map(string)` |

### Optional - Function Configuration

| Name | Description | Type | Default |
|------|-------------|------|---------|
| `description` | Function description | `string` | `""` |
| `memory_size` | Memory allocation (MB) | `number` | `256` |
| `timeout` | Timeout (seconds) | `number` | `30` |
| `architectures` | CPU architecture | `list(string)` | `["arm64"]` |
| `reserved_concurrent_executions` | Reserved concurrency | `number` | `-1` |
| `environment_variables` | Environment variables | `map(string)` | `{}` |

### Optional - IAM

| Name | Description | Type | Default |
|------|-------------|------|---------|
| `existing_execution_role_arn` | Use existing IAM role | `string` | `null` |
| `additional_iam_policies` | Additional policy ARNs | `list(string)` | `[]` |
| `additional_inline_policies` | Additional inline policies | `map(string)` | `{}` |

### Optional - VPC

| Name | Description | Type | Default |
|------|-------------|------|---------|
| `vpc_config` | VPC configuration | `object` | `null` |

### Optional - Secrets

| Name | Description | Type | Default |
|------|-------------|------|---------|
| `secrets_manager_arns` | Existing secret ARNs | `list(string)` | `[]` |
| `create_secrets` | Create new secrets | `bool` | `false` |
| `secrets` | Secrets to create | `map(object)` | `{}` |
| `secrets_kms_key_arn` | KMS key for secrets | `string` | `null` |

### Optional - Triggers

See `variables.tf` for complete trigger configuration options.

## Outputs

| Name | Description |
|------|-------------|
| `function_arn` | Lambda function ARN |
| `function_name` | Lambda function name |
| `invoke_arn` | Invoke ARN for API Gateway |
| `execution_role_arn` | IAM execution role ARN |
| `api_gateway_url` | API Gateway endpoint URL |
| `sqs_queue_url` | SQS trigger queue URL |
| `log_group_name` | CloudWatch log group name |
| `created_secret_arns` | ARNs of created secrets |

## Examples

- [`examples/complete`](examples/complete): Full example with all features enabled

## Module Structure

```
terraform/
├── modules/
│   └── lambda-function/
│       ├── main.tf           # Lambda function resource
│       ├── variables.tf      # Input variables
│       ├── outputs.tf        # Module outputs
│       ├── iam.tf            # IAM role and policies
│       ├── logging.tf        # CloudWatch log group
│       ├── triggers.tf       # API Gateway, SQS, EventBridge
│       ├── secrets.tf        # Secrets Manager
│       ├── vpc.tf            # VPC configuration
│       └── versions.tf       # Provider requirements
├── examples/
│   └── complete/             # Complete example
└── README.md
```

## Security Considerations

1. **Secrets**: Never store secret values in Terraform state. Create secrets through the module, then set values via AWS Console or CLI.

2. **IAM**: The module creates least-privilege roles. Add only necessary permissions via `additional_iam_policies`.

3. **VPC**: When using VPC, ensure subnets have NAT Gateway for internet access and use VPC endpoints for AWS services.

4. **KMS**: Use customer-managed KMS keys for CloudWatch logs and Secrets Manager in production.

5. **Container Images**: Enable ECR image scanning and use immutable tags.

## License

See [LICENSE](../LICENSE) for details.
