"""Lambda handler for output validation.

This Lambda validates transcoded outputs after MediaConvert completes.
Called by Step Functions when job status is COMPLETE.

Validates:
1. Output files exist in S3
2. HLS master playlist structure
3. DASH MPD structure
4. Duration matches input (within tolerance)
"""

from typing import Any

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from ..shared.aws_clients import get_s3_client
from ..shared.config import get_settings
from ..shared.exceptions import OutputValidationError
from ..shared.models import TranscodeManifest
from .dash_validator import validate_dash_manifest
from .duration_checker import validate_duration
from .hls_validator import validate_hls_master

logger = Logger(service="output-validator")
tracer = Tracer(service="output-validator")
metrics = Metrics(service="output-validator", namespace="AnimeTranscoding")


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Validate transcoded outputs.

    Args:
        event: Step Functions input with manifest and job details
        context: Lambda context

    Returns:
        Validation results for Step Functions

    Input event structure:
        {
            "manifest": {...},
            "job_id": "123456789-abcdef",
            "output_prefix": "s3://bucket/series/S01/E0001/manifest_id",
            "variants": [...]
        }

    Output structure:
        {
            "validation_passed": true,
            "validations": [
                {"type": "hls", "passed": true, "checks": [...]},
                {"type": "dash", "passed": true, "checks": [...]},
                {"type": "duration", "passed": true, "checks": [...]}
            ]
        }
    """
    settings = get_settings()

    # Parse inputs
    manifest = TranscodeManifest(**event["manifest"])
    output_prefix = event["output_prefix"]
    variants = event.get("variants", [])

    logger.info(
        "Starting output validation",
        extra={
            "manifest_id": manifest.manifest_id,
            "job_id": event.get("job_id"),
            "output_prefix": output_prefix,
        },
    )

    validation_result: dict[str, Any] = {
        "manifest_id": manifest.manifest_id,
        "job_id": event.get("job_id"),
        "validation_passed": True,
        "validations": [],
    }

    try:
        # Validation 1: Check HLS outputs
        with tracer.provider.in_subsegment("validate_hls"):
            hls_result = _validate_hls_outputs(
                output_prefix=output_prefix,
                expected_variants=variants,
            )
            validation_result["validations"].append(hls_result)
            if not hls_result["passed"]:
                validation_result["validation_passed"] = False

        # Validation 2: Check DASH outputs
        if settings.enable_dash:
            with tracer.provider.in_subsegment("validate_dash"):
                dash_result = _validate_dash_outputs(
                    output_prefix=output_prefix,
                    expected_variants=variants,
                )
                validation_result["validations"].append(dash_result)
                if not dash_result["passed"]:
                    validation_result["validation_passed"] = False

        # Validation 3: Check duration
        with tracer.provider.in_subsegment("validate_duration"):
            duration_result = validate_duration(
                output_prefix=output_prefix,
                expected_duration=manifest.mezzanine.duration_seconds,
            )
            validation_result["validations"].append(duration_result)
            if not duration_result["passed"]:
                # Duration mismatch is a warning, not a failure
                logger.warning(
                    "Duration mismatch detected",
                    extra={"result": duration_result},
                )

        # Emit metrics
        if validation_result["validation_passed"]:
            metrics.add_metric(
                name="OutputValidationSuccess",
                unit=MetricUnit.Count,
                value=1,
            )
        else:
            metrics.add_metric(
                name="OutputValidationFailure",
                unit=MetricUnit.Count,
                value=1,
            )

        metrics.add_metadata(key="manifest_id", value=manifest.manifest_id)

        logger.info(
            "Output validation complete",
            extra={
                "manifest_id": manifest.manifest_id,
                "validation_passed": validation_result["validation_passed"],
                "summary": [
                    {"type": v["type"], "passed": v["passed"]}
                    for v in validation_result["validations"]
                ],
            },
        )

        return validation_result

    except Exception as e:
        logger.exception("Output validation error")
        metrics.add_metric(
            name="OutputValidationErrors",
            unit=MetricUnit.Count,
            value=1,
        )
        raise OutputValidationError(
            f"Output validation failed: {e}",
            {"manifest_id": manifest.manifest_id, "error": str(e)},
        )


@tracer.capture_method
def _validate_hls_outputs(
    output_prefix: str,
    expected_variants: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate HLS output files and structure."""
    s3_client = get_s3_client()
    bucket, prefix = _parse_s3_prefix(output_prefix)

    result: dict[str, Any] = {
        "type": "hls",
        "passed": True,
        "checks": [],
    }

    hls_prefix = f"{prefix}/hls/"

    # Check 1: List HLS files
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=hls_prefix,
            MaxKeys=100,
        )

        files = [obj["Key"] for obj in response.get("Contents", [])]
        result["checks"].append({
            "check": "files_exist",
            "passed": len(files) > 0,
            "message": f"Found {len(files)} HLS file(s)",
        })

        if not files:
            result["passed"] = False
            return result

    except Exception as e:
        result["passed"] = False
        result["checks"].append({
            "check": "list_files",
            "passed": False,
            "message": f"Failed to list HLS files: {e}",
        })
        return result

    # Check 2: Find and validate master playlist
    master_files = [f for f in files if "master" in f.lower() or f.endswith("playlist.m3u8")]

    if not master_files:
        # Try to find any .m3u8 that looks like a master
        master_files = [f for f in files if f.endswith(".m3u8")]

    if master_files:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=master_files[0])
            content = response["Body"].read().decode("utf-8")

            # Validate master playlist
            master_result = validate_hls_master(content, expected_variants)
            result["checks"].extend(master_result["checks"])
            if not master_result["passed"]:
                result["passed"] = False

        except Exception as e:
            result["checks"].append({
                "check": "master_playlist",
                "passed": False,
                "message": f"Failed to read master playlist: {e}",
            })
    else:
        result["passed"] = False
        result["checks"].append({
            "check": "master_playlist",
            "passed": False,
            "message": "No master playlist found",
        })

    # Check 3: Verify segment files exist
    ts_files = [f for f in files if f.endswith(".ts")]
    result["checks"].append({
        "check": "segment_files",
        "passed": len(ts_files) > 0,
        "message": f"Found {len(ts_files)} segment file(s)",
    })

    if not ts_files:
        result["passed"] = False

    return result


