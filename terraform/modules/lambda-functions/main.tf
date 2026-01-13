# Lambda Functions Module for Anime Transcoding Pipeline
# ======================================================
# Creates:
# - Lambda functions for all pipeline stages
# - IAM roles and policies for each Lambda
# - Lambda layers for shared dependencies
# - CloudWatch log groups

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
# Lambda Execution Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_execution" {
  name        = "${var.project_name}-lambda-execution-${var.environment}"
  description = "Execution role for transcoding pipeline Lambdas"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-lambda-execution-role"
  })
}

# Basic Lambda execution policy (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# X-Ray tracing policy
resource "aws_iam_role_policy_attachment" "lambda_xray" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# S3 access policy
resource "aws_iam_role_policy" "lambda_s3" {
  name = "s3-access"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadInputBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:HeadObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.input_bucket_arn,
          "${var.input_bucket_arn}/*"
        ]
      },
      {
        Sid    = "ReadWriteOutputBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.output_bucket_arn,
          "${var.output_bucket_arn}/*"
        ]
      }
    ]
  })
}

# DynamoDB access policy (for idempotency)
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "dynamodb-access"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = [
          var.dynamodb_table_arn,
          "${var.dynamodb_table_arn}/index/*"
        ]
      }
    ]
  })
}

# MediaConvert access policy
resource "aws_iam_role_policy" "lambda_mediaconvert" {
  name = "mediaconvert-access"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "MediaConvertEndpoints"
        Effect = "Allow"
        Action = [
          "mediaconvert:DescribeEndpoints"
        ]
        Resource = "*"
      },
      {
        Sid    = "MediaConvertJobOperations"
        Effect = "Allow"
        Action = [
          "mediaconvert:CreateJob",
          "mediaconvert:GetJob",
          "mediaconvert:ListJobs"
        ]
        Resource = [
          "arn:aws:mediaconvert:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:queues/${var.project_name}-*",
          "arn:aws:mediaconvert:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:jobs/*"
        ]
      },
      {
        Sid      = "PassRoleToMediaConvert"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = var.mediaconvert_role_arn
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "mediaconvert.amazonaws.com"
          }
        }
      }
    ]
  })
}

# KMS access policy
resource "aws_iam_role_policy" "lambda_kms" {
  count = var.enable_kms ? 1 : 0
  name  = "kms-access"
  role  = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = var.kms_key_arn
      }
    ]
  })
}

# SNS publish policy
resource "aws_iam_role_policy" "lambda_sns" {
  name = "sns-publish"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.sns_topic_arns
      }
    ]
  })
}

# Step Functions access policy (for starting pipeline executions)
resource "aws_iam_role_policy" "lambda_stepfunctions" {
  name = "stepfunctions-access"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution",
          "states:DescribeExecution",
          "states:StopExecution"
        ]
        Resource = var.state_machine_arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Lambda Layer for Shared Dependencies
# -----------------------------------------------------------------------------

resource "aws_lambda_layer_version" "shared" {
  layer_name          = "${var.project_name}-shared-${var.environment}"
  description         = "Shared dependencies for transcoding pipeline"
  compatible_runtimes = ["python3.11", "python3.12"]
  filename            = var.layer_zip_path
  source_code_hash    = filebase64sha256(var.layer_zip_path)
}

# -----------------------------------------------------------------------------
# CloudWatch Log Groups
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "manifest_parser" {
  name              = "/aws/lambda/${var.project_name}-manifest-parser-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Function = "manifest-parser"
  })
}

resource "aws_cloudwatch_log_group" "input_validator" {
  name              = "/aws/lambda/${var.project_name}-input-validator-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Function = "input-validator"
  })
}

resource "aws_cloudwatch_log_group" "job_submitter" {
  name              = "/aws/lambda/${var.project_name}-job-submitter-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Function = "job-submitter"
  })
}

resource "aws_cloudwatch_log_group" "output_validator" {
  name              = "/aws/lambda/${var.project_name}-output-validator-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Function = "output-validator"
  })
}

resource "aws_cloudwatch_log_group" "notification_handler" {
  name              = "/aws/lambda/${var.project_name}-notification-handler-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Function = "notification-handler"
  })
}

# -----------------------------------------------------------------------------
# Lambda Functions
# -----------------------------------------------------------------------------

