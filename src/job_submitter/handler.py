"""Lambda handler for submitting MediaConvert jobs.

This Lambda is called by Step Functions after input validation passes.
It builds and submits the MediaConvert job, handling idempotency to
prevent duplicate transcoding.

Flow:
1. Generate idempotency token
2. Check for existing job
3. Build MediaConvert job settings
4. Submit job
5. Store job reference for tracking
"""

import json
from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from ..shared.aws_clients import get_mediaconvert_client
from ..shared.config import get_settings
from ..shared.exceptions import JobSubmissionError
from ..shared.models import TranscodeJobRequest, TranscodeManifest
from .abr_ladder import get_abr_ladder
from .idempotency import (
    check_idempotency,
    generate_idempotency_token,
    store_job_reference,
)
from .job_builder import build_mediaconvert_job

logger = Logger(service="job-submitter")
tracer = Tracer(service="job-submitter")
metrics = Metrics(service="job-submitter", namespace="AnimeTranscoding")


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Submit MediaConvert job for transcoding.

    Args:
        event: Step Functions input containing manifest and validation results
        context: Lambda context

    Returns:
        Job submission result for Step Functions

    Input event structure:
        {
            "manifest": {...},
            "input_s3_uri": "s3://bucket/path/to/mezzanine.mxf",
            "output_s3_prefix": "s3://bucket/output/path",
            "validation_result": {...}
        }

    Output structure:
        {
            "job_id": "1234567890123-abc123",
            "status": "SUBMITTED",
            "output_prefix": "s3://...",
            "variants": [...],
            "idempotent": false
        }
    """
    settings = get_settings()

    # Parse manifest
    manifest = TranscodeManifest(**event["manifest"])
    input_s3_uri = event["input_s3_uri"]
    output_s3_prefix = event["output_s3_prefix"]

    logger.info(
        "Starting job submission",
        extra={
            "manifest_id": manifest.manifest_id,
            "series_id": manifest.episode.series_id,
            "episode": manifest.episode.episode_code,
            "input_s3_uri": input_s3_uri,
        },
    )

    # Generate idempotency token
    idempotency_token = generate_idempotency_token(manifest)

    # Check for existing job (idempotency)
    with tracer.capture_method("check_idempotency"):
        existing_job = check_idempotency(idempotency_token)

    if existing_job:
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
            "job_id": existing_job.get("job_id"),
            "manifest_id": manifest.manifest_id,
            "status": "ALREADY_SUBMITTED",
            "idempotent": True,
            "original_status": existing_job.get("status"),
        }

    # Build ABR ladder based on source resolution
    with tracer.capture_method("build_abr_ladder"):
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
    with tracer.capture_method("build_job_settings"):
        job_settings = build_mediaconvert_job(job_request)

    # Check if in mock mode
    if settings.mock_mode:
        logger.info(
            "Mock mode - simulating job submission",
            extra={"manifest_id": manifest.manifest_id},
        )
        mock_job_id = f"mock-{manifest.manifest_id}-{idempotency_token[:8]}"

        # Store mock job reference
        store_job_reference(
            idempotency_token=idempotency_token,
            job_id=mock_job_id,
            manifest_id=manifest.manifest_id,
            status="MOCK_SUBMITTED",
        )

        return {
            "job_id": mock_job_id,
            "manifest_id": manifest.manifest_id,
            "status": "MOCK_SUBMITTED",
            "output_prefix": output_s3_prefix,
            "variants": [v.model_dump() for v in abr_variants],
            "idempotent": False,
            "mock_mode": True,
        }

    # Submit to MediaConvert
    with tracer.capture_method("submit_job"):
        result = _submit_mediaconvert_job(
            job_settings=job_settings,
            manifest=manifest,
            idempotency_token=idempotency_token,
            settings=settings,
        )

    # Store job reference for tracking
    store_job_reference(
        idempotency_token=idempotency_token,
        job_id=result["job_id"],
        manifest_id=manifest.manifest_id,
        status="SUBMITTED",
    )

    # Emit metrics
    metrics.add_metric(name="JobsSubmitted", unit=MetricUnit.Count, value=1)
    metrics.add_metadata(key="manifest_id", value=manifest.manifest_id)
    metrics.add_metadata(key="job_id", value=result["job_id"])

    logger.info(
        "Job submitted successfully",
        extra={
            "job_id": result["job_id"],
            "manifest_id": manifest.manifest_id,
            "output_prefix": output_s3_prefix,
        },
    )

    return {
        "job_id": result["job_id"],
        "manifest_id": manifest.manifest_id,
        "status": "SUBMITTED",
        "output_prefix": output_s3_prefix,
        "variants": [v.model_dump() for v in abr_variants],
        "idempotent": False,
    }


@tracer.capture_method
def _submit_mediaconvert_job(
    job_settings: dict[str, Any],
    manifest: TranscodeManifest,
    idempotency_token: str,
    settings: Any,
) -> dict[str, Any]:
    """Submit job to MediaConvert API.

    Args:
        job_settings: Built job settings from job_builder
        manifest: TranscodeManifest
        idempotency_token: Idempotency token for deduplication
        settings: Application settings

    Returns:
        Dictionary with job_id and status

    Raises:
        JobSubmissionError: If API call fails
    """
    mediaconvert = get_mediaconvert_client()

    try:
        response = mediaconvert.create_job(
            Role=settings.mediaconvert_role_arn,
            Settings=job_settings,
            Queue=settings.mediaconvert_queue_arn,
            UserMetadata={
                "manifest_id": manifest.manifest_id,
                "series_id": manifest.episode.series_id,
                "episode": manifest.episode.episode_code,
                "idempotency_token": idempotency_token[:32],
            },
            Tags={
                "Environment": settings.environment,
                "Pipeline": "anime-transcoding",
                "SeriesId": manifest.episode.series_id,
            },
            ClientRequestToken=idempotency_token,
        )

        job_id = response["Job"]["Id"]
        job_status = response["Job"]["Status"]

        return {
            "job_id": job_id,
            "status": job_status,
            "arn": response["Job"]["Arn"],
        }

    except mediaconvert.exceptions.ConflictException:
        # Job already exists with same idempotency token
        # This is actually OK - return the existing job
        logger.info(
            "Job already exists (MediaConvert conflict)",
            extra={"idempotency_token": idempotency_token[:16] + "..."},
        )

        # Try to find the existing job
        existing = check_idempotency(idempotency_token)
        if existing and existing.get("job_id"):
            return {
                "job_id": existing["job_id"],
                "status": "ALREADY_EXISTS",
            }

        raise JobSubmissionError(
            "Job already exists but couldn't retrieve ID",
            {"idempotency_token": idempotency_token[:16]},
        )

    except Exception as e:
        logger.exception("MediaConvert API error")
        metrics.add_metric(
            name="JobSubmissionErrors",
            unit=MetricUnit.Count,
            value=1,
        )
        raise JobSubmissionError(
            f"Failed to submit MediaConvert job: {e}",
            {
                "manifest_id": manifest.manifest_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
