"""Manifest validation utilities.

This module provides:
- XML schema validation (XSD)
- Business rule validation
- Cross-field consistency checks
"""

from typing import Any

from lxml import etree

from ..shared.exceptions import ManifestValidationError
from ..shared.models import TranscodeManifest


# Supported audio languages (ISO 639-1)
SUPPORTED_AUDIO_LANGUAGES = {"ja", "en", "es", "pt", "fr", "de", "ko", "zh", "it", "ru"}

# Supported subtitle languages (BCP 47)
SUPPORTED_SUBTITLE_LANGUAGES = {
    "en",
    "es-419",
    "es-ES",
    "pt-BR",
    "pt-PT",
    "fr",
    "de",
    "it",
    "ar",
    "ru",
    "zh-Hans",
    "zh-Hant",
    "ko",
}

# Supported video codecs for mezzanine input
SUPPORTED_MEZZANINE_CODECS = {
    "ProRes 422",
    "ProRes 422 HQ",
    "ProRes 422 LT",
    "ProRes 4444",
    "DNxHD",
    "DNxHR",
    "XDCAM",
    "AVC-Intra",
    "H.264",
    "H.265",
    "HEVC",
}

# Content ratings
VALID_CONTENT_RATINGS = {"TV-Y", "TV-Y7", "TV-G", "TV-PG", "TV-14", "TV-MA"}


def validate_manifest_schema(xml_content: str, xsd_path: str | None = None) -> bool:
    """Validate XML manifest against XSD schema.

    Args:
        xml_content: Raw XML string
        xsd_path: Path to XSD schema file (optional)

    Returns:
        True if valid

    Raises:
        ManifestValidationError: If schema validation fails
    """
    try:
        # Parse XML
        doc = etree.fromstring(xml_content.encode())

        # If no XSD provided, just verify it's well-formed XML
        if xsd_path is None:
            return True

        # Load and validate against XSD
        with open(xsd_path, "rb") as f:
            schema_doc = etree.parse(f)
            schema = etree.XMLSchema(schema_doc)

        if not schema.validate(doc):
            errors = [str(err) for err in schema.error_log]
            raise ManifestValidationError(
                "XML schema validation failed",
                {"errors": errors},
            )

        return True

    except etree.XMLSyntaxError as e:
        raise ManifestValidationError(
            f"XML syntax error: {e}",
            {"line": e.lineno, "column": e.offset},
        )


def validate_business_rules(manifest: TranscodeManifest) -> list[str]:
    """Validate manifest against business rules.

    These are streaming platform content rules beyond schema validation.

    Args:
        manifest: Parsed TranscodeManifest object

    Returns:
        List of warning messages (empty if all valid)

    Raises:
        ManifestValidationError: If critical validation fails
    """
    warnings: list[str] = []
    errors: list[str] = []

    # === Audio Track Validation ===
    _validate_audio_tracks(manifest, errors, warnings)

    # === Subtitle Track Validation ===
    _validate_subtitle_tracks(manifest, errors, warnings)

    # === Mezzanine Validation ===
    _validate_mezzanine(manifest, errors, warnings)

    # === Episode Metadata Validation ===
    _validate_episode(manifest, errors, warnings)

    # === Cross-Field Consistency ===
    _validate_consistency(manifest, errors, warnings)

    # Raise if critical errors found
    if errors:
        raise ManifestValidationError(
            f"Business rule validation failed: {len(errors)} error(s)",
            {"errors": errors, "warnings": warnings},
        )

    return warnings


