# DynamoDB Module Outputs
# ========================

output "idempotency_table_name" {
  description = "Name of the idempotency DynamoDB table"
  value       = aws_dynamodb_table.idempotency.name
}

output "idempotency_table_arn" {
  description = "ARN of the idempotency DynamoDB table"
  value       = aws_dynamodb_table.idempotency.arn
}

output "job_status_table_name" {
  description = "Name of the job status DynamoDB table"
  value       = aws_dynamodb_table.job_status.name
}

output "job_status_table_arn" {
  description = "ARN of the job status DynamoDB table"
  value       = aws_dynamodb_table.job_status.arn
}

output "all_table_arns" {
  description = "List of all DynamoDB table ARNs"
  value = [
    aws_dynamodb_table.idempotency.arn,
    aws_dynamodb_table.job_status.arn
  ]
}
