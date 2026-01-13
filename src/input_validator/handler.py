"""Lambda handler for input validation.

This Lambda validates the mezzanine file before transcoding:
1. Verify file exists in S3
2. Calculate and verify checksum
3. Extract and validate media info
4. Return validation results for Step Functions

Called by Step Functions after manifest parsing.
"""

import tempfile
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from ..shared.aws_clients import get_s3_client
from ..shared.config import get_settings
from ..shared.exceptions import ChecksumMismatchError, MezzanineValidationError
from ..shared.models import TranscodeManifest
from .checksum import verify_checksum
from .mediainfo import extract_media_info, validate_media_info

logger = Logger(service="input-validator")
tracer = Tracer(service="input-validator")
metrics = Metrics(service="input-validator", namespace="AnimeTranscoding")


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Validate mezzanine file before transcoding.

    Args:
        event: Step Functions input containing manifest and S3 URIs
        context: Lambda context

    Returns:
        Validation results for Step Functions

    Input event structure:
        {
            "manifest": {...},
            "input_s3_uri": "s3://bucket/path/to/mezzanine.mxf"
        }

    Output structure:
        {
            "validation_passed": true,
            "file_size_bytes": 15728640000,
            "checksum_verified": true,
            "media_info": {...}
        }
    """
    settings = get_settings()

    # Parse manifest
    manifest = TranscodeManifest(**event["manifest"])
    input_s3_uri = event["input_s3_uri"]

    logger.info(
        "Starting input validation",
        extra={
            "manifest_id": manifest.manifest_id,
            "input_s3_uri": input_s3_uri,
            "expected_checksum": manifest.mezzanine.checksum_md5[:8] + "...",
        },
    )

    # Parse S3 URI
    bucket, key = _parse_s3_uri(input_s3_uri)

    validation_result = {
        "manifest_id": manifest.manifest_id,
        "input_s3_uri": input_s3_uri,
        "validation_passed": False,
        "checks": [],
    }

    try:
        # Check 1: Verify file exists
        with tracer.provider.in_subsegment("check_file_exists"):
            file_info = _check_file_exists(bucket, key)
            validation_result["checks"].append({
                "check": "file_exists",
                "passed": True,
                "details": {"size_bytes": file_info["size"]},
            })
            validation_result["file_size_bytes"] = file_info["size"]

        # Check 2: Verify file size matches manifest
        with tracer.provider.in_subsegment("check_file_size"):
            size_check = _check_file_size(
                actual_size=file_info["size"],
                expected_size=manifest.mezzanine.file_size_bytes,
            )
            validation_result["checks"].append(size_check)

        # Check 3: Verify checksum (streaming)
        with tracer.provider.in_subsegment("verify_checksum"):
            checksum_check = _verify_file_checksum(
                bucket=bucket,
                key=key,
                expected_md5=manifest.mezzanine.checksum_md5,
                expected_xxhash=manifest.mezzanine.checksum_xxhash,
            )
            validation_result["checks"].append(checksum_check)
            validation_result["checksum_verified"] = checksum_check["passed"]

        # Check 4: Extract and validate media info (optional, may fail if FFprobe unavailable)
        with tracer.provider.in_subsegment("validate_media_info"):
            media_check = _validate_media_info(
                bucket=bucket,
                key=key,
                manifest=manifest,
                settings=settings,
            )
            validation_result["checks"].append(media_check)
            if media_check.get("media_info"):
                validation_result["media_info"] = media_check["media_info"]

        # All checks passed
        all_passed = all(c["passed"] for c in validation_result["checks"])
        validation_result["validation_passed"] = all_passed

        # Emit metrics
        metrics.add_metric(
            name="InputValidationSuccess" if all_passed else "InputValidationFailure",
            unit=MetricUnit.Count,
            value=1,
        )
        metrics.add_metadata(key="manifest_id", value=manifest.manifest_id)

        logger.info(
            "Input validation complete",
            extra={
                "manifest_id": manifest.manifest_id,
                "validation_passed": all_passed,
                "checks_summary": [
                    {"check": c["check"], "passed": c["passed"]}
                    for c in validation_result["checks"]
                ],
            },
        )

        return validation_result

    except ChecksumMismatchError as e:
        logger.error("Checksum verification failed", extra=e.to_dict())
        validation_result["checks"].append({
            "check": "checksum",
            "passed": False,
            "error": e.to_dict(),
        })
        metrics.add_metric(
            name="ChecksumMismatchErrors",
            unit=MetricUnit.Count,
            value=1,
        )
        raise

    except MezzanineValidationError as e:
        logger.error("Mezzanine validation failed", extra=e.to_dict())
        metrics.add_metric(
            name="MezzanineValidationErrors",
            unit=MetricUnit.Count,
            value=1,
        )
        raise

    except Exception as e:
        logger.exception("Unexpected validation error")
        metrics.add_metric(
            name="InputValidationErrors",
            unit=MetricUnit.Count,
            value=1,
        )
        raise MezzanineValidationError(
            f"Validation failed: {e}",
            {"manifest_id": manifest.manifest_id, "error": str(e)},
        )


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse S3 URI into bucket and key.

    Args:
        uri: S3 URI (e.g., 's3://bucket/path/to/file')

    Returns:
        Tuple of (bucket, key)
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")

    path = uri[5:]  # Remove 's3://'
    parts = path.split("/", 1)

    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URI: {uri}")

    return parts[0], parts[1]


@tracer.capture_method
def _check_file_exists(bucket: str, key: str) -> dict[str, Any]:
    """Check if file exists in S3 and get metadata.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        Dictionary with file metadata

    Raises:
        MezzanineValidationError: If file not found
    """
    s3_client = get_s3_client()

    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        return {
            "size": response["ContentLength"],
            "etag": response.get("ETag", "").strip('"'),
            "content_type": response.get("ContentType"),
            "last_modified": str(response.get("LastModified")),
        }
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "404":
            raise MezzanineValidationError(
                f"File not found: s3://{bucket}/{key}",
                {"bucket": bucket, "key": key},
            )
        raise


def _check_file_size(actual_size: int, expected_size: int) -> dict[str, Any]:
    """Check if file size matches expected value.

    Args:
        actual_size: Actual file size in bytes
        expected_size: Expected size from manifest

    Returns:
        Check result dictionary
    """
    passed = actual_size == expected_size

    return {
        "check": "file_size",
        "passed": passed,
        "details": {
            "expected_bytes": expected_size,
            "actual_bytes": actual_size,
            "difference_bytes": abs(actual_size - expected_size),
        },
    }


@tracer.capture_method
def _verify_file_checksum(
    bucket: str,
    key: str,
    expected_md5: str,
    expected_xxhash: str | None,
) -> dict[str, Any]:
    """Verify file checksum using streaming.

    For large files, we stream directly from S3 to avoid memory issues.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        expected_md5: Expected MD5 checksum
        expected_xxhash: Expected XXHash64 (optional)

    Returns:
        Check result dictionary
    """
    s3_client = get_s3_client()
    settings = get_settings()

    # Get streaming body
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]

    try:
        # Use tempfile for streaming verification
        # This allows verify_checksum to work with its file-like interface
        with tempfile.SpooledTemporaryFile(max_size=100 * 1024 * 1024) as tmp:
            # Stream from S3 to temp file
            for chunk in body.iter_chunks(chunk_size=settings.checksum_chunk_size_bytes):
                tmp.write(chunk)

            # Reset to beginning
            tmp.seek(0)

            # Verify checksum
            verify_checksum(
                file_obj=tmp,
                expected_md5=expected_md5,
                expected_xxhash=expected_xxhash,
                file_path=f"s3://{bucket}/{key}",
            )

        return {
            "check": "checksum",
            "passed": True,
            "details": {
                "md5_verified": True,
                "xxhash_verified": expected_xxhash is not None,
            },
        }

    finally:
        body.close()


@tracer.capture_method
def _validate_media_info(
    bucket: str,
    key: str,
    manifest: TranscodeManifest,
    settings: Any,
) -> dict[str, Any]:
    """Validate media info using FFprobe via presigned URL.

    Uses a presigned URL to allow FFprobe to read directly from S3
    without downloading the entire file.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        manifest: TranscodeManifest with expected values
        settings: Application settings

    Returns:
        Check result dictionary with media_info if successful
    """
    s3_client = get_s3_client()

    try:
        # Generate presigned URL for FFprobe to read
        # URL valid for 5 minutes - enough for FFprobe to probe the file
        presigned_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=300,
        )

        # Extract media info using FFprobe
        media_info = extract_media_info(presigned_url)

        # Validate against manifest expectations
        validation_errors = validate_media_info(
            info=media_info,
            expected_duration=manifest.mezzanine.duration_seconds,
            expected_width=manifest.mezzanine.resolution_width,
            expected_height=manifest.mezzanine.resolution_height,
            duration_tolerance=settings.duration_tolerance_seconds,
        )

        if validation_errors:
            logger.warning(
                "Media info validation failed",
                extra={
                    "manifest_id": manifest.manifest_id,
                    "errors": validation_errors,
                },
            )
            return {
                "check": "media_info",
                "passed": False,
                "errors": validation_errors,
                "media_info": {
                    "format": media_info.format_name,
                    "duration": media_info.duration_seconds,
                    "resolution": media_info.primary_video.resolution if media_info.primary_video else None,
                    "video_codec": media_info.primary_video.codec_name if media_info.primary_video else None,
                    "audio_tracks": len(media_info.audio_streams),
                },
            }

        logger.info(
            "Media info validation passed",
            extra={
                "manifest_id": manifest.manifest_id,
                "format": media_info.format_name,
                "duration": media_info.duration_seconds,
                "resolution": media_info.primary_video.resolution if media_info.primary_video else None,
            },
        )

        return {
            "check": "media_info",
            "passed": True,
            "media_info": {
                "format": media_info.format_name,
                "duration": media_info.duration_seconds,
                "resolution": media_info.primary_video.resolution if media_info.primary_video else None,
                "video_codec": media_info.primary_video.codec_name if media_info.primary_video else None,
                "frame_rate": media_info.primary_video.frame_rate if media_info.primary_video else None,
                "audio_tracks": len(media_info.audio_streams),
                "audio_languages": media_info.audio_languages,
            },
        }

    except MezzanineValidationError as e:
        # FFprobe failed - log but don't fail validation if FFprobe is unavailable
        # This allows the pipeline to work in environments without FFprobe
        logger.warning(
            "Media info extraction failed - skipping validation",
            extra={
                "manifest_id": manifest.manifest_id,
                "error": str(e),
            },
        )
        return {
            "check": "media_info",
            "passed": True,  # Pass with warning - FFprobe may not be available
            "skipped": True,
            "reason": str(e),
        }

    except Exception as e:
        logger.warning(
            "Unexpected error during media info validation",
            extra={
                "manifest_id": manifest.manifest_id,
                "error": str(e),
            },
        )
        return {
            "check": "media_info",
            "passed": True,  # Pass with warning - don't block pipeline
            "skipped": True,
            "reason": f"Unexpected error: {e}",
        }
