"""Environment-aware configuration with validation.

This module provides centralized configuration management using Pydantic Settings.
All environment variables are validated at startup to fail fast on misconfigurations.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All required settings must be provided via environment variables.
    Settings are cached to avoid repeated parsing.

    Example:
        >>> settings = get_settings()
        >>> print(settings.input_bucket)
        'anime-transcode-input-dev'
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["dev", "staging", "prod"] = Field(
        default="dev",
        description="Deployment environment",
    )
    aws_region: str = Field(
        default="us-east-1",
        alias="AWS_REGION",
        description="AWS region for all services",
    )

    # S3 Configuration
    input_bucket: str = Field(
        default="",
        alias="INPUT_BUCKET",
        description="S3 bucket for mezzanine files and manifests",
    )
    output_bucket: str = Field(
        default="",
        alias="OUTPUT_BUCKET",
        description="S3 bucket for transcoded assets",
    )

    # MediaConvert Configuration (optional - only needed by job_submitter)
    mediaconvert_endpoint: str = Field(
        default="",
        alias="MEDIACONVERT_ENDPOINT",
        description="MediaConvert API endpoint URL",
    )
    mediaconvert_role_arn: str = Field(
        default="",
        alias="MEDIACONVERT_ROLE_ARN",
        description="IAM role ARN for MediaConvert",
    )
    mediaconvert_queue_arn: str = Field(
        default="",
        alias="MEDIACONVERT_QUEUE_ARN",
        description="MediaConvert queue ARN",
    )

    # Step Functions
    step_function_arn: str = Field(
        default="",
        alias="STATE_MACHINE_ARN",
        description="Step Functions state machine ARN",
    )

    # DynamoDB (for idempotency)
    idempotency_table: str = Field(
        default="anime-transcode-idempotency",
        alias="IDEMPOTENCY_TABLE",
        description="DynamoDB table for job idempotency",
    )

    # KMS Configuration
    kms_key_id: str = Field(
        default="",
        alias="KMS_KEY_ID",
        description="KMS key ID for encryption",
    )

    # SNS Topics
    sns_success_topic_arn: str = Field(
        default="",
        alias="SNS_SUCCESS_TOPIC_ARN",
        description="SNS topic for success notifications",
    )
    sns_error_topic_arn: str = Field(
        default="",
        alias="SNS_ERROR_TOPIC_ARN",
        description="SNS topic for error notifications",
    )

    # Webhook Configuration
    webhook_secret: str = Field(
        default="",
        alias="WEBHOOK_SECRET",
        description="Secret for HMAC-SHA256 webhook signature verification",
    )

    # Feature Flags
    mock_mode: bool = Field(
        default=True,
        alias="MOCK_MODE",
        description="Enable mock mode for local development (no real AWS calls)",
    )
    enable_h265: bool = Field(
        default=True,
        alias="ENABLE_H265",
        description="Include H.265/HEVC variants in ABR ladder",
    )
    enable_dash: bool = Field(
        default=True,
        alias="ENABLE_DASH",
        description="Generate DASH output in addition to HLS",
    )

    # Validation Thresholds
    duration_tolerance_seconds: float = Field(
        default=0.5,
        ge=0.0,
        le=5.0,
        description="Allowed duration mismatch between input and output",
    )
    max_mezzanine_size_gb: float = Field(
        default=50.0,
        ge=1.0,
        le=500.0,
        description="Maximum allowed mezzanine file size in GB",
    )
    checksum_chunk_size_mb: int = Field(
        default=64,
        ge=1,
        le=256,
        description="Chunk size for streaming checksum calculation",
    )

    # Retry Configuration
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for transient failures",
    )
    retry_delay_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=30.0,
        description="Initial delay between retries (exponential backoff)",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Logging level",
    )

    @field_validator("mediaconvert_endpoint", mode="before")
    @classmethod
    def validate_mediaconvert_endpoint(cls, v: str) -> str:
        """Ensure MediaConvert endpoint is a valid URL."""
        if v and not v.startswith("https://"):
            raise ValueError("MediaConvert endpoint must start with https://")
        return v

    @field_validator("mediaconvert_role_arn", "mediaconvert_queue_arn", mode="before")
    @classmethod
    def validate_arn_format(cls, v: str) -> str:
        """Validate ARN format."""
        if v and not v.startswith("arn:aws:"):
            raise ValueError("Invalid ARN format - must start with 'arn:aws:'")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "prod"

    @property
    def checksum_chunk_size_bytes(self) -> int:
        """Get chunk size in bytes."""
        return self.checksum_chunk_size_mb * 1024 * 1024

    @property
    def max_mezzanine_size_bytes(self) -> int:
        """Get max mezzanine size in bytes."""
        return int(self.max_mezzanine_size_gb * 1024 * 1024 * 1024)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are loaded once and cached for the lifetime of the process.
    This is safe for Lambda because each invocation gets a fresh process
    or reuses a warm container with the same settings.

    Returns:
        Validated Settings instance

    Raises:
        ValidationError: If required environment variables are missing or invalid
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache.

    Useful for testing when environment variables change.
    """
    get_settings.cache_clear()
