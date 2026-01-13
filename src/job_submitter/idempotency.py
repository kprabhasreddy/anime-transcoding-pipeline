"""Idempotency management using DynamoDB.

Prevents duplicate job submissions when the same manifest is processed
multiple times (e.g., due to S3 event retries or user error).

Uses DynamoDB for atomic conditional writes to ensure exactly-once
semantics in distributed Lambda environments.

Features:
- Profile versioning: Include encoding profile version in token to allow
  re-encoding when settings change
- Force reprocess: Optional bypass for intentional re-transcoding
- Slot reservation: Two-phase commit to prevent race conditions
"""

import hashlib
import time
from datetime import datetime
from typing import Any

from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from ..shared.aws_clients import get_dynamodb_resource
from ..shared.config import get_settings
from ..shared.exceptions import IdempotencyError
from ..shared.models import TranscodeManifest

logger = Logger(service="idempotency")

# TTL for idempotency records (7 days)
IDEMPOTENCY_TTL_DAYS = 7


def generate_idempotency_token(
    manifest: TranscodeManifest,
    profile_version: str = "v1.0",
) -> str:
    """Generate deterministic idempotency token from manifest.

    The token is based on immutable content identifiers to ensure
    the same content always generates the same token.

    Components:
    - manifest_id: Unique job identifier
    - checksum_md5: Content integrity hash
    - file_size_bytes: Additional integrity check
    - audio track languages: Ensures same audio configuration
    - profile_version: Encoding profile version (allows re-encoding with new settings)

    Args:
        manifest: TranscodeManifest object
        profile_version: Current transcode profile version (e.g., "v1.0")
            Increment this when encoding settings change to allow re-processing
            of previously transcoded content with new settings.

    Returns:
        64-character hex string (SHA-256 hash)
    """
    key_components = [
        manifest.manifest_id,
        manifest.mezzanine.checksum_md5,
        str(manifest.mezzanine.file_size_bytes),
        str(sorted([t.language.value for t in manifest.audio_tracks])),
        profile_version,  # Added: allows re-encoding when profile changes
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


def reserve_job_slot(
    idempotency_token: str,
    manifest_id: str,
    output_prefix: str,
) -> dict[str, Any]:
    """Reserve a slot for job submission using conditional write.

    This implements the first phase of a two-phase commit pattern:
    1. Reserve slot with PENDING status (this function)
    2. Update to SUBMITTED after MediaConvert accepts the job

    Uses conditional write to ensure only one Lambda wins the race.

    Args:
        idempotency_token: Token from generate_idempotency_token
        manifest_id: Manifest identifier
        output_prefix: S3 output prefix for the job

    Returns:
        Dictionary with:
        - reserved: True if slot was reserved, False if already taken
        - existing_job: If not reserved, info about the existing job
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
                "manifest_id": manifest_id,
                "status": "PENDING",  # Will be updated to SUBMITTED by Step Functions
                "output_prefix": output_prefix,
                "created_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
            },
            ConditionExpression="attribute_not_exists(idempotency_token)",
        )

        logger.info(
            "Reserved job slot",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "manifest_id": manifest_id,
            },
        )

        return {"reserved": True}

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Item already exists - another Lambda beat us to it
            logger.warning(
                "Job slot already reserved",
                extra={
                    "idempotency_token": idempotency_token[:16] + "...",
                    "manifest_id": manifest_id,
                },
            )
            # Fetch the existing record
            existing = check_idempotency(idempotency_token)
            return {
                "reserved": False,
                "existing_job": existing,
            }
        raise

    except Exception as e:
        logger.error(
            "Failed to reserve job slot",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "error": str(e),
            },
        )
        raise IdempotencyError(
            f"Failed to reserve job slot: {e}",
            {"idempotency_token": idempotency_token[:16], "error": str(e)},
        )


def store_job_reference(
    idempotency_token: str,
    job_id: str,
    manifest_id: str,
    status: str = "SUBMITTED",
    output_prefix: str | None = None,
) -> bool:
    """Store or update job reference for idempotency tracking.

    This is the second phase of the two-phase commit:
    Updates the PENDING reservation with actual job ID and SUBMITTED status.

    Args:
        idempotency_token: Token from generate_idempotency_token
        job_id: MediaConvert job ID
        manifest_id: Manifest identifier
        status: Job status (SUBMITTED, COMPLETE, ERROR, etc.)
        output_prefix: S3 output prefix (optional, may already be set)

    Returns:
        True if stored/updated successfully, False otherwise
    """
    settings = get_settings()

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(settings.idempotency_table)

        update_expr = "SET job_id = :job_id, #status = :status, updated_at = :updated_at"
        expr_values: dict[str, Any] = {
            ":job_id": job_id,
            ":status": status,
            ":updated_at": datetime.utcnow().isoformat(),
        }

        if output_prefix:
            update_expr += ", output_prefix = :output_prefix"
            expr_values[":output_prefix"] = output_prefix

        table.update_item(
            Key={"idempotency_token": idempotency_token},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=expr_values,
        )

        logger.info(
            "Stored job reference",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "job_id": job_id,
                "manifest_id": manifest_id,
                "status": status,
            },
        )

        return True

    except Exception as e:
        logger.error(
            "Failed to store job reference",
            extra={
                "idempotency_token": idempotency_token[:16] + "...",
                "error": str(e),
            },
        )
        return False


def update_job_status(
    idempotency_token: str,
    status: str,
    job_id: str | None = None,
    error_message: str | None = None,
) -> bool:
    """Update job status in idempotency table.

    Called by Step Functions when MediaConvert job completes or fails.

    Args:
        idempotency_token: Token from generate_idempotency_token
        status: New status (COMPLETE, ERROR, etc.)
        job_id: MediaConvert job ID (optional, if not already set)
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

        if job_id:
            update_expr += ", job_id = :job_id"
            expr_values[":job_id"] = job_id

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
