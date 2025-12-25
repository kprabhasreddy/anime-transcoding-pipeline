# Step Functions Module for Anime Transcoding Pipeline
# =====================================================
# Creates:
# - Step Functions state machine for pipeline orchestration
# - IAM role for Step Functions execution
# - EventBridge rule for MediaConvert events

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
# IAM Role for Step Functions
# -----------------------------------------------------------------------------

resource "aws_iam_role" "step_functions" {
  name        = "${var.project_name}-sfn-role-${var.environment}"
  description = "Execution role for transcoding pipeline Step Functions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-sfn-role"
  })
}

# Lambda invocation policy
resource "aws_iam_role_policy" "sfn_lambda" {
  name = "lambda-invoke"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = var.lambda_arns
      }
    ]
  })
}

# X-Ray tracing policy
resource "aws_iam_role_policy_attachment" "sfn_xray" {
  role       = aws_iam_role.step_functions.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# CloudWatch Logs policy
resource "aws_iam_role_policy" "sfn_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

# EventBridge policy (for MediaConvert events)
resource "aws_iam_role_policy" "sfn_events" {
  name = "eventbridge"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "events:PutTargets",
          "events:PutRule",
          "events:DescribeRule"
        ]
        Resource = "arn:aws:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForMediaConvertJobRule"
      }
    ]
  })
}

# SNS publish policy
resource "aws_iam_role_policy" "sfn_sns" {
  name = "sns-publish"
  role = aws_iam_role.step_functions.id

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

# -----------------------------------------------------------------------------
# CloudWatch Log Group for Step Functions
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/vendedlogs/states/${var.project_name}-pipeline-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Service = "step-functions"
  })
}

# -----------------------------------------------------------------------------
# Step Functions State Machine
# -----------------------------------------------------------------------------

