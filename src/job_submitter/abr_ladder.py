"""ABR (Adaptive Bitrate) ladder configuration.

Defines the encoding ladder for streaming output, following industry
best practices from Apple HLS Authoring Spec and Netflix recommendations.

Key concepts:
- QVBR (Quality-Defined Variable Bitrate) for optimal quality/size ratio
- H.264 for universal compatibility
- H.265/HEVC for ~25% bandwidth savings on modern devices
"""

from ..shared.models import ABRVariant, VideoCodec


# =============================================================================
# H.264 (AVC) Ladder - Universal Compatibility
# =============================================================================

ABR_LADDER_H264: list[ABRVariant] = [
    # 1080p Full HD - Desktop/TV
    ABRVariant(
        resolution="1920x1080",
        bitrate_kbps=6000,
        codec=VideoCodec.H264,
        profile="high",
        level="4.2",
    ),
    # 720p HD - Tablet/Good Mobile
    ABRVariant(
        resolution="1280x720",
        bitrate_kbps=3500,
        codec=VideoCodec.H264,
        profile="high",
        level="4.0",
    ),
    # 480p SD - Mobile/Poor Connection
    ABRVariant(
        resolution="854x480",
        bitrate_kbps=1800,
        codec=VideoCodec.H264,
        profile="main",
        level="3.1",
    ),
    # 360p Low - Very Poor Connection
    ABRVariant(
        resolution="640x360",
        bitrate_kbps=800,
        codec=VideoCodec.H264,
        profile="main",
        level="3.0",
    ),
]


# =============================================================================
# H.265 (HEVC) Ladder - Modern Devices (~25% bandwidth savings)
# =============================================================================

ABR_LADDER_H265: list[ABRVariant] = [
    # 1080p HEVC - Modern devices with hardware decode
    ABRVariant(
        resolution="1920x1080",
        bitrate_kbps=4500,  # ~25% less than H.264
        codec=VideoCodec.H265,
        profile="main",
        level="4.0",
    ),
    # 720p HEVC
    ABRVariant(
        resolution="1280x720",
        bitrate_kbps=2500,
        codec=VideoCodec.H265,
        profile="main",
        level="4.0",
    ),
]


def get_abr_ladder(
    source_width: int,
    source_height: int,
    enable_h265: bool = True,
) -> list[ABRVariant]:
    """Build appropriate ABR ladder based on source resolution.

    Only includes variants at or below source resolution to prevent
    upscaling, which wastes bandwidth without quality improvement.

    Args:
        source_width: Source video width in pixels
        source_height: Source video height in pixels
        enable_h265: Whether to include H.265/HEVC variants

    Returns:
        List of ABR variants, sorted by resolution (descending) then codec

    Example:
        >>> variants = get_abr_ladder(1920, 1080, enable_h265=True)
        >>> for v in variants:
        ...     print(f"{v.codec.value} {v.resolution} @ {v.bitrate_kbps}kbps")
        h264 1920x1080 @ 6000kbps
        h265 1920x1080 @ 4500kbps
        h264 1280x720 @ 3500kbps
        h265 1280x720 @ 2500kbps
        h264 854x480 @ 1800kbps
        h264 640x360 @ 800kbps
    """
    variants: list[ABRVariant] = []

    # Filter H.264 variants based on source resolution
    for variant in ABR_LADDER_H264:
        if variant.height <= source_height:
            variants.append(variant)

    # Add H.265 variants if enabled
    if enable_h265:
        for variant in ABR_LADDER_H265:
            if variant.height <= source_height:
                variants.append(variant)

    # Sort by resolution (descending), then codec (h264 before h265)
    variants.sort(
        key=lambda v: (-v.height, v.codec.value),
    )

    return variants


