"""Media info extraction using FFprobe.

Provides container and codec analysis for mezzanine files.
Used for pre-transcode validation to catch issues early.
"""

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from ..shared.exceptions import MezzanineValidationError


@dataclass
class VideoStream:
    """Video stream information."""

    codec_name: str
    codec_long_name: str
    width: int
    height: int
    frame_rate: float
    duration_seconds: float
    bit_rate: int | None
    pix_fmt: str | None
    color_space: str | None
    bit_depth: int | None

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def is_hd(self) -> bool:
        return self.height >= 720

    @property
    def is_4k(self) -> bool:
        return self.height >= 2160


@dataclass
class AudioStream:
    """Audio stream information."""

    codec_name: str
    codec_long_name: str
    channels: int
    sample_rate: int
    bit_rate: int | None
    language: str | None

    @property
    def channel_layout(self) -> str:
        if self.channels == 1:
            return "mono"
        elif self.channels == 2:
            return "stereo"
        elif self.channels == 6:
            return "5.1"
        elif self.channels == 8:
            return "7.1"
        return f"{self.channels}ch"


@dataclass
class MediaInfo:
    """Complete media file information."""

    format_name: str
    format_long_name: str
    duration_seconds: float
    size_bytes: int
    bit_rate: int
    video_streams: list[VideoStream]
    audio_streams: list[AudioStream]
    subtitle_streams: int

    @property
    def primary_video(self) -> VideoStream | None:
        """Get the first video stream."""
        return self.video_streams[0] if self.video_streams else None

    @property
    def audio_languages(self) -> list[str]:
        """Get list of audio track languages."""
        return [s.language for s in self.audio_streams if s.language]


def extract_media_info(file_path: str) -> MediaInfo:
    """Extract media information using FFprobe.

    Args:
        file_path: Path to media file (local or S3 URI for Lambda)

    Returns:
        MediaInfo object with all stream details

    Raises:
        MezzanineValidationError: If FFprobe fails or file is invalid

    Example:
        >>> info = extract_media_info("/path/to/video.mxf")
        >>> print(f"Duration: {info.duration_seconds}s")
        >>> print(f"Resolution: {info.primary_video.resolution}")
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise MezzanineValidationError(
                f"FFprobe failed: {result.stderr}",
                {"file_path": file_path, "stderr": result.stderr},
            )

        data = json.loads(result.stdout)
        return _parse_ffprobe_output(data, file_path)

    except subprocess.TimeoutExpired:
        raise MezzanineValidationError(
            "FFprobe timed out",
            {"file_path": file_path, "timeout_seconds": 60},
        )
    except FileNotFoundError:
        raise MezzanineValidationError(
            "FFprobe not found - ensure FFmpeg is installed",
            {"file_path": file_path},
        )
    except json.JSONDecodeError as e:
        raise MezzanineValidationError(
            f"Invalid FFprobe output: {e}",
            {"file_path": file_path},
        )


def _parse_ffprobe_output(data: dict[str, Any], file_path: str) -> MediaInfo:
    """Parse FFprobe JSON output into MediaInfo object."""
    if "format" not in data:
        raise MezzanineValidationError(
            "No format information in FFprobe output",
            {"file_path": file_path},
        )

    fmt = data["format"]
    streams = data.get("streams", [])

    video_streams = []
    audio_streams = []
    subtitle_count = 0

    for stream in streams:
        codec_type = stream.get("codec_type")

        if codec_type == "video":
            video_streams.append(_parse_video_stream(stream))
        elif codec_type == "audio":
            audio_streams.append(_parse_audio_stream(stream))
        elif codec_type == "subtitle":
            subtitle_count += 1

    if not video_streams:
        raise MezzanineValidationError(
            "No video stream found in file",
            {"file_path": file_path},
        )

    return MediaInfo(
        format_name=fmt.get("format_name", "unknown"),
        format_long_name=fmt.get("format_long_name", "unknown"),
        duration_seconds=float(fmt.get("duration", 0)),
        size_bytes=int(fmt.get("size", 0)),
        bit_rate=int(fmt.get("bit_rate", 0)),
        video_streams=video_streams,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_count,
    )


def _parse_video_stream(stream: dict[str, Any]) -> VideoStream:
    """Parse video stream data."""
    # Parse frame rate from ratio (e.g., "24000/1001")
    frame_rate = _parse_frame_rate(stream.get("r_frame_rate", "0/1"))

    # Parse bit depth from pix_fmt if available
    bit_depth = None
    pix_fmt = stream.get("pix_fmt", "")
    if "10" in pix_fmt or "10le" in pix_fmt or "10be" in pix_fmt:
        bit_depth = 10
    elif "12" in pix_fmt:
        bit_depth = 12
    elif pix_fmt:
        bit_depth = 8

    return VideoStream(
        codec_name=stream.get("codec_name", "unknown"),
        codec_long_name=stream.get("codec_long_name", "unknown"),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        frame_rate=frame_rate,
        duration_seconds=float(stream.get("duration", 0)),
        bit_rate=_parse_int(stream.get("bit_rate")),
        pix_fmt=pix_fmt or None,
        color_space=stream.get("color_space"),
        bit_depth=bit_depth,
    )


def _parse_audio_stream(stream: dict[str, Any]) -> AudioStream:
    """Parse audio stream data."""
    # Get language from tags
    tags = stream.get("tags", {})
    language = tags.get("language")

    return AudioStream(
        codec_name=stream.get("codec_name", "unknown"),
        codec_long_name=stream.get("codec_long_name", "unknown"),
        channels=int(stream.get("channels", 0)),
        sample_rate=int(stream.get("sample_rate", 0)),
        bit_rate=_parse_int(stream.get("bit_rate")),
        language=language,
    )


def _parse_frame_rate(rate_str: str) -> float:
    """Parse frame rate from ratio string (e.g., '24000/1001')."""
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            return float(num) / float(den)
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _parse_int(value: Any) -> int | None:
    """Safely parse integer value."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def validate_media_info(
    info: MediaInfo,
    expected_duration: float,
    expected_width: int,
    expected_height: int,
    duration_tolerance: float = 0.5,
) -> list[str]:
    """Validate media info against expected values.

    Args:
        info: MediaInfo from FFprobe
        expected_duration: Expected duration in seconds
        expected_width: Expected video width
        expected_height: Expected video height
        duration_tolerance: Allowed duration difference in seconds

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    video = info.primary_video
    if not video:
        errors.append("No video stream found")
        return errors

    # Check duration
    duration_diff = abs(info.duration_seconds - expected_duration)
    if duration_diff > duration_tolerance:
        errors.append(
            f"Duration mismatch: expected {expected_duration}s, "
            f"got {info.duration_seconds}s (diff: {duration_diff:.2f}s)"
        )

    # Check resolution
    if video.width != expected_width or video.height != expected_height:
        errors.append(
            f"Resolution mismatch: expected {expected_width}x{expected_height}, "
            f"got {video.resolution}"
        )

    return errors
