# DynamoDB Module Outputs
# ========================

output "table_name" {
  description = "Name of the transcoding jobs DynamoDB table"
  value       = aws_dynamodb_table.transcoding_jobs.name
}

output "table_arn" {
  description = "ARN of the transcoding jobs DynamoDB table"
  value       = aws_dynamodb_table.transcoding_jobs.arn
}

# Backwards-compatible output names for existing code
output "idempotency_table_name" {
  description = "Name of the DynamoDB table (alias for table_name)"
  value       = aws_dynamodb_table.transcoding_jobs.name
}

output "idempotency_table_arn" {
  description = "ARN of the DynamoDB table (alias for table_arn)"
  value       = aws_dynamodb_table.transcoding_jobs.arn
}

# Legacy outputs - point to same table (single-table design)
output "job_status_table_name" {
  description = "Deprecated: Use table_name instead. Points to same consolidated table."
  value       = aws_dynamodb_table.transcoding_jobs.name
}

output "job_status_table_arn" {
  description = "Deprecated: Use table_arn instead. Points to same consolidated table."
  value       = aws_dynamodb_table.transcoding_jobs.arn
}

output "all_table_arns" {
  description = "List of all DynamoDB table ARNs (single table in v1.1+)"
  value = [
    aws_dynamodb_table.transcoding_jobs.arn
  ]
}
