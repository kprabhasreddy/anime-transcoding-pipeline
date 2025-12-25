"""Pydantic models for data validation and serialization.

This module defines the core data structures used throughout the pipeline:
- Manifest models (episode metadata, mezzanine info, tracks)
- ABR ladder configuration
- Job request/response models

All models use Pydantic v2 for validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AudioLanguage(str, Enum):
    """Supported audio languages (ISO 639-1 codes)."""

    JAPANESE = "ja"
    ENGLISH = "en"
    SPANISH = "es"
    PORTUGUESE = "pt"
    FRENCH = "fr"
    GERMAN = "de"
    KOREAN = "ko"
    CHINESE = "zh"
    ITALIAN = "it"
    RUSSIAN = "ru"


class SubtitleLanguage(str, Enum):
    """Supported subtitle languages with regional variants."""

    ENGLISH = "en"
    SPANISH_LATAM = "es-419"
    SPANISH_SPAIN = "es-ES"
    PORTUGUESE_BRAZIL = "pt-BR"
    PORTUGUESE_PORTUGAL = "pt-PT"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    ARABIC = "ar"
    RUSSIAN = "ru"
    CHINESE_SIMPLIFIED = "zh-Hans"
    CHINESE_TRADITIONAL = "zh-Hant"
    KOREAN = "ko"


class ContentRating(str, Enum):
    """TV content ratings (US standard)."""

    TV_Y = "TV-Y"
    TV_Y7 = "TV-Y7"
    TV_G = "TV-G"
    TV_PG = "TV-PG"
    TV_14 = "TV-14"
    TV_MA = "TV-MA"


class VideoCodec(str, Enum):
    """Supported output video codecs."""

    H264 = "h264"
    H265 = "h265"


class SubtitleFormat(str, Enum):
    """Supported subtitle formats."""

    WEBVTT = "WebVTT"
    SRT = "SRT"
    TTML = "TTML"


class AudioTrack(BaseModel):
    """Represents an audio track in the manifest.

    Each audio track corresponds to a language version of the audio,
    such as Japanese original or English dub.
    """

    model_config = ConfigDict(frozen=True)

    language: AudioLanguage = Field(
        description="ISO 639-1 language code",
    )
    label: str = Field(
        min_length=1,
        max_length=100,
        description="Display label (e.g., 'Japanese', 'English (Funimation Dub)')",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the default track",
    )
    channels: Annotated[int, Field(ge=1, le=8)] = Field(
        default=2,
        description="Number of audio channels (2=stereo, 6=5.1 surround)",
    )
    track_index: Annotated[int, Field(ge=1)] = Field(
        default=1,
        description="1-based track index in source file",
    )


class SubtitleTrack(BaseModel):
    """Represents a subtitle track in the manifest."""

    model_config = ConfigDict(frozen=True)

    language: SubtitleLanguage = Field(
        description="BCP 47 language tag",
    )
    label: str = Field(
        min_length=1,
        max_length=100,
        description="Display label (e.g., 'English', 'Spanish (Latin America)')",
    )
    file_path: str = Field(
        min_length=1,
        description="S3 path to subtitle file relative to manifest",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the default subtitle track",
    )
    is_forced: bool = Field(
        default=False,
        description="Whether these are forced narrative subtitles",
    )
    format: SubtitleFormat = Field(
        default=SubtitleFormat.WEBVTT,
        description="Subtitle file format",
    )


class EpisodeMetadata(BaseModel):
    """Metadata for a single anime episode.

    This mirrors typical anime streaming service metadata structures.
    """

    model_config = ConfigDict(frozen=True)

    # Series identification
    series_id: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9-]+$",
        description="URL-safe series identifier (e.g., 'attack-on-titan')",
    )
    series_title: str = Field(
        min_length=1,
        max_length=200,
        description="Series display title",
    )
    series_title_ja: str | None = Field(
        default=None,
        max_length=200,
        description="Series title in Japanese (optional)",
    )

    # Episode identification
    season_number: Annotated[int, Field(ge=1, le=100)] = Field(
        description="Season number (1-based)",
    )
    episode_number: Annotated[int, Field(ge=1, le=9999)] = Field(
        description="Episode number within season (1-based)",
    )
    episode_title: str = Field(
        min_length=1,
        max_length=300,
        description="Episode title",
    )
    episode_title_ja: str | None = Field(
        default=None,
        max_length=300,
        description="Episode title in Japanese (optional)",
    )
    episode_description: str | None = Field(
        default=None,
        max_length=2000,
        description="Episode synopsis/description",
    )

    # Timing
    duration_seconds: Annotated[float, Field(gt=0)] = Field(
        description="Episode duration in seconds",
    )

    # Metadata
    release_date: datetime | None = Field(
        default=None,
        description="Original air date",
    )
    content_rating: ContentRating = Field(
        default=ContentRating.TV_14,
        description="TV content rating",
    )

    # Flags
    is_simulcast: bool = Field(
        default=False,
        description="Whether this is a simulcast episode",
    )
    is_dubbed: bool = Field(
        default=False,
        description="Whether a dub track is available",
    )

    @property
    def episode_code(self) -> str:
        """Generate episode code (e.g., 'S01E001')."""
        return f"S{self.season_number:02d}E{self.episode_number:03d}"


class MezzanineInfo(BaseModel):
    """Information about the source mezzanine file.

    The mezzanine is the high-quality master file used as input for transcoding.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(
        min_length=1,
        description="S3 path to mezzanine file relative to input bucket",
    )

    # Integrity verification
    checksum_md5: str = Field(
        pattern=r"^[a-fA-F0-9]{32}$",
        description="MD5 checksum for integrity verification",
    )
    checksum_xxhash: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{16}$",
        description="XXHash64 checksum (faster alternative to MD5)",
    )
    file_size_bytes: Annotated[int, Field(gt=0)] = Field(
        description="File size in bytes",
    )

    # Video properties
    duration_seconds: Annotated[float, Field(gt=0)] = Field(
        description="Video duration in seconds",
    )
    video_codec: str = Field(
        min_length=1,
        max_length=50,
        description="Source video codec (e.g., 'ProRes 422 HQ')",
    )
    audio_codec: str = Field(
        min_length=1,
        max_length=50,
        description="Source audio codec (e.g., 'PCM')",
    )

    # Resolution
    resolution_width: Annotated[int, Field(ge=320, le=7680)] = Field(
        description="Video width in pixels",
    )
    resolution_height: Annotated[int, Field(ge=240, le=4320)] = Field(
        description="Video height in pixels",
    )

    # Encoding
    frame_rate: Annotated[float, Field(gt=0, le=120)] = Field(
        description="Frame rate (e.g., 23.976, 24, 29.97, 60)",
    )
    bitrate_kbps: Annotated[int, Field(gt=0)] = Field(
        description="Average bitrate in kbps",
    )

    # Optional technical metadata
    color_space: str | None = Field(
        default=None,
        description="Color space (e.g., 'BT.709', 'BT.2020')",
    )
    bit_depth: Annotated[int, Field(ge=8, le=16)] | None = Field(
        default=None,
        description="Bit depth (8, 10, or 12)",
    )

    @property
    def resolution(self) -> str:
        """Return resolution string (e.g., '1920x1080')."""
        return f"{self.resolution_width}x{self.resolution_height}"

    @property
    def is_hd(self) -> bool:
        """Check if source is HD (720p or higher)."""
        return self.resolution_height >= 720

    @property
    def is_4k(self) -> bool:
        """Check if source is 4K (2160p or higher)."""
        return self.resolution_height >= 2160


