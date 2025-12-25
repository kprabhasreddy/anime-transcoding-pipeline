"""HLS playlist validation utilities.

Validates HLS (HTTP Live Streaming) output conformance:
- Master playlist structure
- Media playlist structure
- Variant stream presence
- Audio/video track references
"""

import re
from typing import Any


def validate_hls_master(
    content: str,
    expected_variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate HLS master playlist structure.

    Checks:
    - Valid #EXTM3U header
    - EXT-X-VERSION tag presence
    - STREAM-INF entries for video variants
    - MEDIA entries for audio tracks

    Args:
        content: Master playlist content (.m3u8)
        expected_variants: List of expected variant configs
            [{"resolution": "1920x1080", "codec": "h264"}, ...]

    Returns:
        Validation result dictionary

    Example:
        >>> with open("master.m3u8") as f:
        ...     result = validate_hls_master(f.read())
        >>> print(result["passed"])
        True
    """
    result: dict[str, Any] = {
        "type": "hls_master",
        "passed": True,
        "checks": [],
    }

    lines = content.strip().split("\n")

    # Check 1: EXTM3U header
    if not lines or not lines[0].startswith("#EXTM3U"):
        result["passed"] = False
        result["checks"].append({
            "check": "extm3u_header",
            "passed": False,
            "message": "Missing #EXTM3U header",
        })
        return result

    result["checks"].append({
        "check": "extm3u_header",
        "passed": True,
        "message": "#EXTM3U header present",
    })

    # Check 2: Version tag
    has_version = any(line.startswith("#EXT-X-VERSION") for line in lines)
    result["checks"].append({
        "check": "version_tag",
        "passed": has_version,
        "message": "EXT-X-VERSION present" if has_version else "Missing EXT-X-VERSION",
    })

    # Check 3: Parse variant streams
    variants = _parse_stream_inf(content)
    result["checks"].append({
        "check": "variant_streams",
        "passed": len(variants) > 0,
        "message": f"Found {len(variants)} variant stream(s)",
        "details": variants,
    })

    if not variants:
        result["passed"] = False

    # Check 4: Validate expected variants if provided
    if expected_variants:
        missing = _check_expected_variants(variants, expected_variants)
        if missing:
            result["passed"] = False
            result["checks"].append({
                "check": "expected_variants",
                "passed": False,
                "message": f"Missing expected variants: {missing}",
            })
        else:
            result["checks"].append({
                "check": "expected_variants",
                "passed": True,
                "message": "All expected variants present",
            })

    # Check 5: Audio tracks
    audio_tracks = _parse_media_tags(content, "AUDIO")
    result["checks"].append({
        "check": "audio_tracks",
        "passed": True,  # Audio tracks are optional in master
        "message": f"Found {len(audio_tracks)} audio track(s)",
        "details": audio_tracks,
    })

    return result


def validate_hls_playlist(
    content: str,
    expected_variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate HLS media playlist (segment list).

    This is an alias for validate_hls_master for backwards compatibility.
    For media playlists, use validate_hls_media.
    """
    return validate_hls_master(content, expected_variants)


def validate_hls_media(content: str) -> dict[str, Any]:
    """Validate HLS media playlist (segment list).

    Checks:
    - Valid #EXTM3U header
    - TARGET-DURATION tag
    - EXTINF entries for segments
    - ENDLIST tag (for VOD)

    Args:
        content: Media playlist content

    Returns:
        Validation result dictionary
    """
    result: dict[str, Any] = {
        "type": "hls_media",
        "passed": True,
        "checks": [],
    }

    lines = content.strip().split("\n")

    # Check 1: EXTM3U header
    if not lines or not lines[0].startswith("#EXTM3U"):
        result["passed"] = False
        result["checks"].append({
            "check": "extm3u_header",
            "passed": False,
            "message": "Missing #EXTM3U header",
        })
        return result

    result["checks"].append({
        "check": "extm3u_header",
        "passed": True,
        "message": "#EXTM3U header present",
    })

    # Check 2: Target duration
    target_duration = None
    for line in lines:
        if line.startswith("#EXT-X-TARGETDURATION:"):
            target_duration = int(line.split(":")[1])
            break

    result["checks"].append({
        "check": "target_duration",
        "passed": target_duration is not None,
        "message": f"Target duration: {target_duration}s" if target_duration else "Missing target duration",
    })

    if target_duration is None:
        result["passed"] = False

    # Check 3: Count segments
    segments = _parse_extinf(content)
    result["checks"].append({
        "check": "segments",
        "passed": len(segments) > 0,
        "message": f"Found {len(segments)} segment(s)",
        "details": {
            "count": len(segments),
            "total_duration": sum(s["duration"] for s in segments),
        },
    })

    if not segments:
        result["passed"] = False

    # Check 4: ENDLIST for VOD
    has_endlist = any(line.startswith("#EXT-X-ENDLIST") for line in lines)
    result["checks"].append({
        "check": "endlist",
        "passed": has_endlist,
        "message": "VOD playlist complete" if has_endlist else "Missing ENDLIST (live stream?)",
    })

    return result


def _parse_stream_inf(content: str) -> list[dict[str, Any]]:
    """Parse EXT-X-STREAM-INF entries from master playlist."""
    variants = []
    lines = content.strip().split("\n")

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = _parse_attributes(line.split(":", 1)[1])

            # Get the URI from next line
            uri = lines[i + 1] if i + 1 < len(lines) else ""

            variants.append({
                "bandwidth": int(attrs.get("BANDWIDTH", 0)),
                "resolution": attrs.get("RESOLUTION", ""),
                "codecs": attrs.get("CODECS", ""),
                "audio": attrs.get("AUDIO", ""),
                "uri": uri,
            })

    return variants


def _parse_media_tags(content: str, media_type: str) -> list[dict[str, Any]]:
    """Parse EXT-X-MEDIA entries of specified type."""
    tracks = []

    for line in content.split("\n"):
        if line.startswith("#EXT-X-MEDIA:"):
            attrs = _parse_attributes(line.split(":", 1)[1])

            if attrs.get("TYPE") == media_type:
                tracks.append({
                    "type": attrs.get("TYPE"),
                    "group_id": attrs.get("GROUP-ID", "").strip('"'),
                    "language": attrs.get("LANGUAGE", "").strip('"'),
                    "name": attrs.get("NAME", "").strip('"'),
                    "default": attrs.get("DEFAULT", "NO") == "YES",
                    "uri": attrs.get("URI", "").strip('"'),
                })

    return tracks


def _parse_extinf(content: str) -> list[dict[str, Any]]:
    """Parse EXTINF entries from media playlist."""
    segments = []
    lines = content.strip().split("\n")

    for i, line in enumerate(lines):
        if line.startswith("#EXTINF:"):
            # Format: #EXTINF:6.000,
            duration_str = line.split(":")[1].rstrip(",")
            try:
                duration = float(duration_str)
            except ValueError:
                duration = 0.0

            # Get segment URI from next line
            uri = lines[i + 1] if i + 1 < len(lines) else ""

            segments.append({
                "duration": duration,
                "uri": uri,
            })

    return segments


def _parse_attributes(attr_string: str) -> dict[str, str]:
    """Parse HLS attribute string into dictionary.

    Handles quoted values and comma-separated attributes.
    """
    attrs = {}

    # Regex to match KEY=VALUE or KEY="VALUE"
    pattern = r'([A-Z-]+)=("[^"]*"|[^,]*)'

    for match in re.finditer(pattern, attr_string):
        key = match.group(1)
        value = match.group(2).strip('"')
        attrs[key] = value

    return attrs


def _check_expected_variants(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> list[str]:
    """Check if all expected variants are present.

    Returns list of missing variants.
    """
    missing = []

    for exp in expected:
        found = False
        for act in actual:
            # Match by resolution
            if exp.get("resolution") and act.get("resolution"):
                if exp["resolution"] == act["resolution"]:
                    found = True
                    break

        if not found:
            missing.append(f"{exp.get('codec', 'unknown')}@{exp.get('resolution', 'unknown')}")

    return missing
