"""MediaConvert job builder.

Constructs complete MediaConvert job settings for anime transcoding.

Output structure:
- HLS: H.264 variants only (universal compatibility)
- DASH: H.264 + H.265 variants (modern devices get HEVC benefits)
- Multi-audio: All language tracks as separate renditions
- Subtitles: WebVTT sidecar files
"""

from typing import Any

from ..shared.models import ABRVariant, SubtitleTrack, TranscodeJobRequest, VideoCodec
from .abr_ladder import calculate_qvbr_settings, get_audio_settings

# ISO 639-1 (2-letter) to ISO 639-2/T (3-letter) mapping for MediaConvert
# MediaConvert requires 3-letter codes (ISO 639-2)
ISO_639_1_TO_639_2: dict[str, str] = {
    "en": "ENG",
    "ja": "JPN",
    "es": "SPA",
    "fr": "FRA",
    "de": "DEU",
    "it": "ITA",
    "pt": "POR",
    "ru": "RUS",
    "zh": "ZHO",
    "ko": "KOR",
    "ar": "ARA",
    "hi": "HIN",
    "th": "THA",
    "vi": "VIE",
    "id": "IND",
    "ms": "MSA",
    "tl": "TGL",
    "pl": "POL",
    "nl": "NLD",
    "tr": "TUR",
    "sv": "SWE",
    "da": "DAN",
    "no": "NOR",
    "fi": "FIN",
    "cs": "CES",
    "hu": "HUN",
    "ro": "RON",
    "el": "ELL",
    "he": "HEB",
    "uk": "UKR",
}


def _get_iso_639_2_code(iso_639_1: str) -> str:
    """Convert ISO 639-1 (2-letter) to ISO 639-2 (3-letter) language code.

    MediaConvert requires 3-letter language codes.

    Args:
        iso_639_1: ISO 639-1 code like "en", "ja", or variants like "en-US"

    Returns:
        ISO 639-2 3-letter code like "ENG", "JPN"

    Raises:
        ValueError: If the language code is not in the supported mapping
    """
    code = iso_639_1.lower().split("-")[0]  # Handle variants like "en-US"
    if code not in ISO_639_1_TO_639_2:
        raise ValueError(
            f"Unsupported language code '{iso_639_1}'. "
            f"Supported codes: {', '.join(sorted(ISO_639_1_TO_639_2.keys()))}"
        )
    return ISO_639_1_TO_639_2[code]


def build_mediaconvert_job(request: TranscodeJobRequest) -> dict[str, Any]:
    """Build complete MediaConvert job settings.

    Creates a job configuration that outputs:
    - HLS playlist with H.264 variants for broad compatibility
    - DASH manifest with H.264 + H.265 for bandwidth efficiency
    - Separate audio renditions for each language
    - WebVTT subtitle tracks

    Args:
        request: TranscodeJobRequest with manifest and settings

    Returns:
        MediaConvert job settings dictionary (passed to create_job API)

    Example:
        >>> request = TranscodeJobRequest(...)
        >>> settings = build_mediaconvert_job(request)
        >>> mediaconvert.create_job(Settings=settings, ...)
    """
    manifest = request.manifest

    # Separate variants by codec for output group routing
    h264_variants = [v for v in request.abr_variants if v.codec == VideoCodec.H264]
    h265_variants = [v for v in request.abr_variants if v.codec == VideoCodec.H265]

    job_settings: dict[str, Any] = {
        "TimecodeConfig": {
            "Source": "ZEROBASED",
        },
        "Inputs": [_build_input(request)],
        "OutputGroups": [],
    }

    # Add HLS output group (H.264 only for Safari/iOS compatibility)
    if request.output_hls and h264_variants:
        job_settings["OutputGroups"].append(
            _build_hls_output_group(request, h264_variants)
        )

    # Add DASH output group (H.264 + H.265 for modern devices)
    if request.output_dash:
        all_variants = h264_variants + h265_variants
        if all_variants:
            job_settings["OutputGroups"].append(
                _build_dash_output_group(request, all_variants)
            )

    return job_settings


