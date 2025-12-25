# CloudWatch Monitoring Module Outputs
# =====================================

output "dashboard_arn" {
  description = "ARN of the CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_arn
}

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "alarm_arns" {
  description = "Map of alarm names to ARNs"
  value = merge(
    { for k, v in aws_cloudwatch_metric_alarm.lambda_errors : k => v.arn },
    {
      sfn_failures       = aws_cloudwatch_metric_alarm.sfn_failures.arn
      sfn_throttles      = aws_cloudwatch_metric_alarm.sfn_throttles.arn
      mediaconvert_errors = aws_cloudwatch_metric_alarm.mediaconvert_errors.arn
      pipeline_latency   = aws_cloudwatch_metric_alarm.pipeline_latency.arn
      validation_failures = aws_cloudwatch_metric_alarm.validation_failures.arn
      checksum_mismatches = aws_cloudwatch_metric_alarm.checksum_mismatches.arn
    }
  )
}
