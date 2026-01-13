# DynamoDB Module for Anime Transcoding Pipeline
# ===============================================
# Creates:
# - Single DynamoDB table with single-table design pattern
# - GSIs for efficient queries by manifest_id, status, and job_id
# - TTL configuration for automatic cleanup
#
# Single-Table Design:
# - PK: idempotency_token (for job tracking/deduplication)
# - GSI1: manifest_id + created_at (query all jobs for a manifest)
# - GSI2: status + created_at (find jobs by status)
# - GSI3: job_id (lookup by MediaConvert job ID)

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
# DynamoDB Table - Single Table Design
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "transcoding_jobs" {
  name         = "${var.project_name}-jobs-${var.environment}"
  billing_mode = var.billing_mode
  hash_key     = "idempotency_token"

  # Provisioned capacity (only used when billing_mode is PROVISIONED)
  read_capacity  = var.billing_mode == "PROVISIONED" ? var.read_capacity : null
  write_capacity = var.billing_mode == "PROVISIONED" ? var.write_capacity : null

  # Primary key
  attribute {
    name = "idempotency_token"
    type = "S"
  }

  # GSI attributes
  attribute {
    name = "manifest_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "job_id"
    type = "S"
  }

  # GSI1: Query by manifest_id with time ordering
  # Use case: "Show all transcode jobs for Attack on Titan S01E01"
  global_secondary_index {
    name            = "manifest-id-index"
    hash_key        = "manifest_id"
    range_key       = "created_at"
    projection_type = "ALL"
    # Note: GSI capacity is managed automatically with PAY_PER_REQUEST billing
    read_capacity   = var.billing_mode == "PROVISIONED" ? var.read_capacity : null
    write_capacity  = var.billing_mode == "PROVISIONED" ? var.write_capacity : null
  }

  # GSI2: Query by status with time ordering
  # Use case: "Find all failed jobs" or "Find all in-progress jobs"
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "KEYS_ONLY"
    read_capacity   = var.billing_mode == "PROVISIONED" ? var.read_capacity : null
    write_capacity  = var.billing_mode == "PROVISIONED" ? var.write_capacity : null
  }

  # GSI3: Lookup by MediaConvert job_id
  # Use case: "Get job details from MediaConvert callback"
  global_secondary_index {
    name            = "job-id-index"
    hash_key        = "job_id"
    projection_type = "ALL"
    read_capacity   = var.billing_mode == "PROVISIONED" ? var.read_capacity : null
    write_capacity  = var.billing_mode == "PROVISIONED" ? var.write_capacity : null
  }

  # TTL for automatic cleanup of old records
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption (AWS managed or customer KMS key)
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn != "" ? var.kms_key_arn : null
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-jobs"
    Environment = var.environment
    Purpose     = "Transcode job tracking and idempotency"
  })
}

# -----------------------------------------------------------------------------
# Note on Single-Table Design
# -----------------------------------------------------------------------------
# The old separate tables (idempotency and job_status) have been consolidated
# into a single table. This improves:
# - Cost efficiency (one table instead of two)
# - Query flexibility (GSIs for multiple access patterns)
# - Consistency (single source of truth)
#
# The idempotency_table output now points to this consolidated table.
# All job data (idempotency tokens, job status, metadata) is stored here.
