# Development Environment Variables
# ==================================

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "anime-transcoding"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "lambda_zip_path" {
  description = "Path to Lambda deployment package"
  type        = string
  default     = "../../../dist/lambda-deployment.zip"
}

variable "layer_zip_path" {
  description = "Path to Lambda layer package"
  type        = string
  default     = "../../../dist/lambda-layer.zip"
}

variable "notification_emails" {
  description = "Email addresses for notifications"
  type        = list(string)
  default     = []
}

variable "enable_h265" {
  description = "Enable H.265/HEVC encoding"
  type        = bool
  default     = true
}

variable "enable_dash" {
  description = "Enable DASH output"
  type        = bool
  default     = true
}

variable "mock_mode" {
  description = "Enable mock mode (no real MediaConvert)"
  type        = bool
  default     = true
}

variable "enable_cloudfront" {
  description = "Create CloudFront distribution"
  type        = bool
  default     = false
}
