# CloudWatch Monitoring Module for Anime Transcoding Pipeline
# ============================================================
# Creates:
# - CloudWatch alarms for pipeline health
# - CloudWatch dashboard for visualization
# - Metric filters for custom metrics

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
# CloudWatch Alarms
# -----------------------------------------------------------------------------

# Alarm: Lambda Errors
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project_name}-${each.value}-errors-${var.environment}"
  alarm_description   = "Lambda function ${each.value} is experiencing errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = var.alarm_sns_topic_arns
  ok_actions    = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "lambda-errors"
  })
}

# Alarm: Step Functions Failures
resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "${var.project_name}-pipeline-failures-${var.environment}"
  alarm_description   = "Transcoding pipeline is experiencing execution failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "sfn-failures"
  })
}

# Alarm: Step Functions Throttles
resource "aws_cloudwatch_metric_alarm" "sfn_throttles" {
  alarm_name          = "${var.project_name}-pipeline-throttles-${var.environment}"
  alarm_description   = "Transcoding pipeline is being throttled"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ExecutionThrottled"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "sfn-throttles"
  })
}

# Alarm: MediaConvert Job Errors
resource "aws_cloudwatch_metric_alarm" "mediaconvert_errors" {
  alarm_name          = "${var.project_name}-mediaconvert-errors-${var.environment}"
  alarm_description   = "MediaConvert jobs are failing"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "JobsErrored"
  namespace           = "AWS/MediaConvert"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    Queue = var.mediaconvert_queue_name
  }

  alarm_actions = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "mediaconvert-errors"
  })
}

# Alarm: Pipeline Latency (P99)
resource "aws_cloudwatch_metric_alarm" "pipeline_latency" {
  alarm_name          = "${var.project_name}-pipeline-latency-${var.environment}"
  alarm_description   = "Transcoding pipeline latency is too high (P99 > 30 min)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ExecutionTime"
  namespace           = "AWS/States"
  period              = 900
  extended_statistic  = "p99"
  threshold           = 1800000  # 30 minutes in milliseconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "pipeline-latency"
  })
}

# Alarm: Input Validation Failures (custom metric)
resource "aws_cloudwatch_metric_alarm" "validation_failures" {
  alarm_name          = "${var.project_name}-validation-failures-${var.environment}"
  alarm_description   = "High rate of input validation failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "InputValidationFailure"
  namespace           = "AnimeTranscoding"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "validation-failures"
  })
}

# Alarm: Checksum Mismatch Errors
resource "aws_cloudwatch_metric_alarm" "checksum_mismatches" {
  alarm_name          = "${var.project_name}-checksum-mismatches-${var.environment}"
  alarm_description   = "Checksum verification failures detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ChecksumMismatchErrors"
  namespace           = "AnimeTranscoding"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_sns_topic_arns

  tags = merge(var.tags, {
    Alarm = "checksum-mismatches"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Dashboard
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      # Row 1: Pipeline Overview
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "Pipeline Executions"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", var.state_machine_arn, { label = "Started", color = "#2ca02c" }],
            [".", "ExecutionsSucceeded", ".", ".", { label = "Succeeded", color = "#1f77b4" }],
            [".", "ExecutionsFailed", ".", ".", { label = "Failed", color = "#d62728" }]
          ]
          period = 300
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 0
        width  = 8
        height = 6
        properties = {
          title   = "Pipeline Duration"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/States", "ExecutionTime", "StateMachineArn", var.state_machine_arn, { stat = "p50", label = "P50" }],
            [".", ".", ".", ".", { stat = "p90", label = "P90" }],
            [".", ".", ".", ".", { stat = "p99", label = "P99" }]
          ]
          period = 300
          yAxis = {
            left = {
              label     = "Milliseconds"
              showUnits = false
            }
          }
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 0
        width  = 8
        height = 6
        properties = {
          title  = "Alarm Status"
          region = data.aws_region.current.name
          view   = "singleValue"
          metrics = [
            ["AWS/States", "ExecutionsFailed", "StateMachineArn", var.state_machine_arn, { label = "Pipeline Failures", color = "#d62728" }],
            ["AWS/MediaConvert", "JobsErrored", "Queue", var.mediaconvert_queue_name, { label = "Transcode Errors", color = "#ff7f0e" }],
            ["AnimeTranscoding", "ChecksumMismatchErrors", { label = "Checksum Errors", color = "#9467bd" }]
          ]
          period = 3600
        }
      },

      # Row 2: MediaConvert Metrics
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "MediaConvert Jobs"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/MediaConvert", "JobsSubmitted", "Queue", var.mediaconvert_queue_name, { label = "Submitted", color = "#2ca02c" }],
            [".", "JobsCompleted", ".", ".", { label = "Completed", color = "#1f77b4" }],
            [".", "JobsErrored", ".", ".", { label = "Errored", color = "#d62728" }]
          ]
          period = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "MediaConvert Transcode Time"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AWS/MediaConvert", "TranscodingTime", "Queue", var.mediaconvert_queue_name, { stat = "Average", label = "Average" }],
            [".", ".", ".", ".", { stat = "Maximum", label = "Maximum" }]
          ]
          period = 300
          yAxis = {
            left = {
              label     = "Seconds"
              showUnits = false
            }
          }
        }
      },

      # Row 3: Lambda Metrics
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "Lambda Invocations"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = true
          metrics = [
            for fn in var.lambda_function_names : [
              "AWS/Lambda", "Invocations", "FunctionName", fn, { label = fn }
            ]
          ]
          period = 300
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "Lambda Errors"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            for fn in var.lambda_function_names : [
              "AWS/Lambda", "Errors", "FunctionName", fn, { label = fn }
            ]
          ]
          period = 300
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 12
        width  = 8
        height = 6
        properties = {
          title   = "Lambda Duration"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            for fn in var.lambda_function_names : [
              "AWS/Lambda", "Duration", "FunctionName", fn, { stat = "Average", label = fn }
            ]
          ]
          period = 300
          yAxis = {
            left = {
              label     = "Milliseconds"
              showUnits = false
            }
          }
        }
      },

      # Row 4: Custom Metrics
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "Validation Metrics"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AnimeTranscoding", "InputValidationSuccess", { label = "Input Valid", color = "#2ca02c" }],
            [".", "InputValidationFailure", { label = "Input Invalid", color = "#d62728" }],
            [".", "OutputValidationSuccess", { label = "Output Valid", color = "#1f77b4" }],
            [".", "OutputValidationFailure", { label = "Output Invalid", color = "#ff7f0e" }]
          ]
          period = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "Job Submission Metrics"
          region  = data.aws_region.current.name
          view    = "timeSeries"
          stacked = false
          metrics = [
            ["AnimeTranscoding", "JobsSubmitted", { label = "Jobs Submitted", color = "#2ca02c" }],
            [".", "IdempotentJobSkipped", { label = "Idempotent Skip", color = "#9467bd" }],
            [".", "JobSubmissionErrors", { label = "Submission Errors", color = "#d62728" }]
          ]
          period = 300
        }
      }
    ]
  })
}
