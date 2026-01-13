"""Custom exception hierarchy for the transcoding pipeline.

All pipeline-specific exceptions inherit from TranscodingPipelineError,
enabling consistent error handling and structured error responses.

Exception hierarchy:
    TranscodingPipelineError (base)
    ├── ManifestValidationError
    ├── MezzanineValidationError
    │   └── ChecksumMismatchError
    ├── JobSubmissionError
    └── OutputValidationError
        └── DurationMismatchError
"""

from typing import Any


class TranscodingPipelineError(Exception):
    """Base exception for all pipeline errors.

    Provides structured error information suitable for logging,
    CloudWatch metrics, and SNS notifications.

    Attributes:
        message: Human-readable error description
        error_code: Machine-readable error code for metrics/filtering
        details: Additional context as key-value pairs
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize pipeline error.

        Args:
            message: Human-readable error description
            error_code: Machine-readable error code (e.g., 'MANIFEST_PARSE_ERROR')
            details: Additional context for debugging
        """
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for JSON serialization.

        Returns:
            Dictionary with error_code, error_message, and details.
            Note: Uses 'error_message' instead of 'message' to avoid conflicts
            with Python's logging module which reserves 'message' internally.
        """
        return {
            "error_code": self.error_code,
            "error_message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.error_code!r}, {self.message!r})"


class ManifestValidationError(TranscodingPipelineError):
    """Raised when XML manifest validation fails.

    This covers:
    - Malformed XML syntax
    - Missing required elements
    - Invalid element values
    - Schema validation failures
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "MANIFEST_VALIDATION_ERROR", details)


class MezzanineValidationError(TranscodingPipelineError):
    """Raised when mezzanine file validation fails.

    This covers:
    - File not found
    - Unsupported codec
    - Resolution out of bounds
    - Corrupt container
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "MEZZANINE_VALIDATION_ERROR", details)


class ChecksumMismatchError(MezzanineValidationError):
    """Raised when file checksum doesn't match expected value.

    This indicates file corruption during transfer or storage.
    """

    def __init__(self, expected: str, actual: str, file_path: str) -> None:
        """Initialize checksum mismatch error.

        Args:
            expected: Expected checksum value from manifest
            actual: Actual computed checksum
            file_path: Path to the file that failed verification
        """
        details = {
            "expected_checksum": expected,
            "actual_checksum": actual,
            "file_path": file_path,
        }
        message = f"Checksum mismatch for {file_path}: expected {expected[:8]}..., got {actual[:8]}..."
        super().__init__(message, details)
        # Override error code for more specific metrics
        self.error_code = "CHECKSUM_MISMATCH_ERROR"


class JobSubmissionError(TranscodingPipelineError):
    """Raised when MediaConvert job submission fails.

    This covers:
    - API errors from MediaConvert
    - Invalid job settings
    - Queue issues
    - IAM permission errors
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "JOB_SUBMISSION_ERROR", details)


class OutputValidationError(TranscodingPipelineError):
    """Raised when output validation fails.

    This covers:
    - Missing output files
    - Invalid HLS playlist structure
    - Invalid DASH MPD structure
    - Segment count mismatch
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "OUTPUT_VALIDATION_ERROR", details)


class DurationMismatchError(OutputValidationError):
    """Raised when output duration doesn't match input within tolerance.

    This may indicate:
    - Dropped frames during transcoding
    - Audio/video sync issues
    - Truncated output
    """

    def __init__(
        self,
        input_duration: float,
        output_duration: float,
        tolerance: float,
    ) -> None:
        """Initialize duration mismatch error.

        Args:
            input_duration: Expected duration from input mezzanine (seconds)
            output_duration: Actual duration of transcoded output (seconds)
            tolerance: Configured tolerance threshold (seconds)
        """
        difference = abs(input_duration - output_duration)
        details = {
            "input_duration_seconds": input_duration,
            "output_duration_seconds": output_duration,
            "difference_seconds": difference,
            "tolerance_seconds": tolerance,
        }
        message = (
            f"Duration mismatch: input={input_duration:.2f}s, "
            f"output={output_duration:.2f}s (diff={difference:.2f}s > tolerance={tolerance}s)"
        )
        super().__init__(message, details)
        # Override error code for more specific metrics
        self.error_code = "DURATION_MISMATCH_ERROR"


class IdempotencyError(TranscodingPipelineError):
    """Raised when idempotency check fails.

    This covers:
    - DynamoDB access errors
    - Concurrent job submission conflicts
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, "IDEMPOTENCY_ERROR", details)


class RetryableError(TranscodingPipelineError):
    """Raised for transient errors that should be retried.

    Step Functions can use this to determine retry behavior.
    """

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize retryable error.

        Args:
            message: Error description
            original_error: The underlying exception that triggered this
            details: Additional context
        """
        error_details = details or {}
        if original_error:
            error_details["original_error"] = str(original_error)
            error_details["original_error_type"] = type(original_error).__name__

        super().__init__(message, "RETRYABLE_ERROR", error_details)
        self.original_error = original_error
