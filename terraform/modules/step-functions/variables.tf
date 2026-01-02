# Step Functions Module Variables
# ================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "lambda_arns" {
  description = "List of Lambda function ARNs that Step Functions can invoke"
  type        = list(string)
}

variable "input_validator_arn" {
  description = "ARN of the input validator Lambda"
  type        = string
}

variable "job_submitter_arn" {
  description = "ARN of the job submitter Lambda"
  type        = string
}

variable "output_validator_arn" {
  description = "ARN of the output validator Lambda"
  type        = string
}

variable "notification_handler_arn" {
  description = "ARN of the notification handler Lambda"
  type        = string
}

variable "sns_topic_arns" {
  description = "List of SNS topic ARNs for notifications"
  type        = list(string)
  default     = []
}

variable "mediaconvert_queue_arn" {
  description = "ARN of the MediaConvert queue"
  type        = string
}

variable "mediaconvert_role_arn" {
  description = "ARN of the IAM role for MediaConvert"
  type        = string
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
