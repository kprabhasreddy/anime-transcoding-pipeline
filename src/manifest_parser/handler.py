"""Lambda handler for parsing and validating XML manifests.

This Lambda is triggered by S3 PutObject events when a new manifest
is uploaded to the input bucket's /manifests/ prefix.

Flow:
1. Receive S3 event
2. Download manifest XML
3. Parse and validate
4. Start Step Functions execution
"""

import json
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.data_classes import S3Event, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext

from ..shared.aws_clients import get_s3_client, get_stepfunctions_client
from ..shared.config import get_settings
from ..shared.exceptions import ManifestValidationError
from .validators import validate_business_rules, validate_manifest_dict
from .xml_parser import parse_anime_manifest

# Initialize Powertools
logger = Logger(service="manifest-parser")
tracer = Tracer(service="manifest-parser")
metrics = Metrics(service="manifest-parser", namespace="AnimeTranscoding")


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@event_source(data_class=S3Event)
def handler(event: S3Event, context: LambdaContext) -> dict[str, Any]:
    """Process S3 event for XML manifest upload.

    Args:
        event: S3 PutObject event
        context: Lambda context

    Returns:
        Response with manifest_id and execution ARN

    Raises:
        ManifestValidationError: If manifest is invalid
    """
    settings = get_settings()
    s3_client = get_s3_client()

    results = []

    for record in event.records:
        bucket = record.s3.bucket.name
        key = record.s3.get_object.key

        logger.info(
            "Processing manifest",
            extra={
                "bucket": bucket,
                "key": key,
                "event_time": record.event_time,
                "event_name": record.event_name,
            },
        )

        try:
            # Download manifest from S3
            with tracer.provider.in_subsegment("download_manifest"):
                response = s3_client.get_object(Bucket=bucket, Key=key)
                manifest_xml = response["Body"].read().decode("utf-8")

            logger.debug("Downloaded manifest", extra={"size_bytes": len(manifest_xml)})

            # Parse XML
            with tracer.provider.in_subsegment("parse_manifest"):
                manifest_dict = parse_anime_manifest(manifest_xml)

            # Validate and convert to Pydantic model
            with tracer.provider.in_subsegment("validate_manifest"):
                manifest = validate_manifest_dict(manifest_dict)
                warnings = validate_business_rules(manifest)

            if warnings:
                logger.warning(
                    "Manifest validation warnings",
                    extra={"warnings": warnings, "manifest_id": manifest.manifest_id},
                )

            # Emit success metric
            metrics.add_metric(
                name="ManifestsProcessed",
                unit=MetricUnit.Count,
                value=1,
            )
            metrics.add_metadata(key="manifest_id", value=manifest.manifest_id)
            metrics.add_metadata(key="series_id", value=manifest.episode.series_id)

            # Start pipeline execution
            result = _start_pipeline_execution(
                manifest=manifest,
                source_bucket=bucket,
                source_key=key,
                settings=settings,
            )

            results.append(result)

        except ManifestValidationError as e:
            logger.error(
                "Manifest validation failed",
                extra={
                    "error": e.to_dict(),
                    "bucket": bucket,
                    "key": key,
                },
            )
            metrics.add_metric(
                name="ManifestValidationErrors",
                unit=MetricUnit.Count,
                value=1,
            )
            raise

        except Exception as e:
            logger.exception(
                "Unexpected error processing manifest",
                extra={"bucket": bucket, "key": key},
            )
            metrics.add_metric(
                name="ManifestProcessingErrors",
                unit=MetricUnit.Count,
                value=1,
            )
            raise

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Processed {len(results)} manifest(s)",
            "results": results,
        }),
    }


@tracer.capture_method
def _start_pipeline_execution(
    manifest: Any,
    source_bucket: str,
    source_key: str,
    settings: Any,
) -> dict[str, Any]:
    """Start Step Functions execution for the transcoding pipeline.

    Args:
        manifest: Validated TranscodeManifest
        source_bucket: S3 bucket containing manifest
        source_key: S3 key of manifest
        settings: Application settings

    Returns:
        Execution result with ARN and manifest ID
    """
    # Build pipeline input
    pipeline_input = {
        "manifest": manifest.model_dump(mode="json"),
        "source_bucket": source_bucket,
        "source_key": source_key,
        "input_s3_uri": f"s3://{settings.input_bucket}/{manifest.mezzanine.file_path}",
        "output_s3_prefix": _build_output_prefix(manifest, settings),
        "force_reprocess": False,  # Default: respect idempotency
    }

    # Generate idempotent execution name
    # Using manifest_id + checksum prefix ensures we don't reprocess the same content
    execution_name = f"{manifest.manifest_id}-{manifest.mezzanine.checksum_md5[:8]}"

    # Check if Step Functions ARN is configured
    if not settings.step_function_arn:
        logger.warning(
            "Step Functions ARN not configured - skipping pipeline start",
            extra={"manifest_id": manifest.manifest_id},
        )
        return {
            "manifest_id": manifest.manifest_id,
            "status": "VALIDATION_ONLY",
            "message": "Step Functions not configured",
        }

    # Start execution
    sfn_client = get_stepfunctions_client()

    try:
        response = sfn_client.start_execution(
            stateMachineArn=settings.step_function_arn,
            name=execution_name,
            input=json.dumps(pipeline_input, default=str),
        )

        logger.info(
            "Started pipeline execution",
            extra={
                "execution_arn": response["executionArn"],
                "manifest_id": manifest.manifest_id,
                "execution_name": execution_name,
            },
        )

        return {
            "manifest_id": manifest.manifest_id,
            "execution_arn": response["executionArn"],
            "status": "PIPELINE_STARTED",
        }

    except sfn_client.exceptions.ExecutionAlreadyExists:
        # Idempotent - execution already exists
        logger.info(
            "Execution already exists (idempotent)",
            extra={
                "manifest_id": manifest.manifest_id,
                "execution_name": execution_name,
            },
        )
        return {
            "manifest_id": manifest.manifest_id,
            "status": "ALREADY_PROCESSING",
            "execution_name": execution_name,
        }


def _build_output_prefix(manifest: Any, settings: Any) -> str:
    """Build S3 output prefix for transcoded assets.

    Structure: s3://bucket/series_id/S{season}/E{episode}/manifest_id/

    Args:
        manifest: TranscodeManifest
        settings: Application settings

    Returns:
        Full S3 prefix for outputs
    """
    return (
        f"s3://{settings.output_bucket}/"
        f"{manifest.episode.series_id}/"
        f"S{manifest.episode.season_number:02d}/"
        f"E{manifest.episode.episode_number:04d}/"
        f"{manifest.manifest_id}"
    )


# For local testing
if __name__ == "__main__":
    # Test with sample event
    test_event = {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2024-01-15T10:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "test-input-bucket"},
                    "object": {"key": "manifests/test.xml"},
                },
            }
        ]
    }

    class MockContext:
        function_name = "test"
        memory_limit_in_mb = 128
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:test"
        aws_request_id = "test-request-id"

    # Note: This requires LocalStack or mocked AWS
    # result = handler(test_event, MockContext())
    # print(result)
