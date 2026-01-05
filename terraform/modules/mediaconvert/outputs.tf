# MediaConvert Module Outputs
# ===========================

output "queue_arn" {
  description = "ARN of the main MediaConvert queue"
  value       = aws_media_convert_queue.main.arn
}

output "queue_name" {
  description = "Name of the main MediaConvert queue"
  value       = aws_media_convert_queue.main.name
}

output "priority_queue_arn" {
  description = "ARN of the priority MediaConvert queue (if created)"
  value       = var.create_priority_queue ? aws_media_convert_queue.priority[0].arn : null
}

output "role_arn" {
  description = "ARN of the MediaConvert IAM role"
  value       = aws_iam_role.mediaconvert.arn
}

output "role_name" {
  description = "Name of the MediaConvert IAM role"
  value       = aws_iam_role.mediaconvert.name
}

# Note: MediaConvert endpoint must be discovered at runtime via DescribeEndpoints API
# The Lambda functions handle this automatically