def _build_input(request: TranscodeJobRequest) -> dict[str, Any]:
    """Build input configuration with audio and caption selectors.

    Creates separate audio selectors for each language track,
    and caption selectors for subtitle files.
    """
    manifest = request.manifest

    # Build audio selectors
    audio_selectors: dict[str, Any] = {}
    for idx, track in enumerate(manifest.audio_tracks, start=1):
        selector_name = f"Audio_{track.language.value}"
        audio_selectors[selector_name] = {
            "DefaultSelection": "DEFAULT" if track.is_default else "NOT_DEFAULT",
            "SelectorType": "TRACK",
            "Tracks": [track.track_index],
        }

    # Build caption selectors for subtitle tracks
    caption_selectors: dict[str, Any] = {}
    for track in manifest.subtitle_tracks:
        selector_name = f"Caption_{track.language.value}"
        # Construct full S3 URI for subtitle file
        # Subtitle paths are relative to the manifest location
        input_bucket = request.input_s3_uri.rsplit("/", 1)[0]
        subtitle_uri = f"{input_bucket}/{track.file_path}"

        # Map subtitle format to MediaConvert source type
        format_to_source_type = {
            "SCC": "SCC",
            "TTML": "TTML",
            "WebVTT": "WEBVTT",
            "SRT": "SRT",
        }
        source_type = format_to_source_type.get(track.format.value, "WEBVTT")

        caption_selectors[selector_name] = {
            "SourceSettings": {
                "SourceType": source_type,
                "FileSourceSettings": {
                    "SourceFile": subtitle_uri,
                },
            },
        }

    input_config: dict[str, Any] = {
        "FileInput": request.input_s3_uri,
        "AudioSelectors": audio_selectors,
        "VideoSelector": {
            "ColorSpace": "FOLLOW",
            "Rotate": "AUTO",
        },
        "TimecodeSource": "ZEROBASED",
        "FilterEnable": "AUTO",
        "PsiControl": "USE_PSI",
        "FilterStrength": 0,
        "DeblockFilter": "DISABLED",
        "DenoiseFilter": "DISABLED",
    }

    # Only add caption selectors if there are subtitle tracks
    if caption_selectors:
        input_config["CaptionSelectors"] = caption_selectors

    return input_config


def _build_hls_output_group(
    request: TranscodeJobRequest,
    variants: list[ABRVariant],
) -> dict[str, Any]:
    """Build HLS output group configuration.

    HLS (HTTP Live Streaming) is the primary format for:
    - iOS/Safari
    - Most smart TVs
    - Broad device compatibility

    Structure:
    - Master playlist (.m3u8) with all variants
    - Media playlists for each variant
    - TS segment files
    """
    outputs = []

    # Create video output for each variant
    for variant in variants:
        output = _build_hls_video_output(request, variant)
        outputs.append(output)

    # Create separate audio outputs for each language
    for track in request.manifest.audio_tracks:
        output = _build_hls_audio_output(request, track)
        outputs.append(output)

    # Create caption outputs for each subtitle track
    for track in request.manifest.subtitle_tracks:
        output = _build_hls_caption_output(request, track)
        outputs.append(output)

    # Build HLS group settings
    hls_settings: dict[str, Any] = {
        "SegmentLength": 6,
        "MinSegmentLength": 0,
        "Destination": f"{request.output_s3_prefix}/hls/",
        "ManifestDurationFormat": "FLOATING_POINT",
        "SegmentControl": "SEGMENTED_FILES",
        "OutputSelection": "MANIFESTS_AND_SEGMENTS",
        "StreamInfResolution": "INCLUDE",
        "ClientCache": "ENABLED",
        "ManifestCompression": "NONE",
        "DirectoryStructure": "SINGLE_DIRECTORY",
        "ProgramDateTime": "INCLUDE",
        "ProgramDateTimePeriod": 600,
        "CodecSpecification": "RFC_4281",
    }

    # Only include caption settings if we have subtitles
    if request.manifest.subtitle_tracks:
        hls_settings["CaptionLanguageSetting"] = "INSERT"
        # Build caption language mappings for each subtitle track
        hls_settings["CaptionLanguageMappings"] = [
            {
                "LanguageCode": _get_iso_639_2_code(track.language.value),
                "LanguageDescription": track.label,
                "CaptionChannel": idx + 1,
            }
            for idx, track in enumerate(request.manifest.subtitle_tracks)
        ]
    else:
        hls_settings["CaptionLanguageSetting"] = "OMIT"

    return {
        "Name": "HLS",
        "OutputGroupSettings": {
            "Type": "HLS_GROUP_SETTINGS",
            "HlsGroupSettings": hls_settings,
        },
        "Outputs": outputs,
    }


