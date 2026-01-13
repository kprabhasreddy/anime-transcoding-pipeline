"""Lambda handler for pipeline notifications.

This Lambda handles success and error notifications from the pipeline.
Called by Step Functions at the end of pipeline execution.

Publishes:
1. Success notifications to SNS
2. Error notifications with details
3. Webhook callbacks with HMAC signature verification
4. Formatted messages for email/webhook consumption
"""

import hashlib
import hmac
import json
import ssl
import time
import urllib.request
from typing import Any
from urllib.error import HTTPError, URLError

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from ..shared.aws_clients import get_sns_client
from ..shared.config import get_settings
from .formatters import format_error_message, format_json_notification, format_success_message

logger = Logger(service="notification-handler")
tracer = Tracer(service="notification-handler")
metrics = Metrics(service="notification-handler", namespace="AnimeTranscoding")


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Handle pipeline notifications.

    Args:
        event: Notification event from Step Functions
        context: Lambda context

    Returns:
        Notification result

    Input event structure:
        {
            "type": "SUCCESS" | "ERROR",
            "manifest": {...},
            "job_id": "optional-job-id",
            "output_prefix": "optional-s3-prefix",
            "error_type": "optional-error-type",
            "error": {...optional-error-details}
        }

    Output structure:
        {
            "notification_sent": true,
            "topic": "success|error",
            "message_id": "sns-message-id"
        }
    """
    settings = get_settings()
    sns_client = get_sns_client()

    notification_type = event.get("type", "UNKNOWN")
    manifest = event.get("manifest", {})
    manifest_id = manifest.get("manifest_id", "unknown")

    logger.info(
        "Processing notification",
        extra={
            "type": notification_type,
            "manifest_id": manifest_id,
        },
    )

    try:
        if notification_type == "SUCCESS":
            result = _send_success_notification(
                sns_client=sns_client,
                settings=settings,
                manifest=manifest,
                job_id=event.get("job_id"),
                output_prefix=event.get("output_prefix"),
                variants=event.get("variants", []),
            )
            metrics.add_metric(
                name="SuccessNotificationsSent",
                unit=MetricUnit.Count,
                value=1,
            )

        elif notification_type == "ERROR":
            result = _send_error_notification(
                sns_client=sns_client,
                settings=settings,
                manifest=manifest,
                error_type=event.get("error_type", "UNKNOWN"),
                error=event.get("error", {}),
                job_id=event.get("job_id"),
            )
            metrics.add_metric(
                name="ErrorNotificationsSent",
                unit=MetricUnit.Count,
                value=1,
            )

        else:
            logger.warning(f"Unknown notification type: {notification_type}")
            result = {
                "notification_sent": False,
                "reason": f"Unknown type: {notification_type}",
            }

        # Send webhook callback if configured in manifest
        callback_url = manifest.get("callback_url")
        if callback_url:
            webhook_result = _send_webhook_callback(
                callback_url=callback_url,
                notification_type=notification_type,
                manifest=manifest,
                details={
                    "job_id": event.get("job_id"),
                    "output_prefix": event.get("output_prefix"),
                    "variants": event.get("variants", []),
                    "error_type": event.get("error_type"),
                    "error": event.get("error"),
                },
                settings=settings,
            )
            result["webhook"] = webhook_result

            if webhook_result.get("success"):
                metrics.add_metric(
                    name="WebhookCallbacksSent",
                    unit=MetricUnit.Count,
                    value=1,
                )
            else:
                metrics.add_metric(
                    name="WebhookCallbacksFailed",
                    unit=MetricUnit.Count,
                    value=1,
                )

        metrics.add_metadata(key="manifest_id", value=manifest_id)
        return result

    except Exception as e:
        logger.exception("Failed to send notification")
        metrics.add_metric(
            name="NotificationErrors",
            unit=MetricUnit.Count,
            value=1,
        )
        # Don't raise - notification failures shouldn't fail the pipeline
        return {
            "notification_sent": False,
            "error": str(e),
        }


@tracer.capture_method
def _send_webhook_callback(
    callback_url: str,
    notification_type: str,
    manifest: dict[str, Any],
    details: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    """Send webhook callback to the URL specified in the manifest.

    Uses HMAC-SHA256 signature for request verification.
    The webhook secret should be configured in environment settings.

    Args:
        callback_url: URL to send the webhook to
        notification_type: SUCCESS or ERROR
        manifest: Original manifest data
        details: Notification details (job_id, output, etc.)
        settings: Application settings

    Returns:
        Dictionary with success status and response details

    Webhook Request:
        - Method: POST
        - Content-Type: application/json
        - X-Webhook-Signature: HMAC-SHA256 signature of body
        - X-Webhook-Timestamp: Unix timestamp
    """
    # Get webhook secret from settings (if not configured, skip signing)
    webhook_secret = getattr(settings, "webhook_secret", None)

    # Build JSON payload
    payload = format_json_notification(
        notification_type=notification_type,
        manifest=manifest,
        details=details,
        environment=settings.environment,
    )
    payload_bytes = payload.encode("utf-8")

    # Generate timestamp and signature
    timestamp = str(int(time.time()))
    signature = ""

    if webhook_secret:
        # Create HMAC signature: HMAC-SHA256(secret, timestamp + "." + payload)
        message = f"{timestamp}.{payload}".encode("utf-8")
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    # Build request
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AnimeTranscodingPipeline/1.0",
        "X-Webhook-Timestamp": timestamp,
    }

    if signature:
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        request = urllib.request.Request(
            callback_url,
            data=payload_bytes,
            headers=headers,
            method="POST",
        )

        # Create SSL context (verify certificates in production)
        ssl_context = ssl.create_default_context()

        with urllib.request.urlopen(request, context=ssl_context, timeout=10) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")[:500]  # Limit response size

        logger.info(
            "Webhook callback sent successfully",
            extra={
                "callback_url": callback_url,
                "status_code": status_code,
                "manifest_id": manifest.get("manifest_id"),
            },
        )

        return {
            "success": True,
            "status_code": status_code,
            "response": response_body,
        }

    except HTTPError as e:
        logger.error(
            "Webhook callback failed with HTTP error",
            extra={
                "callback_url": callback_url,
                "status_code": e.code,
                "reason": e.reason,
                "manifest_id": manifest.get("manifest_id"),
            },
        )
        return {
            "success": False,
            "error": f"HTTP {e.code}: {e.reason}",
        }

    except URLError as e:
        logger.error(
            "Webhook callback failed with URL error",
            extra={
                "callback_url": callback_url,
                "error": str(e.reason),
                "manifest_id": manifest.get("manifest_id"),
            },
        )
        return {
            "success": False,
            "error": str(e.reason),
        }

    except Exception as e:
        logger.error(
            "Webhook callback failed",
            extra={
                "callback_url": callback_url,
                "error": str(e),
                "manifest_id": manifest.get("manifest_id"),
            },
        )
        return {
            "success": False,
            "error": str(e),
        }


@tracer.capture_method
def _send_success_notification(
    sns_client: Any,
    settings: Any,
    manifest: dict[str, Any],
    job_id: str | None,
    output_prefix: str | None,
    variants: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send success notification to SNS."""
    if not settings.sns_success_topic_arn:
        logger.info("No success SNS topic configured, skipping notification")
        return {"notification_sent": False, "reason": "No topic configured"}

    message = format_success_message(
        manifest=manifest,
        job_id=job_id,
        output_prefix=output_prefix,
        variants=variants,
        environment=settings.environment,
    )

    episode = manifest.get("episode", {})
    subject = (
        f"[SUCCESS] Transcode Complete: "
        f"{episode.get('series_title', 'Unknown')} "
        f"S{episode.get('season_number', '?'):02d}E{episode.get('episode_number', '?'):02d}"
    )

    response = sns_client.publish(
        TopicArn=settings.sns_success_topic_arn,
        Subject=subject[:100],  # SNS subject limit
        Message=message,
        MessageAttributes={
            "type": {"DataType": "String", "StringValue": "SUCCESS"},
            "manifest_id": {"DataType": "String", "StringValue": manifest.get("manifest_id", "unknown")},
            "environment": {"DataType": "String", "StringValue": settings.environment},
        },
    )

    logger.info(
        "Success notification sent",
        extra={
            "message_id": response["MessageId"],
            "manifest_id": manifest.get("manifest_id"),
        },
    )

    return {
        "notification_sent": True,
        "topic": "success",
        "message_id": response["MessageId"],
    }