def _validate_audio_tracks(
    manifest: TranscodeManifest,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate audio track configuration."""
    tracks = manifest.audio_tracks

    # Check for exactly one default
    defaults = [t for t in tracks if t.is_default]
    if len(defaults) != 1:
        errors.append(
            f"Exactly one audio track must be default (found {len(defaults)})"
        )

    # Check for Japanese original (recommended for anime)
    has_japanese = any(t.language.value == "ja" for t in tracks)
    if not has_japanese:
        warnings.append("No Japanese audio track - unusual for anime content")

    # Check for duplicate languages
    languages = [t.language.value for t in tracks]
    if len(languages) != len(set(languages)):
        warnings.append("Duplicate audio language detected")

    # Validate language codes
    for track in tracks:
        if track.language.value not in SUPPORTED_AUDIO_LANGUAGES:
            warnings.append(f"Unusual audio language: {track.language.value}")


def _validate_subtitle_tracks(
    manifest: TranscodeManifest,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate subtitle track configuration."""
    tracks = manifest.subtitle_tracks

    if not tracks:
        # No subtitles is valid but unusual for anime
        warnings.append("No subtitle tracks - consider adding for accessibility")
        return

    # Check for at least one default if subtitles exist
    defaults = [t for t in tracks if t.is_default]
    if len(defaults) == 0:
        warnings.append("No default subtitle track set")
    elif len(defaults) > 1:
        warnings.append("Multiple default subtitle tracks")

    # Validate subtitle file paths
    for track in tracks:
        if not track.file_path.endswith((".vtt", ".srt", ".ttml")):
            warnings.append(
                f"Unusual subtitle format for {track.language}: {track.file_path}"
            )


def _validate_mezzanine(
    manifest: TranscodeManifest,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate mezzanine file metadata."""
    mezz = manifest.mezzanine

    # Check resolution bounds
    if mezz.resolution_width < 720 or mezz.resolution_height < 480:
        warnings.append(
            f"Low resolution source: {mezz.resolution}. Consider using HD source."
        )

    if mezz.resolution_width > 3840 or mezz.resolution_height > 2160:
        warnings.append(f"Very high resolution source: {mezz.resolution}")

    # Check frame rate
    valid_frame_rates = {23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0}
    if not any(abs(mezz.frame_rate - fr) < 0.01 for fr in valid_frame_rates):
        warnings.append(f"Unusual frame rate: {mezz.frame_rate}")

    # Check codec
    codec_found = False
    for supported in SUPPORTED_MEZZANINE_CODECS:
        if supported.lower() in mezz.video_codec.lower():
            codec_found = True
            break

    if not codec_found:
        warnings.append(f"Unusual mezzanine codec: {mezz.video_codec}")

    # Check duration sanity
    if mezz.duration_seconds < 60:
        warnings.append("Very short content (< 1 minute)")
    elif mezz.duration_seconds > 7200:
        warnings.append("Very long content (> 2 hours)")

    # Check bitrate
    if mezz.bitrate_kbps < 10000:
        warnings.append("Low mezzanine bitrate - may affect output quality")


def _validate_episode(
    manifest: TranscodeManifest,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate episode metadata."""
    ep = manifest.episode

    # Check content rating
    if ep.content_rating.value not in VALID_CONTENT_RATINGS:
        warnings.append(f"Invalid content rating: {ep.content_rating}")

    # Check season/episode bounds
    if ep.season_number > 50:
        warnings.append(f"High season number: {ep.season_number}")

    if ep.episode_number > 500:
        warnings.append(f"High episode number: {ep.episode_number}")

    # Check for dub consistency
    if ep.is_dubbed:
        has_non_japanese = any(
            t.language.value != "ja" for t in manifest.audio_tracks
        )
        if not has_non_japanese:
            warnings.append("Marked as dubbed but only Japanese audio track present")


def _validate_consistency(
    manifest: TranscodeManifest,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate cross-field consistency."""
    # Duration consistency (already checked in model, but double-check)
    ep_dur = manifest.episode.duration_seconds
    mezz_dur = manifest.mezzanine.duration_seconds

    if abs(ep_dur - mezz_dur) > 1.0:
        errors.append(
            f"Duration mismatch: episode={ep_dur}s, mezzanine={mezz_dur}s"
        )

    # File path consistency
    mezz_path = manifest.mezzanine.file_path.lower()
    series_id = manifest.episode.series_id.lower()

    if series_id not in mezz_path:
        warnings.append(
            f"Series ID '{series_id}' not found in mezzanine path - verify correct file"
        )


def validate_manifest_dict(manifest_dict: dict[str, Any]) -> TranscodeManifest:
    """Validate and convert manifest dictionary to Pydantic model.

    Args:
        manifest_dict: Dictionary from XML parser

    Returns:
        Validated TranscodeManifest object

    Raises:
        ManifestValidationError: If validation fails
    """
    try:
        return TranscodeManifest(**manifest_dict)
    except Exception as e:
        raise ManifestValidationError(
            f"Manifest validation failed: {e}",
            {"validation_error": str(e)},
        )
