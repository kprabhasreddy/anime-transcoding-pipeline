"""XML parsing utilities for anime manifests.

This module provides robust XML parsing with:
- Element-by-element extraction
- Graceful handling of optional fields
- Detailed error messages for debugging
- Support for localized titles (Japanese)
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from ..shared.exceptions import ManifestValidationError


def parse_anime_manifest(xml_content: str) -> dict[str, Any]:
    """Parse anime manifest XML into a dictionary structure.

    Args:
        xml_content: Raw XML string

    Returns:
        Dictionary matching TranscodeManifest schema

    Raises:
        ManifestValidationError: If XML is malformed or missing required elements

    Example:
        >>> xml = open("manifest.xml").read()
        >>> manifest = parse_anime_manifest(xml)
        >>> print(manifest["episode"]["series_title"])
        'Attack on Titan'
    """
    # Parse XML
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ManifestValidationError(
            f"Invalid XML format: {e}",
            {"parse_error": str(e), "position": getattr(e, "position", None)},
        )

    # Validate root element
    # Strip namespace if present
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if root_tag != "AnimeTranscodeManifest":
        raise ManifestValidationError(
            f"Invalid root element: expected 'AnimeTranscodeManifest', got '{root_tag}'",
            {"actual_root": root_tag},
        )

    # Extract manifest metadata
    manifest_version = root.get("version", "1.0")
    manifest_id = _get_required_text(root, "ManifestId")

    # Parse sections
    episode = _parse_episode(_get_required_element(root, "Episode"))
    mezzanine = _parse_mezzanine(_get_required_element(root, "Mezzanine"))
    audio_tracks = _parse_audio_tracks(_get_required_element(root, "AudioTracks"))

    # Optional sections
    subtitle_tracks = []
    subtitle_elem = root.find("SubtitleTracks")
    if subtitle_elem is not None:
        subtitle_tracks = _parse_subtitle_tracks(subtitle_elem)

    # Optional fields
    priority = int(_get_optional_text(root, "Priority", "0"))
    callback_url = _get_optional_text(root, "CallbackUrl")

    return {
        "manifest_version": manifest_version,
        "manifest_id": manifest_id,
        "episode": episode,
        "mezzanine": mezzanine,
        "audio_tracks": audio_tracks,
        "subtitle_tracks": subtitle_tracks,
        "priority": priority,
        "callback_url": callback_url,
    }


def _get_required_element(parent: ET.Element, tag: str) -> ET.Element:
    """Get a required child element or raise error.

    Args:
        parent: Parent XML element
        tag: Tag name to find

    Returns:
        Found element

    Raises:
        ManifestValidationError: If element not found
    """
    elem = parent.find(tag)
    if elem is None:
        raise ManifestValidationError(
            f"Missing required element: {tag}",
            {"parent": parent.tag, "missing_element": tag},
        )
    return elem


def _get_required_text(parent: ET.Element, tag: str) -> str:
    """Get required element text content.

    Args:
        parent: Parent XML element
        tag: Tag name to find

    Returns:
        Text content of element

    Raises:
        ManifestValidationError: If element not found or empty
    """
    elem = _get_required_element(parent, tag)
    if elem.text is None or elem.text.strip() == "":
        raise ManifestValidationError(
            f"Element '{tag}' cannot be empty",
            {"parent": parent.tag, "element": tag},
        )
    return elem.text.strip()


def _get_optional_text(
    parent: ET.Element,
    tag: str,
    default: str | None = None,
) -> str | None:
    """Get optional element text content.

    Args:
        parent: Parent XML element
        tag: Tag name to find
        default: Default value if not found

    Returns:
        Text content or default
    """
    elem = parent.find(tag)
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse boolean string value."""
    if value is None:
        return default
    return value.lower() in ("true", "yes", "1")


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string."""
    if not value:
        return None
    try:
        # Handle 'Z' suffix
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_episode(elem: ET.Element) -> dict[str, Any]:
    """Parse Episode element.

    Extracts all episode metadata including localized titles.
    """
    return {
        "series_id": _get_required_text(elem, "SeriesId"),
        "series_title": _get_required_text(elem, "SeriesTitle"),
        "series_title_ja": _get_optional_text(elem, "SeriesTitleJa"),
        "season_number": int(_get_required_text(elem, "SeasonNumber")),
        "episode_number": int(_get_required_text(elem, "EpisodeNumber")),
        "episode_title": _get_required_text(elem, "EpisodeTitle"),
        "episode_title_ja": _get_optional_text(elem, "EpisodeTitleJa"),
        "episode_description": _get_optional_text(elem, "EpisodeDescription"),
        "duration_seconds": float(_get_required_text(elem, "DurationSeconds")),
        "release_date": _parse_datetime(_get_optional_text(elem, "ReleaseDate")),
        "content_rating": _get_optional_text(elem, "ContentRating", "TV-14"),
        "is_simulcast": _parse_bool(_get_optional_text(elem, "IsSimulcast")),
        "is_dubbed": _parse_bool(_get_optional_text(elem, "IsDubbed")),
    }


def _parse_mezzanine(elem: ET.Element) -> dict[str, Any]:
    """Parse Mezzanine element.

    Extracts source file information and technical metadata.
    """
    return {
        "file_path": _get_required_text(elem, "FilePath"),
        "checksum_md5": _get_required_text(elem, "ChecksumMD5"),
        "checksum_xxhash": _get_optional_text(elem, "ChecksumXXHash"),
        "file_size_bytes": int(_get_required_text(elem, "FileSizeBytes")),
        "duration_seconds": float(_get_required_text(elem, "DurationSeconds")),
        "video_codec": _get_required_text(elem, "VideoCodec"),
        "audio_codec": _get_required_text(elem, "AudioCodec"),
        "resolution_width": int(_get_required_text(elem, "ResolutionWidth")),
        "resolution_height": int(_get_required_text(elem, "ResolutionHeight")),
        "frame_rate": float(_get_required_text(elem, "FrameRate")),
        "bitrate_kbps": int(_get_required_text(elem, "BitrateKbps")),
        "color_space": _get_optional_text(elem, "ColorSpace"),
        "bit_depth": _parse_optional_int(_get_optional_text(elem, "BitDepth")),
    }


def _parse_optional_int(value: str | None) -> int | None:
    """Parse optional integer value."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_audio_tracks(elem: ET.Element) -> list[dict[str, Any]]:
    """Parse AudioTracks element.

    Extracts all audio track configurations.
    """
    tracks = []
    for track_elem in elem.findall("AudioTrack"):
        tracks.append({
            "language": _get_required_text(track_elem, "Language"),
            "label": _get_required_text(track_elem, "Label"),
            "is_default": _parse_bool(_get_optional_text(track_elem, "IsDefault")),
            "channels": int(_get_optional_text(track_elem, "Channels", "2")),
            "track_index": int(_get_optional_text(track_elem, "TrackIndex", "1")),
        })

    if not tracks:
        raise ManifestValidationError(
            "At least one AudioTrack is required",
            {"element": "AudioTracks"},
        )

    return tracks


def _parse_subtitle_tracks(elem: ET.Element) -> list[dict[str, Any]]:
    """Parse SubtitleTracks element.

    Extracts all subtitle track configurations.
    """
    tracks = []
    for track_elem in elem.findall("SubtitleTrack"):
        tracks.append({
            "language": _get_required_text(track_elem, "Language"),
            "label": _get_required_text(track_elem, "Label"),
            "file_path": _get_required_text(track_elem, "FilePath"),
            "is_default": _parse_bool(_get_optional_text(track_elem, "IsDefault")),
            "is_forced": _parse_bool(_get_optional_text(track_elem, "IsForced")),
            "format": _get_optional_text(track_elem, "Format", "WebVTT"),
        })
    return tracks
