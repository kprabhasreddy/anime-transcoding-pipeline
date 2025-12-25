# Development Environment Outputs
# ================================

output "input_bucket_name" {
  description = "Name of the input S3 bucket"
  value       = module.s3_buckets.input_bucket_name
}

output "output_bucket_name" {
  description = "Name of the output S3 bucket"
  value       = module.s3_buckets.output_bucket_name
}

output "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  value       = module.step_functions.state_machine_arn
}

output "mediaconvert_queue_arn" {
  description = "ARN of the MediaConvert queue"
  value       = module.mediaconvert.queue_arn
}

output "mediaconvert_role_arn" {
  description = "ARN of the MediaConvert IAM role"
  value       = module.mediaconvert.role_arn
}

output "cloudwatch_dashboard_url" {
  description = "URL to CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${module.monitoring.dashboard_name}"
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name"
  value       = var.enable_cloudfront ? module.cloudfront[0].distribution_domain_name : null
}

output "sns_success_topic_arn" {
  description = "ARN of success notification topic"
  value       = module.sns.success_topic_arn
}

output "sns_error_topic_arn" {
  description = "ARN of error notification topic"
  value       = module.sns.error_topic_arn
}

output "lambda_functions" {
  description = "Lambda function names"
  value = {
    manifest_parser      = module.lambda.manifest_parser_name
    input_validator      = module.lambda.input_validator_name
    job_submitter        = module.lambda.job_submitter_name
    output_validator     = module.lambda.output_validator_name
    notification_handler = module.lambda.notification_handler_name
  }
}

output "trigger_command" {
  description = "Command to trigger the pipeline"
  value       = "aws s3 cp manifest.xml s3://${module.s3_buckets.input_bucket_name}/manifests/"
}
