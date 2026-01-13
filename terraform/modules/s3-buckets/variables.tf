# S3 Buckets Module - Variables
# =============================

variable "project_name" {
  type        = string
  description = "Project name for resource naming"
  default     = "anime-transcode"
}

variable "environment" {
  type        = string
  description = "Environment name (dev, staging, prod)"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "kms_key_arn" {
  type        = string
  description = "KMS key ARN for S3 encryption (empty for AES256)"
  default     = ""
}

variable "enable_versioning" {
  type        = bool
  description = "Enable S3 versioning for audit trail"
  default     = true
}

variable "cors_allowed_origins" {
  type        = list(string)
  description = "Allowed origins for CORS (output bucket)"
  default     = ["*"]
}

variable "manifest_parser_lambda_arn" {
  type        = string
  description = "ARN of Lambda to trigger on manifest upload"
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Additional tags for resources"
  default     = {}
}
