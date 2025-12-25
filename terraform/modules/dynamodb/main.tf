# DynamoDB Module for Anime Transcoding Pipeline
# ===============================================
# Creates:
# - DynamoDB table for job idempotency tracking
# - TTL configuration for automatic cleanup

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# DynamoDB Table for Idempotency
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "idempotency" {
  name         = "${var.project_name}-idempotency-${var.environment}"
  billing_mode = var.billing_mode
  hash_key     = "idempotency_token"

  # On-demand capacity (default) or provisioned
  dynamic "provisioned_throughput" {
    for_each = var.billing_mode == "PROVISIONED" ? [1] : []
    content {
      read_capacity  = var.read_capacity
      write_capacity = var.write_capacity
    }
  }

  attribute {
    name = "idempotency_token"
    type = "S"
  }

  attribute {
    name = "manifest_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # Global Secondary Index for querying by manifest_id
  global_secondary_index {
    name            = "manifest-id-index"
    hash_key        = "manifest_id"
    range_key       = "created_at"
    projection_type = "ALL"

    dynamic "provisioned_throughput" {
      for_each = var.billing_mode == "PROVISIONED" ? [1] : []
      content {
        read_capacity  = var.read_capacity
        write_capacity = var.write_capacity
      }
    }
  }

  # TTL for automatic cleanup of old records
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn != "" ? var.kms_key_arn : null
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-idempotency"
    Environment = var.environment
  })
}

# -----------------------------------------------------------------------------
# DynamoDB Table for Job Status Tracking
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "job_status" {
  name         = "${var.project_name}-job-status-${var.environment}"
  billing_mode = var.billing_mode
  hash_key     = "job_id"

  dynamic "provisioned_throughput" {
    for_each = var.billing_mode == "PROVISIONED" ? [1] : []
    content {
      read_capacity  = var.read_capacity
      write_capacity = var.write_capacity
    }
  }

  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "manifest_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  # GSI for querying by manifest_id
  global_secondary_index {
    name            = "manifest-id-index"
    hash_key        = "manifest_id"
    projection_type = "ALL"

    dynamic "provisioned_throughput" {
      for_each = var.billing_mode == "PROVISIONED" ? [1] : []
      content {
        read_capacity  = var.read_capacity
        write_capacity = var.write_capacity
      }
    }
  }

  # GSI for querying by status
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    projection_type = "KEYS_ONLY"

    dynamic "provisioned_throughput" {
      for_each = var.billing_mode == "PROVISIONED" ? [1] : []
      content {
        read_capacity  = var.read_capacity
        write_capacity = var.write_capacity
      }
    }
  }

  # TTL for cleanup
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn != "" ? var.kms_key_arn : null
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-job-status"
    Environment = var.environment
  })
}