@tracer.capture_method
def _send_error_notification(
    sns_client: Any,
    settings: Any,
    manifest: dict[str, Any],
    error_type: str,
    error: dict[str, Any],
    job_id: str | None,
) -> dict[str, Any]:
    """Send error notification to SNS."""
    if not settings.sns_error_topic_arn:
        logger.info("No error SNS topic configured, skipping notification")
        return {"notification_sent": False, "reason": "No topic configured"}

    message = format_error_message(
        manifest=manifest,
        error_type=error_type,
        error=error,
        job_id=job_id,
        environment=settings.environment,
    )

    episode = manifest.get("episode", {})
    subject = (
        f"[ERROR] Transcode Failed: "
        f"{episode.get('series_title', 'Unknown')} - "
        f"{error_type}"
    )

    response = sns_client.publish(
        TopicArn=settings.sns_error_topic_arn,
        Subject=subject[:100],
        Message=message,
        MessageAttributes={
            "type": {"DataType": "String", "StringValue": "ERROR"},
            "error_type": {"DataType": "String", "StringValue": error_type},
            "manifest_id": {"DataType": "String", "StringValue": manifest.get("manifest_id", "unknown")},
            "environment": {"DataType": "String", "StringValue": settings.environment},
        },
    )

    logger.info(
        "Error notification sent",
        extra={
            "message_id": response["MessageId"],
            "manifest_id": manifest.get("manifest_id"),
            "error_type": error_type,
        },
    )

    return {
        "notification_sent": True,
        "topic": "error",
        "message_id": response["MessageId"],
    }
