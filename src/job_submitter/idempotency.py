"""Idempotency management using DynamoDB.

Prevents duplicate job submissions when the same manifest is processed
multiple times (e.g., due to S3 event retries or user error).

Uses DynamoDB for atomic conditional writes to ensure exactly-once
semantics in distributed Lambda environments.
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Any

from aws_lambda_powertools import Logger

from ..shared.aws_clients import get_dynamodb_resource
from ..shared.config import get_settings
from ..shared.exceptions import IdempotencyError
from ..shared.models import TranscodeManifest

logger = Logger(service="idempotency")

# TTL for idempotency records (7 days)
IDEMPOTENCY_TTL_DAYS = 7


def generate_idempotency_token(manifest: TranscodeManifest) -> str:
    """Generate deterministic idempotency token from manifest.

    The token is based on immutable content identifiers to ensure
    the same content always generates the same token.

    Components:
    - manifest_id: Unique job identifier
    - checksum_md5: Content integrity hash
    - file_size_bytes: Additional integrity check
    - audio track languages: Ensures same audio configuration

    Args:
        manifest: TranscodeManifest object

    Returns:
        64-character hex string (SHA-256 hash)
    """
    key_components = [
        manifest.manifest_id,
        manifest.mezzanine.checksum_md5,
        str(manifest.mezzanine.file_size_bytes),
        str(sorted([t.language.value for t in manifest.audio_tracks])),
    ]

    combined = "|".join(key_components)
    return hashlib.sha256(combined.encode()).hexdigest()


def check_idempotency(idempotency_token: str) -> dict[str, Any] | None:
    """Check if a job with this token already exists.

    Args:
        idempotency_token: Token from generate_idempotency_token

    Returns:
        Existing job record if found, None otherwise
    """
    settings = get_settings()

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(settings.idempotency_table)

        response = table.get_item(
            Key={"idempotency_token": idempotency_token},
            ConsistentRead=True,
        )

        item = response.get("Item")

        if item:
            logger.info(
                "Found existing idempotency record",
                extra={
                    "idempotency_token": idempotency_token[:16] + "...",
                    "job_id": item.get("job_id"),
                    "status": item.get("status"),
                },
            )
            return item

        return None

    except Exception as e:
        logger.error(
            "Idempotency check failed",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "error": str(e),
            },
        )
        # Don't fail the pipeline - allow job to proceed
        # This means we might get duplicates, but that's safer than blocking
        return None


def store_job_reference(
    idempotency_token: str,
    job_id: str,
    manifest_id: str,
    status: str = "SUBMITTED",
) -> bool:
    """Store job reference for idempotency tracking.

    Uses conditional write to prevent race conditions when multiple
    Lambda invocations try to submit the same job.

    Args:
        idempotency_token: Token from generate_idempotency_token
        job_id: MediaConvert job ID
        manifest_id: Manifest identifier
        status: Initial job status

    Returns:
        True if stored successfully, False if already exists

    Raises:
        IdempotencyError: If DynamoDB operation fails
    """
    settings = get_settings()

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(settings.idempotency_table)

        # Calculate TTL (Unix timestamp)
        ttl = int(time.time()) + (IDEMPOTENCY_TTL_DAYS * 24 * 60 * 60)

        # Conditional put - only succeeds if item doesn't exist
        table.put_item(
            Item={
                "idempotency_token": idempotency_token,
                "job_id": job_id,
                "manifest_id": manifest_id,
                "status": status,
                "created_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
            },
            ConditionExpression="attribute_not_exists(idempotency_token)",
        )

        logger.info(
            "Stored idempotency record",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "job_id": job_id,
                "manifest_id": manifest_id,
            },
        )

        return True

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Item already exists - another Lambda beat us to it
        logger.warning(
            "Idempotency record already exists",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "manifest_id": manifest_id,
            },
        )
        return False

    except Exception as e:
        logger.error(
            "Failed to store idempotency record",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "error": str(e),
            },
        )
        raise IdempotencyError(
            f"Failed to store idempotency record: {e}",
            {"idempotency_token": idempotency_token[:16], "error": str(e)},
        )


def update_job_status(
    idempotency_token: str,
    status: str,
    error_message: str | None = None,
) -> bool:
    """Update job status in idempotency table.

    Called by job monitor when MediaConvert job completes or fails.

    Args:
        idempotency_token: Token from generate_idempotency_token
        status: New status (COMPLETE, ERROR, etc.)
        error_message: Error message if failed

    Returns:
        True if updated successfully
    """
    settings = get_settings()

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(settings.idempotency_table)

        update_expr = "SET #status = :status, updated_at = :updated_at"
        expr_values: dict[str, Any] = {
            ":status": status,
            ":updated_at": datetime.utcnow().isoformat(),
        }

        if error_message:
            update_expr += ", error_message = :error"
            expr_values[":error"] = error_message

        table.update_item(
            Key={"idempotency_token": idempotency_token},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=expr_values,
        )

        logger.info(
            "Updated idempotency record status",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "status": status,
            },
        )

        return True

    except Exception as e:
        logger.error(
            "Failed to update idempotency record",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "error": str(e),
            },
        )
        return False


def cleanup_expired_records() -> int:
    """Clean up expired idempotency records.

    Note: DynamoDB TTL handles this automatically, but this can be
    used for immediate cleanup if needed.

    Returns:
        Number of records deleted
    """
    settings = get_settings()

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(settings.idempotency_table)

        # Find expired records
        now = int(time.time())
        response = table.scan(
            FilterExpression="ttl < :now",
            ExpressionAttributeValues={":now": now},
            ProjectionExpression="idempotency_token",
        )

        deleted = 0
        for item in response.get("Items", []):
            table.delete_item(Key={"idempotency_token": item["idempotency_token"]})
            deleted += 1

        logger.info(f"Cleaned up {deleted} expired idempotency records")
        return deleted

    except Exception as e:
        logger.error(f"Failed to cleanup expired records: {e}")
        return 0