@tracer.capture_method
def _validate_dash_outputs(
    output_prefix: str,
    expected_variants: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate DASH output files and structure."""
    s3_client = get_s3_client()
    bucket, prefix = _parse_s3_prefix(output_prefix)

    result: dict[str, Any] = {
        "type": "dash",
        "passed": True,
        "checks": [],
    }

    dash_prefix = f"{prefix}/dash/"

    # Check 1: List DASH files
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=dash_prefix,
            MaxKeys=100,
        )

        files = [obj["Key"] for obj in response.get("Contents", [])]
        result["checks"].append({
            "check": "files_exist",
            "passed": len(files) > 0,
            "message": f"Found {len(files)} DASH file(s)",
        })

        if not files:
            result["passed"] = False
            return result

    except Exception as e:
        result["passed"] = False
        result["checks"].append({
            "check": "list_files",
            "passed": False,
            "message": f"Failed to list DASH files: {e}",
        })
        return result

    # Check 2: Find and validate MPD manifest
    mpd_files = [f for f in files if f.endswith(".mpd")]

    if mpd_files:
        try:
            response = s3_client.get_object(Bucket=bucket, Key=mpd_files[0])
            content = response["Body"].read().decode("utf-8")

            # Validate MPD
            mpd_result = validate_dash_manifest(content, expected_variants)
            result["checks"].extend(mpd_result["checks"])
            if not mpd_result["passed"]:
                result["passed"] = False

        except Exception as e:
            result["checks"].append({
                "check": "mpd_manifest",
                "passed": False,
                "message": f"Failed to read MPD: {e}",
            })
    else:
        result["passed"] = False
        result["checks"].append({
            "check": "mpd_manifest",
            "passed": False,
            "message": "No MPD manifest found",
        })

    # Check 3: Verify segment files exist
    # MediaConvert outputs fMP4 segments with .mp4 extension (not .m4s)
    # Exclude initialization segments (which contain "init" in the name)
    segment_files = [
        f for f in files
        if f.endswith(".mp4") and "init" not in f.lower()
    ]
    result["checks"].append({
        "check": "segment_files",
        "passed": len(segment_files) > 0,
        "message": f"Found {len(segment_files)} segment file(s)",
    })

    if not segment_files:
        result["passed"] = False

    return result


def _parse_s3_prefix(uri: str) -> tuple[str, str]:
    """Parse S3 URI into bucket and prefix."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")

    path = uri[5:]
    parts = path.split("/", 1)

    return parts[0], parts[1] if len(parts) > 1 else ""
