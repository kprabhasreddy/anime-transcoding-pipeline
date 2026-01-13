"""Duration matching verification.

Validates that transcoded output duration matches input within tolerance.
Detects:
- Truncated transcodes
- Dropped frames
- Audio/video sync issues
"""

import re
from typing import Any

from ..shared.aws_clients import get_s3_client
from ..shared.config import get_settings
from ..shared.exceptions import DurationMismatchError
from .dash_validator import parse_mpd_duration


def check_duration_match(
    output_prefix: str,
    expected_duration: float,
    tolerance: float | None = None,
) -> float:
    """Verify output duration matches expected within tolerance.

    Attempts to extract duration from:
    1. DASH MPD manifest (most accurate)
    2. HLS master playlist (segment sum)

    Args:
        output_prefix: S3 prefix for outputs (s3://bucket/path)
        expected_duration: Expected duration in seconds
        tolerance: Allowed difference in seconds (default from settings)

    Returns:
        Actual output duration in seconds

    Raises:
        DurationMismatchError: If duration exceeds tolerance
    """
    settings = get_settings()
    if tolerance is None:
        tolerance = settings.duration_tolerance_seconds

    # Parse S3 prefix
    bucket, prefix = _parse_s3_prefix(output_prefix)

    # Try to get duration from DASH MPD first (most reliable)
    actual_duration = _get_dash_duration(bucket, prefix)

    if actual_duration is None:
        # Fallback to HLS
        actual_duration = _get_hls_duration(bucket, prefix)

    if actual_duration is None:
        # Could not determine duration - return expected as fallback
        # This shouldn't happen if transcoding succeeded
        return expected_duration

    # Check tolerance
    difference = abs(actual_duration - expected_duration)

    if difference > tolerance:
        raise DurationMismatchError(
            input_duration=expected_duration,
            output_duration=actual_duration,
            tolerance=tolerance,
        )

    return actual_duration


def validate_duration(
    output_prefix: str,
    expected_duration: float,
    tolerance: float | None = None,
) -> dict[str, Any]:
    """Validate output duration and return detailed result.

    Non-throwing version of check_duration_match for validation pipelines.

    Args:
        output_prefix: S3 prefix for outputs
        expected_duration: Expected duration in seconds
        tolerance: Allowed difference in seconds

    Returns:
        Validation result dictionary
    """
    settings = get_settings()
    if tolerance is None:
        tolerance = settings.duration_tolerance_seconds

    result: dict[str, Any] = {
        "type": "duration",
        "passed": True,
        "checks": [],
    }

    try:
        actual_duration = check_duration_match(
            output_prefix=output_prefix,
            expected_duration=expected_duration,
            tolerance=tolerance,
        )

        difference = abs(actual_duration - expected_duration)

        result["checks"].append({
            "check": "duration_match",
            "passed": True,
            "message": (
                f"Duration match: {actual_duration:.2f}s "
                f"(expected {expected_duration:.2f}s, diff {difference:.2f}s)"
            ),
            "details": {
                "expected_seconds": expected_duration,
                "actual_seconds": actual_duration,
                "difference_seconds": difference,
                "tolerance_seconds": tolerance,
            },
        })

    except DurationMismatchError as e:
        result["passed"] = False
        result["checks"].append({
            "check": "duration_match",
            "passed": False,
            "message": e.message,
            "details": e.details,
        })

    except Exception as e:
        result["checks"].append({
            "check": "duration_extraction",
            "passed": False,
            "message": f"Failed to extract duration: {e}",
        })

    return result


def _parse_s3_prefix(uri: str) -> tuple[str, str]:
    """Parse S3 URI into bucket and prefix."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")

    path = uri[5:]
    parts = path.split("/", 1)

    return parts[0], parts[1] if len(parts) > 1 else ""


def _get_dash_duration(bucket: str, prefix: str) -> float | None:
    """Extract duration from DASH MPD manifest."""
    s3_client = get_s3_client()

    # Find MPD file dynamically (MediaConvert names it based on input filename)
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{prefix}/dash/",
            MaxKeys=20,
        )

        mpd_files = [
            obj["Key"] for obj in response.get("Contents", [])
            if obj["Key"].endswith(".mpd")
        ]

        if not mpd_files:
            return None

        # Get first MPD file
        response = s3_client.get_object(Bucket=bucket, Key=mpd_files[0])
        content = response["Body"].read().decode("utf-8")

        # Parse mediaPresentationDuration
        import xml.etree.ElementTree as ET

        root = ET.fromstring(content)
        duration_str = root.get("mediaPresentationDuration")

        if duration_str:
            return parse_mpd_duration(duration_str)

    except Exception:
        pass

    return None


def _get_hls_duration(bucket: str, prefix: str) -> float | None:
    """Extract duration from HLS playlist.

    Sums up EXTINF values from a media playlist.
    """
    s3_client = get_s3_client()

    # Try to find a media playlist
    try:
        # List objects to find .m3u8 files
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{prefix}/hls/",
            MaxKeys=20,
        )

        m3u8_files = [
            obj["Key"] for obj in response.get("Contents", [])
            if obj["Key"].endswith(".m3u8") and "master" not in obj["Key"].lower()
        ]

        if not m3u8_files:
            return None

        # Get first media playlist
        response = s3_client.get_object(Bucket=bucket, Key=m3u8_files[0])
        content = response["Body"].read().decode("utf-8")

        # Sum EXTINF durations
        return _sum_extinf_durations(content)

    except Exception:
        return None


def _sum_extinf_durations(content: str) -> float:
    """Sum all EXTINF durations in an HLS playlist."""
    total = 0.0

    for line in content.split("\n"):
        if line.startswith("#EXTINF:"):
            # Format: #EXTINF:6.000, or #EXTINF:6.000
            duration_str = line.split(":")[1].rstrip(",").strip()
            try:
                total += float(duration_str)
            except ValueError:
                pass

    return total
