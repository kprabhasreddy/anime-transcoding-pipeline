# MediaConvert Module for Anime Transcoding Pipeline
# ===================================================
# Creates:
# - MediaConvert queue(s)
# - IAM role for MediaConvert
# - IAM policies for S3 access

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
# MediaConvert Queues
# -----------------------------------------------------------------------------

resource "aws_media_convert_queue" "main" {
  name        = "${var.project_name}-queue-${var.environment}"
  description = "Main queue for anime transcoding - ${var.environment}"
  status      = "ACTIVE"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-queue"
    Environment = var.environment
  })
}

# Priority queue for urgent jobs
resource "aws_media_convert_queue" "priority" {
  count       = var.create_priority_queue ? 1 : 0
  name        = "${var.project_name}-priority-${var.environment}"
  description = "Priority queue for urgent transcoding jobs"
  status      = "ACTIVE"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-priority-queue"
    Environment = var.environment
    Priority    = "high"
  })
}

# -----------------------------------------------------------------------------
# IAM Role for MediaConvert
# -----------------------------------------------------------------------------

resource "aws_iam_role" "mediaconvert" {
  name        = "${var.project_name}-mediaconvert-role-${var.environment}"
  description = "IAM role for MediaConvert to access S3 and KMS"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "mediaconvert.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-mediaconvert-role"
  })
}

# S3 Access Policy
resource "aws_iam_role_policy" "mediaconvert_s3" {
  name = "s3-access"
  role = aws_iam_role.mediaconvert.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadInput"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:GetObjectAcl"
        ]
        Resource = [
          "${var.input_bucket_arn}/*"
        ]
      },
      {
        Sid    = "ListInput"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          var.input_bucket_arn
        ]
      },
      {
        Sid    = "WriteOutput"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:GetObject"
        ]
        Resource = [
          "${var.output_bucket_arn}/*"
        ]
      },
      {
        Sid    = "ListOutput"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          var.output_bucket_arn
        ]
      }
    ]
  })
}

# KMS Access Policy (if using KMS encryption)
resource "aws_iam_role_policy" "mediaconvert_kms" {
  count = var.enable_kms ? 1 : 0
  name  = "kms-access"
  role  = aws_iam_role.mediaconvert.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSAccess"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = [
          var.kms_key_arn
        ]
      }
    ]
  })
}

# CloudWatch Logs Policy
resource "aws_iam_role_policy" "mediaconvert_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.mediaconvert.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/mediaconvert/*"
        ]
      }
    ]
  })
}
