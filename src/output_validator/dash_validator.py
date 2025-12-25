"""DASH MPD manifest validation utilities.

Validates MPEG-DASH (Dynamic Adaptive Streaming over HTTP) output:
- MPD XML structure
- Period and AdaptationSet presence
- Representation configurations
- Audio/video codec declarations
"""

import xml.etree.ElementTree as ET
from typing import Any

# DASH namespace
DASH_NS = {"dash": "urn:mpeg:dash:schema:mpd:2011"}


def validate_dash_manifest(
    content: str,
    expected_variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate DASH MPD manifest structure.

    Checks:
    - Valid XML structure
    - MPD root element with namespace
    - At least one Period
    - Video AdaptationSet with Representations
    - Audio AdaptationSet(s)
    - Duration declaration

    Args:
        content: MPD manifest content (XML string)
        expected_variants: List of expected variant configs
            [{"resolution": "1920x1080", "codec": "h264"}, ...]

    Returns:
        Validation result dictionary

    Example:
        >>> with open("manifest.mpd") as f:
        ...     result = validate_dash_manifest(f.read())
        >>> print(result["passed"])
        True
    """
    result: dict[str, Any] = {
        "type": "dash_mpd",
        "passed": True,
        "checks": [],
    }

    # Check 1: Parse XML
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["passed"] = False
        result["checks"].append({
            "check": "xml_parse",
            "passed": False,
            "message": f"Invalid XML: {e}",
        })
        return result

    result["checks"].append({
        "check": "xml_parse",
        "passed": True,
        "message": "Valid XML document",
    })

    # Check 2: MPD root element
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if root_tag != "MPD":
        result["passed"] = False
        result["checks"].append({
            "check": "mpd_root",
            "passed": False,
            "message": f"Expected MPD root, got {root_tag}",
        })
        return result

    result["checks"].append({
        "check": "mpd_root",
        "passed": True,
        "message": "MPD root element present",
    })

    # Check 3: Duration
    duration = root.get("mediaPresentationDuration")
    result["checks"].append({
        "check": "duration",
        "passed": duration is not None,
        "message": f"Duration: {duration}" if duration else "Missing duration",
    })

    # Check 4: Type (static for VOD)
    mpd_type = root.get("type", "static")
    result["checks"].append({
        "check": "type",
        "passed": True,
        "message": f"MPD type: {mpd_type}",
    })

    # Check 5: Periods
    periods = root.findall(".//dash:Period", DASH_NS)
    if not periods:
        # Try without namespace
        periods = root.findall(".//Period")

    result["checks"].append({
        "check": "periods",
        "passed": len(periods) > 0,
        "message": f"Found {len(periods)} Period(s)",
    })

    if not periods:
        result["passed"] = False
        return result

    # Check 6: AdaptationSets
    video_sets = []
    audio_sets = []

    for period in periods:
        # Find AdaptationSets
        adaptation_sets = period.findall(".//dash:AdaptationSet", DASH_NS)
        if not adaptation_sets:
            adaptation_sets = period.findall(".//AdaptationSet")

        for adapt_set in adaptation_sets:
            content_type = adapt_set.get("contentType", "")
            mime_type = adapt_set.get("mimeType", "")

            if "video" in content_type or "video" in mime_type:
                video_sets.append(_parse_adaptation_set(adapt_set))
            elif "audio" in content_type or "audio" in mime_type:
                audio_sets.append(_parse_adaptation_set(adapt_set))

    result["checks"].append({
        "check": "video_adaptation_sets",
        "passed": len(video_sets) > 0,
        "message": f"Found {len(video_sets)} video AdaptationSet(s)",
        "details": video_sets,
    })

    if not video_sets:
        result["passed"] = False

    result["checks"].append({
        "check": "audio_adaptation_sets",
        "passed": len(audio_sets) > 0,
        "message": f"Found {len(audio_sets)} audio AdaptationSet(s)",
        "details": audio_sets,
    })

    # Check 7: Video Representations
    all_representations = []
    for vs in video_sets:
        all_representations.extend(vs.get("representations", []))

    result["checks"].append({
        "check": "video_representations",
        "passed": len(all_representations) > 0,
        "message": f"Found {len(all_representations)} video Representation(s)",
        "details": all_representations,
    })

    if not all_representations:
        result["passed"] = False

    # Check 8: Expected variants if provided
    if expected_variants:
        missing = _check_expected_variants(all_representations, expected_variants)
        if missing:
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

    return result


def _parse_adaptation_set(adapt_set: ET.Element) -> dict[str, Any]:
    """Parse AdaptationSet element."""
    representations = []

    # Find Representations
    reps = adapt_set.findall(".//dash:Representation", DASH_NS)
    if not reps:
        reps = adapt_set.findall(".//Representation")

    for rep in reps:
        representations.append({
            "id": rep.get("id", ""),
            "bandwidth": int(rep.get("bandwidth", 0)),
            "width": int(rep.get("width", 0)) if rep.get("width") else None,
            "height": int(rep.get("height", 0)) if rep.get("height") else None,
            "codecs": rep.get("codecs", ""),
        })

    return {
        "id": adapt_set.get("id", ""),
        "content_type": adapt_set.get("contentType", ""),
        "mime_type": adapt_set.get("mimeType", ""),
        "lang": adapt_set.get("lang", ""),
        "representations": representations,
    }


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
        exp_resolution = exp.get("resolution", "")

        if exp_resolution:
            exp_width, exp_height = map(int, exp_resolution.split("x"))

            for act in actual:
                if act.get("width") == exp_width and act.get("height") == exp_height:
                    found = True
                    break

        if not found:
            missing.append(f"{exp.get('codec', 'unknown')}@{exp_resolution}")

    return missing


def parse_mpd_duration(duration_str: str) -> float:
    """Parse ISO 8601 duration string to seconds.

    Format: PT{hours}H{minutes}M{seconds}S

    Args:
        duration_str: ISO 8601 duration (e.g., "PT24M0.5S")

    Returns:
        Duration in seconds

    Example:
        >>> parse_mpd_duration("PT1H30M45.5S")
        5445.5
    """
    import re

    if not duration_str or not duration_str.startswith("PT"):
        return 0.0

    # Remove 'PT' prefix
    duration_str = duration_str[2:]

    total_seconds = 0.0

    # Hours
    hours_match = re.search(r"(\d+(?:\.\d+)?)H", duration_str)
    if hours_match:
        total_seconds += float(hours_match.group(1)) * 3600

    # Minutes
    minutes_match = re.search(r"(\d+(?:\.\d+)?)M", duration_str)
    if minutes_match:
        total_seconds += float(minutes_match.group(1)) * 60

    # Seconds
    seconds_match = re.search(r"(\d+(?:\.\d+)?)S", duration_str)
    if seconds_match:
        total_seconds += float(seconds_match.group(1))

    return total_seconds
