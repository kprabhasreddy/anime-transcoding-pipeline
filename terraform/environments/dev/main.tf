# Development Environment Configuration
# ======================================
# This environment uses LocalStack-compatible settings for local development

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  # Uncomment for remote state (S3 backend)
  # backend "s3" {
  #   bucket         = "anime-transcoding-terraform-state"
  #   key            = "dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region

  # Uncomment for LocalStack
  # skip_credentials_validation = true
  # skip_metadata_api_check     = true
  # skip_requesting_account_id  = true
  # endpoints {
  #   s3             = "http://localhost:4566"
  #   dynamodb       = "http://localhost:4566"
  #   sns            = "http://localhost:4566"
  #   sqs            = "http://localhost:4566"
  #   lambda         = "http://localhost:4566"
  #   iam            = "http://localhost:4566"
  #   stepfunctions  = "http://localhost:4566"
  #   cloudwatch     = "http://localhost:4566"
  #   logs           = "http://localhost:4566"
  # }

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# -----------------------------------------------------------------------------
# Local Variables
# -----------------------------------------------------------------------------

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# -----------------------------------------------------------------------------
# KMS Encryption
# -----------------------------------------------------------------------------

module "kms" {
  source = "../../modules/kms-encryption"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.common_tags
}

# -----------------------------------------------------------------------------
# S3 Buckets
# -----------------------------------------------------------------------------

module "s3_buckets" {
  source = "../../modules/s3-buckets"

  project_name = var.project_name
  environment  = var.environment
  kms_key_arn  = module.kms.key_arn
  tags         = local.common_tags
}

# -----------------------------------------------------------------------------
# DynamoDB Tables
# -----------------------------------------------------------------------------

module "dynamodb" {
  source = "../../modules/dynamodb"

  project_name = var.project_name
  environment  = var.environment
  kms_key_arn  = module.kms.key_arn
  tags         = local.common_tags
}

# -----------------------------------------------------------------------------
# MediaConvert
# -----------------------------------------------------------------------------

module "mediaconvert" {
  source = "../../modules/mediaconvert"

  project_name          = var.project_name
  environment           = var.environment
  input_bucket_arn      = module.s3_buckets.input_bucket_arn
  output_bucket_arn     = module.s3_buckets.output_bucket_arn
  kms_key_arn           = module.kms.key_arn
  enable_kms            = true
  create_priority_queue = false
  tags                  = local.common_tags
}

# -----------------------------------------------------------------------------
# SNS Notifications
# -----------------------------------------------------------------------------

module "sns" {
  source = "../../modules/sns-notifications"

  project_name            = var.project_name
  environment             = var.environment
  kms_key_id              = module.kms.key_id
  success_email_addresses = var.notification_emails
  error_email_addresses   = var.notification_emails
  alarm_email_addresses   = var.notification_emails
  tags                    = local.common_tags
}

# -----------------------------------------------------------------------------
# Step Functions
# -----------------------------------------------------------------------------

module "step_functions" {
  source = "../../modules/step-functions"

  project_name             = var.project_name
  environment              = var.environment
  lambda_arns              = values(module.lambda.all_lambda_arns)
  input_validator_arn      = module.lambda.input_validator_arn
  job_submitter_arn        = module.lambda.job_submitter_arn
  output_validator_arn     = module.lambda.output_validator_arn
  notification_handler_arn = module.lambda.notification_handler_arn
  sns_topic_arns           = module.sns.all_topic_arns
  mediaconvert_queue_arn   = module.mediaconvert.queue_arn
  mediaconvert_role_arn    = module.mediaconvert.role_arn
  tags                     = local.common_tags
}

# -----------------------------------------------------------------------------
# Lambda Functions
# -----------------------------------------------------------------------------

module "lambda" {
  source = "../../modules/lambda-functions"

  project_name           = var.project_name
  environment            = var.environment
  lambda_zip_path        = var.lambda_zip_path
  layer_zip_path         = var.layer_zip_path
  input_bucket_name      = module.s3_buckets.input_bucket_name
  input_bucket_arn       = module.s3_buckets.input_bucket_arn
  output_bucket_name     = module.s3_buckets.output_bucket_name
  output_bucket_arn      = module.s3_buckets.output_bucket_arn
  dynamodb_table_name    = module.dynamodb.idempotency_table_name
  dynamodb_table_arn     = module.dynamodb.idempotency_table_arn
  mediaconvert_queue_arn = module.mediaconvert.queue_arn
  mediaconvert_role_arn  = module.mediaconvert.role_arn
  state_machine_arn      = module.step_functions.state_machine_arn
  kms_key_arn            = module.kms.key_arn
  enable_kms             = true
  sns_topic_arns         = module.sns.all_topic_arns
  success_sns_topic_arn  = module.sns.success_topic_arn
  error_sns_topic_arn    = module.sns.error_topic_arn
  enable_h265            = var.enable_h265
  enable_dash            = var.enable_dash
  mock_mode              = var.mock_mode
  log_level              = "DEBUG"
  tags                   = local.common_tags
}

# -----------------------------------------------------------------------------
# CloudWatch Monitoring
# -----------------------------------------------------------------------------

module "monitoring" {
  source = "../../modules/cloudwatch-monitoring"

  project_name = var.project_name
  environment  = var.environment
  lambda_function_names = [
    module.lambda.manifest_parser_name,
    module.lambda.input_validator_name,
    module.lambda.job_submitter_name,
    module.lambda.output_validator_name,
    module.lambda.notification_handler_name,
  ]
  state_machine_arn       = module.step_functions.state_machine_arn
  mediaconvert_queue_name = module.mediaconvert.queue_name
  alarm_sns_topic_arns    = [module.sns.alarms_topic_arn]
  tags                    = local.common_tags
}

# -----------------------------------------------------------------------------
# CloudFront Distribution (Optional for dev)
# -----------------------------------------------------------------------------

module "cloudfront" {
  source = "../../modules/cloudfront-distribution"
  count  = var.enable_cloudfront ? 1 : 0

  project_name                       = var.project_name
  environment                        = var.environment
  output_bucket_name                 = module.s3_buckets.output_bucket_name
  output_bucket_arn                  = module.s3_buckets.output_bucket_arn
  output_bucket_regional_domain_name = module.s3_buckets.output_bucket_regional_domain_name
  require_signed_urls                = false
  price_class                        = "PriceClass_100"
  tags                               = local.common_tags
}
