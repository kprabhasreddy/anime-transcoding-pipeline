# KMS Module Outputs
# ==================

output "key_id" {
  description = "ID of the KMS key"
  value       = aws_kms_key.main.key_id
}

output "key_arn" {
  description = "ARN of the KMS key"
  value       = aws_kms_key.main.arn
}

output "alias_name" {
  description = "Name of the KMS key alias"
  value       = aws_kms_alias.main.name
}

output "alias_arn" {
  description = "ARN of the KMS key alias"
  value       = aws_kms_alias.main.arn
}