def calculate_qvbr_settings(variant: ABRVariant) -> dict:
    """Calculate QVBR (Quality-Defined Variable Bitrate) codec settings.

    QVBR provides optimal quality-to-file-size ratio by targeting a quality
    level instead of a fixed bitrate. MediaConvert adjusts the bitrate
    dynamically based on content complexity.

    Quality levels:
    - 1-4: Low quality, small files
    - 5-6: Good quality, reasonable size
    - 7-8: High quality (recommended for streaming)
    - 9-10: Near-lossless

    Args:
        variant: ABR variant configuration

    Returns:
        MediaConvert codec settings dictionary
    """
    # Quality level 7 is recommended for streaming
    # Provides good quality without excessive bitrate
    quality_level = 7

    # Set max bitrate to 1.5x the target for VBR headroom
    max_bitrate = int(variant.bitrate_kbps * 1.5 * 1000)

    if variant.codec == VideoCodec.H264:
        return {
            "Codec": "H_264",
            "H264Settings": {
                "RateControlMode": "QVBR",
                "QvbrSettings": {
                    "QvbrQualityLevel": quality_level,
                    "MaxAverageBitrate": variant.bitrate_kbps * 1000,
                },
                "MaxBitrate": max_bitrate,  # Required with MULTI_PASS_HQ
                "QualityTuningLevel": "MULTI_PASS_HQ",  # Required for MaxAverageBitrate
                "CodecProfile": _format_h264_profile(variant.profile),
                "CodecLevel": "AUTO",  # Let MediaConvert pick appropriate level
                "GopSize": 48,  # ~2 seconds at 24fps
                "GopSizeUnits": "FRAMES",
                "NumberBFramesBetweenReferenceFrames": 2,
                "GopBReference": "ENABLED",  # Allow B-frames to reference other B-frames
                "AdaptiveQuantization": "HIGH",
                "SceneChangeDetect": "ENABLED",
                "EntropyEncoding": "CABAC",
                "Syntax": "DEFAULT",
                "Slices": 1,
                "InterlaceMode": "PROGRESSIVE",
            },
        }

    elif variant.codec == VideoCodec.H265:
        return {
            "Codec": "H_265",
            "H265Settings": {
                "RateControlMode": "QVBR",
                "QvbrSettings": {
                    "QvbrQualityLevel": quality_level,
                    "MaxAverageBitrate": variant.bitrate_kbps * 1000,
                },
                "MaxBitrate": max_bitrate,  # Required with MULTI_PASS_HQ
                "QualityTuningLevel": "MULTI_PASS_HQ",  # Required for MaxAverageBitrate
                "CodecProfile": _format_h265_profile(variant.profile),
                "CodecLevel": "AUTO",  # Let MediaConvert pick appropriate level
                "GopSize": 48,
                "GopSizeUnits": "FRAMES",
                "NumberBFramesBetweenReferenceFrames": 2,
                "GopBReference": "ENABLED",
                "AdaptiveQuantization": "HIGH",
                "SceneChangeDetect": "ENABLED",
                "Tiles": "ENABLED",
                "InterlaceMode": "PROGRESSIVE",
                "WriteMp4PackagingType": "HVC1",
            },
        }

    raise ValueError(f"Unsupported codec: {variant.codec}")


def _format_h264_profile(profile: str) -> str:
    """Format H.264 profile for MediaConvert API."""
    profile_map = {
        "baseline": "BASELINE",
        "main": "MAIN",
        "high": "HIGH",
        "high_10": "HIGH_10BIT",
        "high_422": "HIGH_422",
        "high_444": "HIGH_444_PREDICTIVE",
    }
    return profile_map.get(profile.lower(), "HIGH")


def _format_h265_profile(profile: str) -> str:
    """Format H.265 profile for MediaConvert API."""
    profile_map = {
        "main": "MAIN_MAIN",
        "main10": "MAIN10_MAIN",
        "main_10": "MAIN10_MAIN",
    }
    return profile_map.get(profile.lower(), "MAIN_MAIN")


def _format_codec_level(level: str) -> str:
    """Format codec level for MediaConvert API.

    Converts '4.0' to 'LEVEL_4' format, '4.1' to 'LEVEL_4_1'.
    MediaConvert uses format: LEVEL_4, LEVEL_4_1, LEVEL_4_2, etc.
    Note: 'x.0' levels become 'LEVEL_x', not 'LEVEL_x_0'.
    """
    # Split on decimal: "4.0" -> ["4", "0"], "4.2" -> ["4", "2"]
    parts = level.split(".")
    if len(parts) == 2 and parts[1] == "0":
        # 4.0 -> LEVEL_4 (not LEVEL_4_0)
        return f"LEVEL_{parts[0]}"
    else:
        # 4.1 -> LEVEL_4_1, 4.2 -> LEVEL_4_2
        level_clean = level.replace(".", "_")
        return f"LEVEL_{level_clean}"


def get_audio_settings(channels: int = 2, bitrate_kbps: int = 128) -> dict:
    """Get standard AAC audio encoding settings.

    Args:
        channels: Number of audio channels (2=stereo, 6=5.1)
        bitrate_kbps: Audio bitrate in kbps

    Returns:
        MediaConvert audio codec settings
    """
    coding_mode = "CODING_MODE_2_0" if channels <= 2 else "CODING_MODE_5_1"

    return {
        "Codec": "AAC",
        "AacSettings": {
            "AudioDescriptionBroadcasterMix": "NORMAL",
            "Bitrate": bitrate_kbps * 1000,
            "RateControlMode": "CBR",
            "CodecProfile": "LC",
            "CodingMode": coding_mode,
            "RawFormat": "NONE",
            "SampleRate": 48000,
            "Specification": "MPEG4",
        },
    }
