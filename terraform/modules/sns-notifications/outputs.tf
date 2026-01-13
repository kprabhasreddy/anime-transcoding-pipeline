# SNS Notifications Module Outputs
# =================================

output "success_topic_arn" {
  description = "ARN of the success notifications topic"
  value       = aws_sns_topic.success.arn
}

output "success_topic_name" {
  description = "Name of the success notifications topic"
  value       = aws_sns_topic.success.name
}

output "error_topic_arn" {
  description = "ARN of the error notifications topic"
  value       = aws_sns_topic.error.arn
}

output "error_topic_name" {
  description = "Name of the error notifications topic"
  value       = aws_sns_topic.error.name
}

output "alarms_topic_arn" {
  description = "ARN of the alarms notifications topic"
  value       = aws_sns_topic.alarms.arn
}

output "alarms_topic_name" {
  description = "Name of the alarms notifications topic"
  value       = aws_sns_topic.alarms.name
}

output "all_topic_arns" {
  description = "List of all SNS topic ARNs"
  value = [
    aws_sns_topic.success.arn,
    aws_sns_topic.error.arn,
    aws_sns_topic.alarms.arn
  ]
}
