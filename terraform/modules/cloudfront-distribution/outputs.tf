# CloudFront Distribution Module Outputs
# ========================================

output "distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = aws_cloudfront_distribution.main.id
}

output "distribution_arn" {
  description = "ARN of the CloudFront distribution"
  value       = aws_cloudfront_distribution.main.arn
}

output "distribution_domain_name" {
  description = "Domain name of the CloudFront distribution"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "distribution_hosted_zone_id" {
  description = "Route 53 zone ID for the CloudFront distribution"
  value       = aws_cloudfront_distribution.main.hosted_zone_id
}

output "origin_access_control_id" {
  description = "ID of the Origin Access Control"
  value       = aws_cloudfront_origin_access_control.main.id
}

output "key_group_id" {
  description = "ID of the CloudFront key group (if created)"
  value       = var.cloudfront_public_key_pem != "" ? aws_cloudfront_key_group.main[0].id : null
}

output "public_key_id" {
  description = "ID of the CloudFront public key (if created)"
  value       = var.cloudfront_public_key_pem != "" ? aws_cloudfront_public_key.main[0].id : null
}

output "streaming_url_base" {
  description = "Base URL for streaming content"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}