# Manifest Parser Lambda
resource "aws_lambda_function" "manifest_parser" {
  function_name = "${var.project_name}-manifest-parser-${var.environment}"
  description   = "Parses anime XML manifests and triggers transcoding pipeline"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "src.manifest_parser.handler.handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  layers = [aws_lambda_layer_version.shared.arn]

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      LOG_LEVEL                = var.log_level
      POWERTOOLS_SERVICE_NAME  = "manifest-parser"
      POWERTOOLS_METRICS_NAMESPACE = "AnimeTranscoding"
      INPUT_BUCKET             = var.input_bucket_name
      OUTPUT_BUCKET            = var.output_bucket_name
      STATE_MACHINE_ARN        = var.state_machine_arn
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.manifest_parser]

  tags = merge(var.tags, {
    Function = "manifest-parser"
  })
}

# Input Validator Lambda
resource "aws_lambda_function" "input_validator" {
  function_name = "${var.project_name}-input-validator-${var.environment}"
  description   = "Validates mezzanine files before transcoding (checksum, mediainfo)"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "src.input_validator.handler.handler"
  runtime       = "python3.11"
  timeout       = 300  # 5 minutes for large file checksums
  memory_size   = 512

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  layers = [aws_lambda_layer_version.shared.arn]

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      LOG_LEVEL                = var.log_level
      POWERTOOLS_SERVICE_NAME  = "input-validator"
      POWERTOOLS_METRICS_NAMESPACE = "AnimeTranscoding"
      CHECKSUM_CHUNK_SIZE_BYTES = "8388608"  # 8MB chunks
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.input_validator]

  tags = merge(var.tags, {
    Function = "input-validator"
  })
}

# Job Submitter Lambda
resource "aws_lambda_function" "job_submitter" {
  function_name = "${var.project_name}-job-submitter-${var.environment}"
  description   = "Submits MediaConvert jobs for transcoding"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "src.job_submitter.handler.handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 256

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  layers = [aws_lambda_layer_version.shared.arn]

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      LOG_LEVEL                = var.log_level
      POWERTOOLS_SERVICE_NAME  = "job-submitter"
      POWERTOOLS_METRICS_NAMESPACE = "AnimeTranscoding"
      MEDIACONVERT_QUEUE_ARN   = var.mediaconvert_queue_arn
      MEDIACONVERT_ROLE_ARN    = var.mediaconvert_role_arn
      IDEMPOTENCY_TABLE        = var.dynamodb_table_name
      ENABLE_H265              = tostring(var.enable_h265)
      ENABLE_DASH              = tostring(var.enable_dash)
      MOCK_MODE                = tostring(var.mock_mode)
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.job_submitter]

  tags = merge(var.tags, {
    Function = "job-submitter"
  })
}

# Output Validator Lambda
resource "aws_lambda_function" "output_validator" {
  function_name = "${var.project_name}-output-validator-${var.environment}"
  description   = "Validates transcoded outputs (HLS/DASH, duration match)"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "src.output_validator.handler.handler"
  runtime       = "python3.11"
  timeout       = 120
  memory_size   = 256

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  layers = [aws_lambda_layer_version.shared.arn]

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      LOG_LEVEL                = var.log_level
      POWERTOOLS_SERVICE_NAME  = "output-validator"
      POWERTOOLS_METRICS_NAMESPACE = "AnimeTranscoding"
      ENABLE_DASH              = tostring(var.enable_dash)
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.output_validator]

  tags = merge(var.tags, {
    Function = "output-validator"
  })
}

# Notification Handler Lambda
resource "aws_lambda_function" "notification_handler" {
  function_name = "${var.project_name}-notification-handler-${var.environment}"
  description   = "Handles pipeline notifications and alerts"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "src.notification_handler.handler.handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 128

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  layers = [aws_lambda_layer_version.shared.arn]

  environment {
    variables = {
      ENVIRONMENT              = var.environment
      LOG_LEVEL                = var.log_level
      POWERTOOLS_SERVICE_NAME  = "notification-handler"
      POWERTOOLS_METRICS_NAMESPACE = "AnimeTranscoding"
      SUCCESS_SNS_TOPIC_ARN    = var.success_sns_topic_arn
      ERROR_SNS_TOPIC_ARN      = var.error_sns_topic_arn
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.notification_handler]

  tags = merge(var.tags, {
    Function = "notification-handler"
  })
}

# -----------------------------------------------------------------------------
# S3 Event Trigger for Manifest Parser
# -----------------------------------------------------------------------------

resource "aws_lambda_permission" "s3_trigger" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.manifest_parser.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.input_bucket_arn
}

resource "aws_s3_bucket_notification" "manifest_trigger" {
  bucket = var.input_bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.manifest_parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "manifests/"
    filter_suffix       = ".xml"
  }

  depends_on = [aws_lambda_permission.s3_trigger]
}
