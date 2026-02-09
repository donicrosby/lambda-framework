# ==============================================================================
# VPC Configuration for Lambda Function
# Optional VPC connectivity for accessing private resources (RDS, ElastiCache, etc.)
# CIS Lambda.3: Lambda functions should be deployed in a VPC
# CIS Lambda.5: VPC Lambda functions should operate in multiple AZs
# ==============================================================================

# Note: The VPC configuration is handled directly in the Lambda function resource
# (main.tf) via the vpc_config block. This file contains validation and
# documentation for VPC-related requirements.

# The IAM permissions for VPC (CreateNetworkInterface, DeleteNetworkInterface,
# DescribeNetworkInterfaces) are defined in iam.tf when vpc_config is provided.

# ==============================================================================
# VPC Configuration Validation
# ==============================================================================

# The validation in variables.tf ensures:
# - At least 2 subnets are provided for multi-AZ deployment (CIS Lambda.5)
# - At least 1 security group is provided

# ==============================================================================
# Best Practices for VPC-connected Lambda Functions
# ==============================================================================

# 1. Use private subnets with NAT Gateway for internet access
# 2. Security groups should follow least-privilege (only allow required egress)
# 3. Consider VPC endpoints for AWS services to avoid NAT Gateway costs
# 4. Subnets should be in different Availability Zones for high availability
# 5. Reserve sufficient IP addresses in subnets for Lambda ENIs

# ==============================================================================
# Data source to validate subnets are in different AZs (optional enhanced check)
# ==============================================================================

data "aws_subnet" "selected" {
  for_each = var.vpc_config != null ? toset(var.vpc_config.subnet_ids) : toset([])

  id = each.value
}

locals {
  # Get unique AZs from the provided subnets
  subnet_azs = var.vpc_config != null ? distinct([for subnet in data.aws_subnet.selected : subnet.availability_zone]) : []

  # Validate that subnets span multiple AZs for CIS Lambda.5
  multi_az_validated = var.vpc_config == null || length(local.subnet_azs) >= 2
}

# This check will cause a plan failure if subnets don't span multiple AZs
resource "null_resource" "multi_az_check" {
  count = var.vpc_config != null ? 1 : 0

  lifecycle {
    precondition {
      condition     = local.multi_az_validated
      error_message = "CIS Lambda.5: VPC Lambda functions must operate in multiple Availability Zones. Provided subnets are in the same AZ."
    }
  }
}