def _build_hls_video_output(
    request: TranscodeJobRequest,
    variant: ABRVariant,
) -> dict[str, Any]:
    """Build HLS video output for a single variant."""
    return {
        "NameModifier": f"_{variant.name}",
        "ContainerSettings": {
            "Container": "M3U8",
            "M3u8Settings": {
                "AudioFramesPerPes": 4,
                "PcrControl": "PCR_EVERY_PES_PACKET",
                "PmtPid": 480,
                "PrivateMetadataPid": 503,
                "ProgramNumber": 1,
                "PatInterval": 0,
                "PmtInterval": 0,
                "VideoPid": 481,
                "AudioPids": [482, 483, 484, 485, 486, 487, 488, 489],
            },
        },
        "VideoDescription": {
            "Width": variant.width,
            "Height": variant.height,
            "CodecSettings": calculate_qvbr_settings(variant),
            "ScalingBehavior": "DEFAULT",
            "TimecodeInsertion": "DISABLED",
            "AntiAlias": "ENABLED",
            "RespondToAfd": "NONE",
            "Sharpness": 50,
            "AfdSignaling": "NONE",
            "DropFrameTimecode": "ENABLED",
        },
        "AudioDescriptions": [
            {
                "AudioSourceName": f"Audio_{track.language.value}",
                "AudioTypeControl": "FOLLOW_INPUT",
                "LanguageCode": _get_iso_639_2_code(track.language.value),
                "LanguageCodeControl": "USE_CONFIGURED",
                "CodecSettings": get_audio_settings(track.channels),
            }
            for track in request.manifest.audio_tracks
        ],
    }


def _build_hls_audio_output(
    request: TranscodeJobRequest,
    track: Any,
) -> dict[str, Any]:
    """Build HLS audio-only output for a language track."""
    return {
        "NameModifier": f"_audio_{track.language.value}",
        "ContainerSettings": {
            "Container": "M3U8",
            "M3u8Settings": {
                "AudioFramesPerPes": 4,
                "PcrControl": "PCR_EVERY_PES_PACKET",
                "PmtPid": 480,
                "ProgramNumber": 1,
            },
        },
        "AudioDescriptions": [
            {
                "AudioSourceName": f"Audio_{track.language.value}",
                "AudioTypeControl": "FOLLOW_INPUT",
                "LanguageCode": _get_iso_639_2_code(track.language.value),
                "LanguageCodeControl": "USE_CONFIGURED",
                "CodecSettings": get_audio_settings(track.channels),
                "StreamName": track.label,
            }
        ],
    }


def _build_hls_caption_output(
    request: TranscodeJobRequest,
    track: SubtitleTrack,
) -> dict[str, Any]:
    """Build HLS WebVTT caption output for a subtitle track.

    Outputs subtitles as WebVTT sidecar files referenced in the HLS playlist.
    """
    # Map language code to ISO 639-2 (3-letter) for MediaConvert
    lang_code = _get_iso_639_2_code(track.language.value)

    return {
        "NameModifier": f"_caption_{track.language.value}",
        "ContainerSettings": {
            "Container": "RAW",
        },
        "CaptionDescriptions": [
            {
                "CaptionSelectorName": f"Caption_{track.language.value}",
                "DestinationSettings": {
                    "DestinationType": "WEBVTT",
                    "WebvttDestinationSettings": {
                        "StylePassthrough": "STRICT",
                    },
                },
                "LanguageCode": lang_code,
                "LanguageDescription": track.label,
            }
        ],
    }