resource "aws_sfn_state_machine" "transcoding_pipeline" {
  name     = "${var.project_name}-pipeline-${var.environment}"
  role_arn = aws_iam_role.step_functions.arn

  definition = jsonencode({
    Comment = "Anime Transcoding Pipeline - Orchestrates video transcoding workflow"
    StartAt = "ValidateInput"

    States = {
      # Step 1: Validate mezzanine file
      ValidateInput = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.input_validator_arn
          Payload = {
            "manifest.$"      = "$.manifest"
            "input_s3_uri.$"  = "$.input_s3_uri"
          }
        }
        ResultPath = "$.validation_result"
        ResultSelector = {
          "validation_passed.$" = "$.Payload.validation_passed"
          "file_size_bytes.$"   = "$.Payload.file_size_bytes"
          "checksum_verified.$" = "$.Payload.checksum_verified"
          "checks.$"            = "$.Payload.checks"
        }
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.TooManyRequestsException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error"
            Next        = "HandleValidationError"
          }
        ]
        Next = "CheckValidationResult"
      }

      # Check if validation passed
      CheckValidationResult = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.validation_result.validation_passed"
            BooleanEquals = true
            Next          = "SubmitTranscodeJob"
          }
        ]
        Default = "HandleValidationError"
      }

      # Step 2: Submit MediaConvert job
      SubmitTranscodeJob = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.job_submitter_arn
          Payload = {
            "manifest.$"          = "$.manifest"
            "input_s3_uri.$"      = "$.input_s3_uri"
            "output_s3_prefix.$"  = "$.output_s3_prefix"
            "validation_result.$" = "$.validation_result"
          }
        }
        ResultPath = "$.job_submission"
        ResultSelector = {
          "job_id.$"        = "$.Payload.job_id"
          "status.$"        = "$.Payload.status"
          "output_prefix.$" = "$.Payload.output_prefix"
          "variants.$"      = "$.Payload.variants"
          "idempotent.$"    = "$.Payload.idempotent"
        }
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException"]
            IntervalSeconds = 2
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error"
            Next        = "HandleJobSubmissionError"
          }
        ]
        Next = "CheckMockMode"
      }

      # Check if running in mock mode (skip waiting for MediaConvert)
      CheckMockMode = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.job_submission.status"
            StringEquals  = "MOCK_SUBMITTED"
            Next          = "MockJobComplete"
          },
          {
            Variable      = "$.job_submission.idempotent"
            BooleanEquals = true
            Next          = "HandleIdempotentJob"
          }
        ]
        Default = "WaitForMediaConvert"
      }

      # Mock mode: simulate job completion
      MockJobComplete = {
        Type    = "Pass"
        Result  = "COMPLETE"
        ResultPath = "$.mediaconvert_status"
        Next    = "ValidateOutput"
      }

      # Handle already-submitted job
      HandleIdempotentJob = {
        Type    = "Pass"
        Result  = "IDEMPOTENT_SKIP"
        ResultPath = "$.mediaconvert_status"
        Next    = "NotifySuccess"
      }

      # Step 3: Wait for MediaConvert job completion
      WaitForMediaConvert = {
        Type     = "Task"
        Resource = "arn:aws:states:::mediaconvert:createJob.sync"
        Parameters = {
          "Role.$"     = "$.mediaconvert_role_arn"
          "Settings.$" = "$.job_settings"
          "Queue.$"    = "$.mediaconvert_queue_arn"
        }
        ResultPath = "$.mediaconvert_result"
        Retry = [
          {
            ErrorEquals     = ["MediaConvert.ServiceUnavailableException"]
            IntervalSeconds = 30
            MaxAttempts     = 3
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error"
            Next        = "HandleTranscodeError"
          }
        ]
        Next = "ValidateOutput"
      }

      # Step 4: Validate transcoded output
      ValidateOutput = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.output_validator_arn
          Payload = {
            "manifest.$"       = "$.manifest"
            "job_id.$"         = "$.job_submission.job_id"
            "output_prefix.$"  = "$.job_submission.output_prefix"
            "variants.$"       = "$.job_submission.variants"
          }
        }
        ResultPath = "$.output_validation"
        ResultSelector = {
          "validation_passed.$" = "$.Payload.validation_passed"
          "validations.$"       = "$.Payload.validations"
        }
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException"]
            IntervalSeconds = 2
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            ResultPath  = "$.error"
            Next        = "HandleOutputValidationError"
          }
        ]
        Next = "CheckOutputValidation"
      }

      # Check if output validation passed
      CheckOutputValidation = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.output_validation.validation_passed"
            BooleanEquals = true
            Next          = "NotifySuccess"
          }
        ]
        Default = "HandleOutputValidationError"
      }

      # Step 5: Notify success
      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.notification_handler_arn
          Payload = {
            "type"              = "SUCCESS"
            "manifest.$"        = "$.manifest"
            "job_id.$"          = "$.job_submission.job_id"
            "output_prefix.$"   = "$.job_submission.output_prefix"
            "variants.$"        = "$.job_submission.variants"
          }
        }
        ResultPath = "$.notification"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException"]
            IntervalSeconds = 2
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Next = "PipelineComplete"
      }

      # Success state
      PipelineComplete = {
        Type = "Succeed"
      }

      # Error handlers
      HandleValidationError = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.notification_handler_arn
          Payload = {
            "type"       = "ERROR"
            "error_type" = "VALIDATION_FAILED"
            "manifest.$" = "$.manifest"
            "error.$"    = "$.error"
          }
        }
        ResultPath = "$.notification"
        Next       = "ValidationFailed"
      }

      ValidationFailed = {
        Type  = "Fail"
        Error = "ValidationError"
        Cause = "Input validation failed - checksum mismatch or file not found"
      }

      HandleJobSubmissionError = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.notification_handler_arn
          Payload = {
            "type"       = "ERROR"
            "error_type" = "JOB_SUBMISSION_FAILED"
            "manifest.$" = "$.manifest"
            "error.$"    = "$.error"
          }
        }
        ResultPath = "$.notification"
        Next       = "JobSubmissionFailed"
      }

      JobSubmissionFailed = {
        Type  = "Fail"
        Error = "JobSubmissionError"
        Cause = "Failed to submit MediaConvert job"
      }

      HandleTranscodeError = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.notification_handler_arn
          Payload = {
            "type"       = "ERROR"
            "error_type" = "TRANSCODE_FAILED"
            "manifest.$" = "$.manifest"
            "job_id.$"   = "$.job_submission.job_id"
            "error.$"    = "$.error"
          }
        }
        ResultPath = "$.notification"
        Next       = "TranscodeFailed"
      }

      TranscodeFailed = {
        Type  = "Fail"
        Error = "TranscodeError"
        Cause = "MediaConvert job failed"
      }

      HandleOutputValidationError = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.notification_handler_arn
          Payload = {
            "type"       = "ERROR"
            "error_type" = "OUTPUT_VALIDATION_FAILED"
            "manifest.$" = "$.manifest"
            "job_id.$"   = "$.job_submission.job_id"
            "error.$"    = "$.error"
          }
        }
        ResultPath = "$.notification"
        Next       = "OutputValidationFailed"
      }

      OutputValidationFailed = {
        Type  = "Fail"
        Error = "OutputValidationError"
        Cause = "Output validation failed - missing files or invalid playlist"
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-pipeline"
  })
}

# -----------------------------------------------------------------------------
# EventBridge Rule for MediaConvert Events
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "mediaconvert_events" {
  name        = "${var.project_name}-mediaconvert-events-${var.environment}"
  description = "Capture MediaConvert job status changes"

  event_pattern = jsonencode({
    source      = ["aws.mediaconvert"]
    detail-type = ["MediaConvert Job State Change"]
    detail = {
      status = ["COMPLETE", "ERROR", "CANCELED"]
    }
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-mediaconvert-events"
  })
}
