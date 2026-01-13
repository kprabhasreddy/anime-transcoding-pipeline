# Step Functions Module Outputs
# =============================

output "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  value       = aws_sfn_state_machine.transcoding_pipeline.arn
}

output "state_machine_name" {
  description = "Name of the Step Functions state machine"
  value       = aws_sfn_state_machine.transcoding_pipeline.name
}

output "execution_role_arn" {
  description = "ARN of the Step Functions execution role"
  value       = aws_iam_role.step_functions.arn
}

output "log_group_arn" {
  description = "ARN of the Step Functions CloudWatch log group"
  value       = aws_cloudwatch_log_group.step_functions.arn
}

output "mediaconvert_event_rule_arn" {
  description = "ARN of the MediaConvert EventBridge rule"
  value       = aws_cloudwatch_event_rule.mediaconvert_events.arn
}