class TranscodeManifest(BaseModel):
    """Complete transcoding manifest combining all metadata.

    This is the primary input to the transcoding pipeline, containing
    all information needed to process an episode.
    """

    model_config = ConfigDict(frozen=True)

    # Manifest metadata
    manifest_version: str = Field(
        default="1.0",
        description="Manifest schema version",
    )
    manifest_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9-_]+$",
        description="Unique identifier for this transcode job",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Manifest creation timestamp",
    )

    # Content
    episode: EpisodeMetadata = Field(
        description="Episode metadata",
    )
    mezzanine: MezzanineInfo = Field(
        description="Source mezzanine file information",
    )

    # Tracks
    audio_tracks: list[AudioTrack] = Field(
        min_length=1,
        description="Audio tracks (at least one required)",
    )
    subtitle_tracks: list[SubtitleTrack] = Field(
        default=[],
        description="Subtitle tracks (optional)",
    )

    # Job configuration
    priority: Annotated[int, Field(ge=0, le=10)] = Field(
        default=0,
        description="Job priority (0=normal, 10=highest)",
    )
    callback_url: str | None = Field(
        default=None,
        description="URL to notify on job completion",
    )

    @field_validator("audio_tracks")
    @classmethod
    def validate_single_default_audio(cls, v: list[AudioTrack]) -> list[AudioTrack]:
        """Ensure exactly one audio track is marked as default."""
        defaults = [t for t in v if t.is_default]
        if len(defaults) != 1:
            raise ValueError("Exactly one audio track must be marked as default")
        return v

    @model_validator(mode="after")
    def validate_durations_match(self) -> "TranscodeManifest":
        """Ensure episode and mezzanine durations are consistent."""
        episode_dur = self.episode.duration_seconds
        mezz_dur = self.mezzanine.duration_seconds

        # Allow small tolerance for floating point precision
        if abs(episode_dur - mezz_dur) > 1.0:
            raise ValueError(
                f"Episode duration ({episode_dur}s) doesn't match "
                f"mezzanine duration ({mezz_dur}s)"
            )
        return self


