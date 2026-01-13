# Lambda Functions Module Variables
# ==================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "lambda_zip_path" {
  description = "Path to the Lambda deployment package"
  type        = string
}

variable "layer_zip_path" {
  description = "Path to the Lambda layer package"
  type        = string
}

variable "input_bucket_name" {
  description = "Name of the input S3 bucket"
  type        = string
}

variable "input_bucket_arn" {
  description = "ARN of the input S3 bucket"
  type        = string
}

variable "output_bucket_name" {
  description = "Name of the output S3 bucket"
  type        = string
}

variable "output_bucket_arn" {
  description = "ARN of the output S3 bucket"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table for idempotency"
  type        = string
}

variable "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  type        = string
}

variable "mediaconvert_queue_arn" {
  description = "ARN of the MediaConvert queue"
  type        = string
}

variable "mediaconvert_role_arn" {
  description = "ARN of the MediaConvert IAM role"
  type        = string
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the KMS key for encryption (optional)"
  type        = string
  default     = ""
}

variable "enable_kms" {
  description = "Whether KMS encryption is enabled"
  type        = bool
  default     = false
}

variable "sns_topic_arns" {
  description = "List of SNS topic ARNs for notifications"
  type        = list(string)
  default     = []
}

variable "success_sns_topic_arn" {
  description = "ARN of the SNS topic for success notifications"
  type        = string
  default     = ""
}

variable "error_sns_topic_arn" {
  description = "ARN of the SNS topic for error notifications"
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 14
}

variable "log_level" {
  description = "Log level for Lambda functions"
  type        = string
  default     = "INFO"
}

variable "enable_h265" {
  description = "Enable H.265/HEVC encoding"
  type        = bool
  default     = true
}

variable "enable_dash" {
  description = "Enable DASH output in addition to HLS"
  type        = bool
  default     = true
}

variable "mock_mode" {
  description = "Enable mock mode for demos (no actual MediaConvert calls)"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
