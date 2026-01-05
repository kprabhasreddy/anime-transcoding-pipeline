# MediaConvert Module Variables
# =============================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "input_bucket_arn" {
  description = "ARN of the input S3 bucket"
  type        = string
}

variable "output_bucket_arn" {
  description = "ARN of the output S3 bucket"
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

variable "create_priority_queue" {
  description = "Whether to create a priority queue for urgent jobs"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
