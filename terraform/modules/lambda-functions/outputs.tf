# Lambda Functions Module Outputs
# ================================

output "manifest_parser_arn" {
  description = "ARN of the manifest parser Lambda"
  value       = aws_lambda_function.manifest_parser.arn
}

output "manifest_parser_name" {
  description = "Name of the manifest parser Lambda"
  value       = aws_lambda_function.manifest_parser.function_name
}

output "input_validator_arn" {
  description = "ARN of the input validator Lambda"
  value       = aws_lambda_function.input_validator.arn
}

output "input_validator_name" {
  description = "Name of the input validator Lambda"
  value       = aws_lambda_function.input_validator.function_name
}

output "job_submitter_arn" {
  description = "ARN of the job submitter Lambda"
  value       = aws_lambda_function.job_submitter.arn
}

output "job_submitter_name" {
  description = "Name of the job submitter Lambda"
  value       = aws_lambda_function.job_submitter.function_name
}

output "output_validator_arn" {
  description = "ARN of the output validator Lambda"
  value       = aws_lambda_function.output_validator.arn
}

output "output_validator_name" {
  description = "Name of the output validator Lambda"
  value       = aws_lambda_function.output_validator.function_name
}

output "notification_handler_arn" {
  description = "ARN of the notification handler Lambda"
  value       = aws_lambda_function.notification_handler.arn
}

output "notification_handler_name" {
  description = "Name of the notification handler Lambda"
  value       = aws_lambda_function.notification_handler.function_name
}

output "execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_execution.arn
}

output "layer_arn" {
  description = "ARN of the shared Lambda layer"
  value       = aws_lambda_layer_version.shared.arn
}

output "all_lambda_arns" {
  description = "Map of all Lambda function ARNs"
  value = {
    manifest_parser      = aws_lambda_function.manifest_parser.arn
    input_validator      = aws_lambda_function.input_validator.arn
    job_submitter        = aws_lambda_function.job_submitter.arn
    output_validator     = aws_lambda_function.output_validator.arn
    notification_handler = aws_lambda_function.notification_handler.arn
  }
}

output "all_lambda_names" {
  description = "List of all Lambda function names"
  value = [
    aws_lambda_function.manifest_parser.function_name,
    aws_lambda_function.input_validator.function_name,
    aws_lambda_function.job_submitter.function_name,
    aws_lambda_function.output_validator.function_name,
    aws_lambda_function.notification_handler.function_name,
  ]
}
