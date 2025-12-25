# SNS Notifications Module Variables
# ====================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}

variable "kms_key_id" {
  description = "KMS key ID for SNS encryption (optional)"
  type        = string
  default     = ""
}

variable "success_email_addresses" {
  description = "Email addresses for success notifications"
  type        = list(string)
  default     = []
}

variable "error_email_addresses" {
  description = "Email addresses for error notifications"
  type        = list(string)
  default     = []
}

variable "alarm_email_addresses" {
  description = "Email addresses for alarm notifications"
  type        = list(string)
  default     = []
}

variable "error_webhook_url" {
  description = "HTTPS webhook URL for error notifications (e.g., Slack)"
  type        = string
  default     = ""
}

variable "alarm_webhook_url" {
  description = "HTTPS webhook URL for alarm notifications (e.g., PagerDuty)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
