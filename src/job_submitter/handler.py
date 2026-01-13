"""Lambda handler for building MediaConvert job configuration.

This Lambda is called by Step Functions after input validation passes.
It builds the MediaConvert job configuration and returns it for Step Functions
to submit directly using the .sync integration pattern.

Architecture note (v1.1):
    The Lambda no longer submits jobs directly. Instead, it returns the complete
    job configuration, and Step Functions uses mediaconvert:createJob.sync to
    submit the job and wait for completion. This provides:
    - Cleaner separation of concerns
    - Native Step Functions retry/error handling for MediaConvert
    - Simplified Lambda code (no API calls, just configuration)

Flow:
1. Generate idempotency token (includes profile version)
2. Check for existing job (skip if already processed, unless force_reprocess)
3. Build MediaConvert job settings
4. Reserve slot in DynamoDB (prevents race conditions)
5. Return settings for Step Functions to submit
"""

from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from ..shared.config import get_settings
from ..shared.models import TranscodeJobRequest, TranscodeManifest
from .abr_ladder import get_abr_ladder
from .idempotency import (
    check_idempotency,
    generate_idempotency_token,
    reserve_job_slot,
)
from .job_builder import build_mediaconvert_job

logger = Logger(service="job-submitter")
tracer = Tracer(service="job-submitter")
metrics = Metrics(service="job-submitter", namespace="AnimeTranscoding")

