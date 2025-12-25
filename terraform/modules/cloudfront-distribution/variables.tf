# CloudFront Distribution Module Variables
# ==========================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
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

variable "output_bucket_regional_domain_name" {
  description = "Regional domain name of the output S3 bucket"
  type        = string
}

variable "cloudfront_public_key_pem" {
  description = "PEM-encoded public key for signed URLs (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "require_signed_urls" {
  description = "Require signed URLs for content access"
  type        = bool
  default     = false
}

variable "domain_names" {
  description = "Custom domain names for the distribution (requires ACM certificate)"
  type        = list(string)
  default     = []
}

variable "acm_certificate_arn" {
  description = "ARN of ACM certificate for custom domain (must be in us-east-1)"
  type        = string
  default     = ""
}

variable "price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"

  validation {
    condition = contains([
      "PriceClass_100",
      "PriceClass_200",
      "PriceClass_All"
    ], var.price_class)
    error_message = "Invalid price class."
  }
}

variable "cors_allowed_origins" {
  description = "Allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}

variable "geo_restriction_type" {
  description = "Geo restriction type (none, whitelist, blacklist)"
  type        = string
  default     = "none"
}

variable "geo_restriction_locations" {
  description = "List of country codes for geo restriction"
  type        = list(string)
  default     = []
}

variable "access_log_bucket" {
  description = "S3 bucket for CloudFront access logs (optional)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