class ABRVariant(BaseModel):
    """Represents a single variant in the ABR (Adaptive Bitrate) ladder.

    Each variant is a specific resolution/bitrate/codec combination that
    will be generated by MediaConvert.
    """

    model_config = ConfigDict(frozen=True)

    resolution: str = Field(
        pattern=r"^\d+x\d+$",
        description="Resolution string (e.g., '1920x1080')",
    )
    bitrate_kbps: Annotated[int, Field(gt=0, le=50000)] = Field(
        description="Target bitrate in kbps",
    )
    codec: VideoCodec = Field(
        description="Video codec (h264 or h265)",
    )
    profile: str = Field(
        min_length=1,
        max_length=20,
        description="Codec profile (e.g., 'main', 'high')",
    )
    level: str = Field(
        pattern=r"^\d+\.\d+$",
        description="Codec level (e.g., '4.0', '4.2')",
    )

    @property
    def width(self) -> int:
        """Extract width from resolution string."""
        return int(self.resolution.split("x")[0])

    @property
    def height(self) -> int:
        """Extract height from resolution string."""
        return int(self.resolution.split("x")[1])

    @property
    def name(self) -> str:
        """Generate variant name (e.g., 'h264_1080p')."""
        return f"{self.codec.value}_{self.height}p"


class TranscodeJobRequest(BaseModel):
    """Request to create a MediaConvert job."""

    model_config = ConfigDict(frozen=True)

    manifest: TranscodeManifest = Field(
        description="Parsed transcode manifest",
    )
    input_s3_uri: str = Field(
        pattern=r"^s3://[a-z0-9-]+/.+$",
        description="Full S3 URI to mezzanine file",
    )
    output_s3_prefix: str = Field(
        pattern=r"^s3://[a-z0-9-]+/.+$",
        description="S3 prefix for output files",
    )
    abr_variants: list[ABRVariant] = Field(
        min_length=1,
        description="ABR ladder variants to generate",
    )
    output_hls: bool = Field(
        default=True,
        description="Generate HLS output",
    )
    output_dash: bool = Field(
        default=True,
        description="Generate DASH output",
    )
    idempotency_token: str = Field(
        min_length=32,
        max_length=64,
        description="Idempotency token to prevent duplicate jobs",
    )


class TranscodeJobStatus(str, Enum):
    """MediaConvert job status values."""

    SUBMITTED = "SUBMITTED"
    PROGRESSING = "PROGRESSING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"
    CANCELED = "CANCELED"


class TranscodeJobResult(BaseModel):
    """Result of a completed transcode job."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(
        description="MediaConvert job ID",
    )
    manifest_id: str = Field(
        description="Original manifest ID",
    )
    status: TranscodeJobStatus = Field(
        description="Final job status",
    )
    started_at: datetime = Field(
        description="Job start timestamp",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Job completion timestamp",
    )

    # Output locations
    output_hls_uri: str | None = Field(
        default=None,
        description="S3 URI to HLS master playlist",
    )
    output_dash_uri: str | None = Field(
        default=None,
        description="S3 URI to DASH MPD manifest",
    )

    # Validation results
    output_duration_seconds: float | None = Field(
        default=None,
        description="Measured output duration",
    )

    # Error information
    error_message: str | None = Field(
        default=None,
        description="Error message if job failed",
    )
    error_code: str | None = Field(
        default=None,
        description="Error code if job failed",
    )

    @property
    def is_success(self) -> bool:
        """Check if job completed successfully."""
        return self.status == TranscodeJobStatus.COMPLETE

    @property
    def duration_seconds(self) -> float | None:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