# Current transcode profile version - increment when encoding settings change
# This is included in idempotency token to allow re-processing with new settings
TRANSCODE_PROFILE_VERSION = "v1.0"


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Build MediaConvert job configuration for transcoding.

    Args:
        event: Step Functions input containing manifest and validation results
        context: Lambda context

    Returns:
        Job configuration for Step Functions to submit to MediaConvert

    Input event structure:
        {
            "manifest": {...},
            "input_s3_uri": "s3://bucket/path/to/mezzanine.mxf",
            "output_s3_prefix": "s3://bucket/output/path",
            "validation_result": {...},
            "force_reprocess": false  # Optional: bypass idempotency check
        }

    Output structure:
        {
            "job_settings": {...},           # MediaConvert job settings
            "job_metadata": {                # Metadata for tracking
                "manifest_id": "...",
                "idempotency_token": "...",
                "variants": [...]
            },
            "mediaconvert_role_arn": "...",  # Role for MediaConvert
            "mediaconvert_queue_arn": "...", # Queue to submit to
            "skip_transcode": false,         # True if idempotent skip
            "mock_mode": false               # True if in mock mode
        }
    """
    settings = get_settings()

    # Parse manifest
    manifest = TranscodeManifest(**event["manifest"])
    input_s3_uri = event["input_s3_uri"]
    output_s3_prefix = event["output_s3_prefix"]
    force_reprocess = event.get("force_reprocess", False)

    logger.info(
        "Building job configuration",
        extra={
            "manifest_id": manifest.manifest_id,
            "series_id": manifest.episode.series_id,
            "episode": manifest.episode.episode_code,
            "input_s3_uri": input_s3_uri,
            "force_reprocess": force_reprocess,
        },
    )

    # Generate idempotency token (includes profile version for re-encoding support)
    idempotency_token = generate_idempotency_token(
        manifest=manifest,
        profile_version=TRANSCODE_PROFILE_VERSION,
    )

    # Check for existing job (idempotency) unless force_reprocess is set
    if not force_reprocess:
        with tracer.provider.in_subsegment("check_idempotency"):
            existing_job = check_idempotency(idempotency_token)

        if existing_job and existing_job.get("status") in ("COMPLETE", "SUBMITTED", "PROGRESSING"):
            logger.info(
                "Returning existing job (idempotent)",
                extra={
                    "job_id": existing_job.get("job_id"),
                    "manifest_id": manifest.manifest_id,
                    "status": existing_job.get("status"),
                },
            )
            metrics.add_metric(
                name="IdempotentJobSkipped",
                unit=MetricUnit.Count,
                value=1,
            )
            return {
                "skip_transcode": True,
                "mock_mode": False,
                "idempotent": True,
                "existing_job": {
                    "job_id": existing_job.get("job_id"),
                    "status": existing_job.get("status"),
                    "output_prefix": existing_job.get("output_prefix"),
                },
                "job_settings": None,
                "job_metadata": {
                    "manifest_id": manifest.manifest_id,
                    "idempotency_token": idempotency_token,
                },
                "mediaconvert_role_arn": None,
                "mediaconvert_queue_arn": None,
            }

    # Build ABR ladder based on source resolution
    with tracer.provider.in_subsegment("build_abr_ladder"):
        abr_variants = get_abr_ladder(
            source_width=manifest.mezzanine.resolution_width,
            source_height=manifest.mezzanine.resolution_height,
            enable_h265=settings.enable_h265,
        )

    logger.info(
        "ABR ladder configured",
        extra={
            "variant_count": len(abr_variants),
            "variants": [
                {"resolution": v.resolution, "codec": v.codec.value, "bitrate": v.bitrate_kbps}
                for v in abr_variants
            ],
        },
    )

    # Map priority to queue tier
    queue_arn = _get_queue_for_priority(manifest.priority, settings)

    # Build job request
    job_request = TranscodeJobRequest(
        manifest=manifest,
        input_s3_uri=input_s3_uri,
        output_s3_prefix=output_s3_prefix,
        abr_variants=abr_variants,
        output_hls=True,
        output_dash=settings.enable_dash,
        idempotency_token=idempotency_token,
    )

    # Build MediaConvert job settings
    with tracer.provider.in_subsegment("build_job_settings"):
        job_settings = build_mediaconvert_job(job_request)

    # Reserve slot in idempotency table (prevents race conditions)
    with tracer.provider.in_subsegment("reserve_job_slot"):
        reservation = reserve_job_slot(
            idempotency_token=idempotency_token,
            manifest_id=manifest.manifest_id,
            output_prefix=output_s3_prefix,
        )

    if not reservation["reserved"]:
        # Another process already reserved this slot
        logger.info(
            "Job slot already reserved by another process",
            extra={"manifest_id": manifest.manifest_id},
        )
        return {
            "skip_transcode": True,
            "mock_mode": False,
            "idempotent": True,
            "existing_job": reservation.get("existing_job"),
            "job_settings": None,
            "job_metadata": {
                "manifest_id": manifest.manifest_id,
                "idempotency_token": idempotency_token,
            },
            "mediaconvert_role_arn": None,
            "mediaconvert_queue_arn": None,
        }

    # Emit metrics
    metrics.add_metric(name="JobsConfigured", unit=MetricUnit.Count, value=1)
    metrics.add_metadata(key="manifest_id", value=manifest.manifest_id)

    # Check if in mock mode
    if settings.mock_mode:
        logger.info(
            "Mock mode - returning mock job configuration",
            extra={"manifest_id": manifest.manifest_id},
        )
        return {
            "skip_transcode": False,
            "mock_mode": True,
            "idempotent": False,
            "existing_job": None,
            "job_settings": job_settings,
            "job_metadata": {
                "manifest_id": manifest.manifest_id,
                "idempotency_token": idempotency_token,
                "output_prefix": output_s3_prefix,
                "variants": [v.model_dump() for v in abr_variants],
                "profile_version": TRANSCODE_PROFILE_VERSION,
            },
            "mediaconvert_role_arn": settings.mediaconvert_role_arn,
            "mediaconvert_queue_arn": queue_arn,
        }

    logger.info(
        "Job configuration built successfully",
        extra={
            "manifest_id": manifest.manifest_id,
            "output_prefix": output_s3_prefix,
            "queue_arn": queue_arn,
        },
    )

    return {
        "skip_transcode": False,
        "mock_mode": False,
        "idempotent": False,
        "existing_job": None,
        "job_settings": job_settings,
        "job_metadata": {
            "manifest_id": manifest.manifest_id,
            "idempotency_token": idempotency_token,
            "output_prefix": output_s3_prefix,
            "variants": [v.model_dump() for v in abr_variants],
            "profile_version": TRANSCODE_PROFILE_VERSION,
        },
        "mediaconvert_role_arn": settings.mediaconvert_role_arn,
        "mediaconvert_queue_arn": queue_arn,
        "user_metadata": {
            "manifest_id": manifest.manifest_id,
            "series_id": manifest.episode.series_id,
            "episode": manifest.episode.episode_code,
            "idempotency_token": idempotency_token[:32],
        },
        "tags": {
            "Environment": settings.environment,
            "Pipeline": "anime-transcoding",
            "SeriesId": manifest.episode.series_id,
            "ManifestId": manifest.manifest_id,
        },
    }


def _get_queue_for_priority(priority: int, settings: Any) -> str:
    """Map manifest priority to MediaConvert queue.

    Priority levels:
    - 0-3: Standard queue (default)
    - 4-7: High priority queue (future)
    - 8-10: Reserved/on-demand queue (future)

    Args:
        priority: Manifest priority (0-10)
        settings: Application settings

    Returns:
        MediaConvert queue ARN
    """
    # For v1, use single queue. Multi-queue support planned for v2.
    # if priority >= 8 and hasattr(settings, 'mediaconvert_reserved_queue_arn'):
    #     return settings.mediaconvert_reserved_queue_arn
    # elif priority >= 4 and hasattr(settings, 'mediaconvert_high_priority_queue_arn'):
    #     return settings.mediaconvert_high_priority_queue_arn
    return settings.mediaconvert_queue_arn
