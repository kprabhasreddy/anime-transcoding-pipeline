# S3 Buckets Module for Anime Transcoding Pipeline
# ================================================
# Creates input and output buckets with:
# - KMS encryption at rest
# - Versioning for audit trail
# - Lifecycle policies for cost optimization
# - Public access blocks for security

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
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# Input Bucket - Mezzanine files and manifests
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "input" {
  bucket = "${var.project_name}-input-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name    = "${var.project_name}-input"
    Purpose = "mezzanine-ingestion"
  })
}

resource "aws_s3_bucket_versioning" "input" {
  bucket = aws_s3_bucket.input.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "input" {
  bucket = aws_s3_bucket.input.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = var.kms_key_arn != "" ? "aws:kms" : "AES256"
    }
    bucket_key_enabled = var.kms_key_arn != "" ? true : false
  }
}

resource "aws_s3_bucket_public_access_block" "input" {
  bucket = aws_s3_bucket.input.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "input" {
  bucket = aws_s3_bucket.input.id

  # Archive processed mezzanines
  rule {
    id     = "archive-processed"
    status = "Enabled"

    filter {
      prefix = "processed/"
    }

    transition {
      days          = 30
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = 365
    }
  }

  # Clean up failed uploads
  rule {
    id     = "cleanup-incomplete-uploads"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# -----------------------------------------------------------------------------
# Output Bucket - Transcoded assets
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "output" {
  bucket = "${var.project_name}-output-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name    = "${var.project_name}-output"
    Purpose = "transcoded-delivery"
  })
}

resource "aws_s3_bucket_versioning" "output" {
  bucket = aws_s3_bucket.output.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = var.kms_key_arn != "" ? "aws:kms" : "AES256"
    }
    bucket_key_enabled = var.kms_key_arn != "" ? true : false
  }
}

resource "aws_s3_bucket_public_access_block" "output" {
  bucket = aws_s3_bucket.output.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CORS for video playback (adjust origins for production)
resource "aws_s3_bucket_cors_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag", "Content-Length", "Content-Range"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  # Transition older content to cheaper storage
  rule {
    id     = "archive-old-content"
    status = "Enabled"

    filter {
      prefix = ""
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# -----------------------------------------------------------------------------
# S3 Event Notification for Manifest Uploads
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_notification" "manifest_trigger" {
  count  = var.manifest_parser_lambda_arn != "" ? 1 : 0
  bucket = aws_s3_bucket.input.id

  lambda_function {
    lambda_function_arn = var.manifest_parser_lambda_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "manifests/"
    filter_suffix       = ".xml"
  }

  depends_on = [aws_lambda_permission.allow_s3[0]]
}

resource "aws_lambda_permission" "allow_s3" {
  count         = var.manifest_parser_lambda_arn != "" ? 1 : 0
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = var.manifest_parser_lambda_arn
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.input.arn
}