def _build_dash_output_group(
    request: TranscodeJobRequest,
    variants: list[ABRVariant],
) -> dict[str, Any]:
    """Build DASH output group configuration.

    MPEG-DASH provides:
    - H.265/HEVC support for bandwidth efficiency
    - Better DRM integration (Widevine, PlayReady)
    - Standard-based (ISO/IEC 23009)

    Structure:
    - MPD manifest
    - Initialization segments (init.m4s)
    - Media segments (segment_XXX.m4s)
    """
    outputs = []

    # Create video output for each variant
    for variant in variants:
        output = _build_dash_video_output(request, variant)
        outputs.append(output)

    # Create audio outputs for each language
    for track in request.manifest.audio_tracks:
        output = _build_dash_audio_output(request, track)
        outputs.append(output)

    return {
        "Name": "DASH",
        "OutputGroupSettings": {
            "Type": "DASH_ISO_GROUP_SETTINGS",
            "DashIsoGroupSettings": {
                "SegmentLength": 6,
                "Destination": f"{request.output_s3_prefix}/dash/",
                "FragmentLength": 2,
                "SegmentControl": "SEGMENTED_FILES",
                "HbbtvCompliance": "NONE",
                "MpdProfile": "MAIN_PROFILE",
                "WriteSegmentTimelineInRepresentation": "ENABLED",
            },
        },
        "Outputs": outputs,
    }


def _build_dash_video_output(
    request: TranscodeJobRequest,
    variant: ABRVariant,
) -> dict[str, Any]:
    """Build DASH video output for a single variant."""
    return {
        "NameModifier": f"_{variant.name}",
        "ContainerSettings": {
            "Container": "MPD",
        },
        "VideoDescription": {
            "Width": variant.width,
            "Height": variant.height,
            "CodecSettings": calculate_qvbr_settings(variant),
            "ScalingBehavior": "DEFAULT",
            "AntiAlias": "ENABLED",
            "Sharpness": 50,
            "TimecodeInsertion": "DISABLED",
        },
    }


def _build_dash_audio_output(
    request: TranscodeJobRequest,
    track: Any,
) -> dict[str, Any]:
    """Build DASH audio output for a language track."""
    return {
        "NameModifier": f"_audio_{track.language.value}",
        "ContainerSettings": {
            "Container": "MPD",
        },
        "AudioDescriptions": [
            {
                "AudioSourceName": f"Audio_{track.language.value}",
                "AudioTypeControl": "FOLLOW_INPUT",
                "LanguageCode": _get_iso_639_2_code(track.language.value),
                "LanguageCodeControl": "USE_CONFIGURED",
                "CodecSettings": get_audio_settings(track.channels),
                "StreamName": track.label,
            }
        ],
    }


def estimate_output_size_gb(
    duration_seconds: float,
    variants: list[ABRVariant],
    audio_tracks: int = 2,
) -> float:
    """Estimate total output size for budgeting.

    Args:
        duration_seconds: Content duration
        variants: ABR variants to encode
        audio_tracks: Number of audio tracks

    Returns:
        Estimated output size in GB
    """
    total_bitrate_kbps = sum(v.bitrate_kbps for v in variants)

    # Add audio (128kbps per track)
    audio_bitrate_kbps = audio_tracks * 128

    # Total bitrate
    combined_kbps = total_bitrate_kbps + audio_bitrate_kbps

    # Calculate size (bitrate * duration / 8 for bytes / 1024^3 for GB)
    size_gb = (combined_kbps * 1000 * duration_seconds) / 8 / (1024**3)

    # Add ~10% for container overhead
    return size_gb * 1.1
