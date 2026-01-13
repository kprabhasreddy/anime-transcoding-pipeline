# S3 Buckets Module - Outputs
# ============================

output "input_bucket_id" {
  description = "Input bucket ID"
  value       = aws_s3_bucket.input.id
}

output "input_bucket_name" {
  description = "Input bucket name"
  value       = aws_s3_bucket.input.id
}

output "input_bucket_arn" {
  description = "Input bucket ARN"
  value       = aws_s3_bucket.input.arn
}

output "input_bucket_domain_name" {
  description = "Input bucket domain name"
  value       = aws_s3_bucket.input.bucket_domain_name
}

output "output_bucket_id" {
  description = "Output bucket ID"
  value       = aws_s3_bucket.output.id
}

output "output_bucket_name" {
  description = "Output bucket name"
  value       = aws_s3_bucket.output.id
}

output "output_bucket_arn" {
  description = "Output bucket ARN"
  value       = aws_s3_bucket.output.arn
}

output "output_bucket_domain_name" {
  description = "Output bucket domain name"
  value       = aws_s3_bucket.output.bucket_domain_name
}

output "output_bucket_regional_domain_name" {
  description = "Output bucket regional domain name (for CloudFront)"
  value       = aws_s3_bucket.output.bucket_regional_domain_name
}
