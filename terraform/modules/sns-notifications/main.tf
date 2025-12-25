# SNS Notifications Module for Anime Transcoding Pipeline
# ========================================================
# Creates:
# - SNS topics for success and error notifications
# - SNS subscriptions (email/webhook)
# - Access policies

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
# SNS Topics
# -----------------------------------------------------------------------------

# Success notifications topic
resource "aws_sns_topic" "success" {
  name         = "${var.project_name}-success-${var.environment}"
  display_name = "Anime Transcoding Success Notifications"

  # Enable encryption if KMS key provided
  kms_master_key_id = var.kms_key_id != "" ? var.kms_key_id : null

  tags = merge(var.tags, {
    Name = "${var.project_name}-success-topic"
    Type = "success"
  })
}

# Error notifications topic
resource "aws_sns_topic" "error" {
  name         = "${var.project_name}-error-${var.environment}"
  display_name = "Anime Transcoding Error Notifications"

  kms_master_key_id = var.kms_key_id != "" ? var.kms_key_id : null

  tags = merge(var.tags, {
    Name = "${var.project_name}-error-topic"
    Type = "error"
  })
}

# Alarm notifications topic (for CloudWatch alarms)
resource "aws_sns_topic" "alarms" {
  name         = "${var.project_name}-alarms-${var.environment}"
  display_name = "Anime Transcoding Alarm Notifications"

  kms_master_key_id = var.kms_key_id != "" ? var.kms_key_id : null

  tags = merge(var.tags, {
    Name = "${var.project_name}-alarms-topic"
    Type = "alarms"
  })
}

# -----------------------------------------------------------------------------
# Topic Policies
# -----------------------------------------------------------------------------

# Allow Lambda and Step Functions to publish to success topic
resource "aws_sns_topic_policy" "success" {
  arn = aws_sns_topic.success.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "${var.project_name}-success-policy"
    Statement = [
      {
        Sid    = "AllowLambdaPublish"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.success.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "AllowStepFunctionsPublish"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.success.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# Allow Lambda and Step Functions to publish to error topic
resource "aws_sns_topic_policy" "error" {
  arn = aws_sns_topic.error.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "${var.project_name}-error-policy"
    Statement = [
      {
        Sid    = "AllowLambdaPublish"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.error.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "AllowStepFunctionsPublish"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.error.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# Allow CloudWatch to publish to alarms topic
resource "aws_sns_topic_policy" "alarms" {
  arn = aws_sns_topic.alarms.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "${var.project_name}-alarms-policy"
    Statement = [
      {
        Sid    = "AllowCloudWatchPublish"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.alarms.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Email Subscriptions
# -----------------------------------------------------------------------------

# Success email subscriptions
resource "aws_sns_topic_subscription" "success_email" {
  for_each = toset(var.success_email_addresses)

  topic_arn = aws_sns_topic.success.arn
  protocol  = "email"
  endpoint  = each.value
}

# Error email subscriptions
resource "aws_sns_topic_subscription" "error_email" {
  for_each = toset(var.error_email_addresses)

  topic_arn = aws_sns_topic.error.arn
  protocol  = "email"
  endpoint  = each.value
}

# Alarm email subscriptions
resource "aws_sns_topic_subscription" "alarm_email" {
  for_each = toset(var.alarm_email_addresses)

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
}

# -----------------------------------------------------------------------------
# Webhook Subscriptions (Optional)
# -----------------------------------------------------------------------------

# Error webhook (e.g., Slack, PagerDuty)
resource "aws_sns_topic_subscription" "error_webhook" {
  count = var.error_webhook_url != "" ? 1 : 0

  topic_arn = aws_sns_topic.error.arn
  protocol  = "https"
  endpoint  = var.error_webhook_url

  # Delivery policy for retries
  delivery_policy = jsonencode({
    healthyRetryPolicy = {
      minDelayTarget     = 1
      maxDelayTarget     = 60
      numRetries         = 5
      numNoDelayRetries  = 0
      backoffFunction    = "exponential"
    }
  })
}

# Alarm webhook
resource "aws_sns_topic_subscription" "alarm_webhook" {
  count = var.alarm_webhook_url != "" ? 1 : 0

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "https"
  endpoint  = var.alarm_webhook_url

  delivery_policy = jsonencode({
    healthyRetryPolicy = {
      minDelayTarget     = 1
      maxDelayTarget     = 60
      numRetries         = 5
      numNoDelayRetries  = 0
      backoffFunction    = "exponential"
    }
  })
}
