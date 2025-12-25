"""Message formatters for notifications.

Formats structured notifications for different channels:
- Email (human-readable)
- JSON (webhook consumption)
"""

import json
from datetime import datetime, timezone
from typing import Any


def format_success_message(
    manifest: dict[str, Any],
    job_id: str | None,
    output_prefix: str | None,
    variants: list[dict[str, Any]],
    environment: str,
) -> str:
    """Format success notification message.

    Args:
        manifest: Original manifest data
        job_id: MediaConvert job ID
        output_prefix: S3 output location
        variants: List of output variants
        environment: Deployment environment

    Returns:
        Formatted message string
    """
    episode = manifest.get("episode", {})
    mezzanine = manifest.get("mezzanine", {})

    # Build human-readable message
    lines = [
        "=" * 60,
        "TRANSCODING COMPLETE",
        "=" * 60,
        "",
        "Episode Details:",
        f"  Series: {episode.get('series_title', 'Unknown')}",
        f"  Episode: S{episode.get('season_number', 0):02d}E{episode.get('episode_number', 0):02d}",
        f"  Title: {episode.get('episode_title', 'Unknown')}",
        "",
        "Job Details:",
        f"  Manifest ID: {manifest.get('manifest_id', 'Unknown')}",
        f"  Job ID: {job_id or 'N/A'}",
        f"  Environment: {environment}",
        f"  Completed: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Source:",
        f"  Resolution: {mezzanine.get('resolution_width', '?')}x{mezzanine.get('resolution_height', '?')}",
        f"  Duration: {_format_duration(mezzanine.get('duration_seconds', 0))}",
        f"  Codec: {mezzanine.get('video_codec', 'Unknown')}",
        "",
        "Output:",
        f"  Location: {output_prefix or 'N/A'}",
        f"  Variants: {len(variants)}",
    ]

    if variants:
        lines.append("")
        lines.append("  Variant Details:")
        for v in variants:
            lines.append(
                f"    - {v.get('resolution', '?')}: "
                f"{v.get('bitrate_kbps', 0)} Kbps ({v.get('codec', 'h264')})"
            )

    lines.extend([
        "",
        "-" * 60,
        "This is an automated notification from the Anime Transcoding Pipeline.",
    ])

    return "\n".join(lines)


def format_error_message(
    manifest: dict[str, Any],
    error_type: str,
    error: dict[str, Any],
    job_id: str | None,
    environment: str,
) -> str:
    """Format error notification message.

    Args:
        manifest: Original manifest data
        error_type: Type of error (VALIDATION_FAILED, etc.)
        error: Error details
        job_id: MediaConvert job ID (if available)
        environment: Deployment environment

    Returns:
        Formatted message string
    """
    episode = manifest.get("episode", {})

    # Error type descriptions
    error_descriptions = {
        "VALIDATION_FAILED": "Input validation failed. The mezzanine file did not pass quality checks.",
        "JOB_SUBMISSION_FAILED": "Failed to submit the transcoding job to MediaConvert.",
        "TRANSCODE_FAILED": "MediaConvert job failed during transcoding.",
        "OUTPUT_VALIDATION_FAILED": "Output validation failed. The transcoded files did not pass quality checks.",
        "UNKNOWN": "An unknown error occurred in the pipeline.",
    }

    lines = [
        "!" * 60,
        "TRANSCODING FAILED",
        "!" * 60,
        "",
        f"Error Type: {error_type}",
        f"Description: {error_descriptions.get(error_type, 'Unknown error')}",
        "",
        "Episode Details:",
        f"  Series: {episode.get('series_title', 'Unknown')}",
        f"  Episode: S{episode.get('season_number', 0):02d}E{episode.get('episode_number', 0):02d}",
        f"  Title: {episode.get('episode_title', 'Unknown')}",
        "",
        "Job Details:",
        f"  Manifest ID: {manifest.get('manifest_id', 'Unknown')}",
        f"  Job ID: {job_id or 'N/A'}",
        f"  Environment: {environment}",
        f"  Failed: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Error Details:",
    ]

    # Add error information
    if isinstance(error, dict):
        if "Error" in error:
            lines.append(f"  Error Code: {error.get('Error', 'Unknown')}")
        if "Cause" in error:
            lines.append(f"  Cause: {error.get('Cause', 'Unknown')}")
        if "message" in error:
            lines.append(f"  Message: {error.get('message', 'Unknown')}")

        # Add any other error fields
        for key, value in error.items():
            if key not in ("Error", "Cause", "message"):
                lines.append(f"  {key}: {value}")
    else:
        lines.append(f"  {error}")

    lines.extend([
        "",
        "Recommended Actions:",
    ])

    # Add action recommendations based on error type
    if error_type == "VALIDATION_FAILED":
        lines.extend([
            "  1. Verify the mezzanine file exists at the specified S3 location",
            "  2. Check that the file checksum matches the manifest",
            "  3. Ensure the file is not corrupted",
        ])
    elif error_type == "JOB_SUBMISSION_FAILED":
        lines.extend([
            "  1. Check MediaConvert service quotas",
            "  2. Verify IAM permissions are correct",
            "  3. Review CloudWatch logs for the job-submitter Lambda",
        ])
    elif error_type == "TRANSCODE_FAILED":
        lines.extend([
            "  1. Review MediaConvert job logs in the AWS Console",
            "  2. Check if the source file format is supported",
            "  3. Verify the job settings are valid for the source",
        ])
    elif error_type == "OUTPUT_VALIDATION_FAILED":
        lines.extend([
            "  1. Check the output S3 bucket for generated files",
            "  2. Verify HLS/DASH playlist structure",
            "  3. Review CloudWatch logs for the output-validator Lambda",
        ])
    else:
        lines.extend([
            "  1. Review CloudWatch logs for the relevant Lambda function",
            "  2. Check Step Functions execution history",
            "  3. Contact the platform team if the issue persists",
        ])

    lines.extend([
        "",
        "-" * 60,
        "This is an automated notification from the Anime Transcoding Pipeline.",
        "Do not reply to this message.",
    ])

    return "\n".join(lines)


def format_json_notification(
    notification_type: str,
    manifest: dict[str, Any],
    details: dict[str, Any],
    environment: str,
) -> str:
    """Format notification as JSON for webhook consumption.

    Args:
        notification_type: SUCCESS or ERROR
        manifest: Original manifest data
        details: Additional notification details
        environment: Deployment environment

    Returns:
        JSON string
    """
    payload = {
        "type": notification_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "manifest_id": manifest.get("manifest_id"),
        "episode": {
            "series_id": manifest.get("episode", {}).get("series_id"),
            "series_title": manifest.get("episode", {}).get("series_title"),
            "season": manifest.get("episode", {}).get("season_number"),
            "episode": manifest.get("episode", {}).get("episode_number"),
            "title": manifest.get("episode", {}).get("episode_title"),
        },
        "details": details,
    }

    return json.dumps(payload, indent=2, default=str)


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS format."""
    if not seconds:
        return "00:00:00"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
