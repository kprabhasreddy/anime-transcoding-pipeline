"""AWS client wrappers with retry logic and mock support.

This module provides centralized AWS client management with:
- Automatic retry for transient errors
- Mock mode support for local development
- Consistent configuration across all Lambdas
"""

import random
import time
from functools import lru_cache
from typing import Any, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import get_settings
from .exceptions import RetryableError

# AWS service configuration with retry
AWS_CONFIG = Config(
    retries={
        "max_attempts": 3,
        "mode": "adaptive",
    },
    connect_timeout=5,
    read_timeout=30,
)

# Error codes that indicate transient failures
RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ProvisionedThroughputExceededException",
    "ServiceUnavailable",
    "RequestLimitExceeded",
    "InternalError",
    "Throttling",
}


@lru_cache(maxsize=1)
def get_s3_client() -> Any:
    """Get cached S3 client.

    Returns:
        boto3 S3 client configured for the current environment
    """
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=AWS_CONFIG,
    )


@lru_cache(maxsize=1)
def get_mediaconvert_client() -> Any:
    """Get cached MediaConvert client.

    MediaConvert requires a custom endpoint URL which varies by account.

    Returns:
        boto3 MediaConvert client with account-specific endpoint
    """
    settings = get_settings()

    if settings.mock_mode:
        # Return standard client for moto mocking
        return boto3.client(
            "mediaconvert",
            region_name=settings.aws_region,
            config=AWS_CONFIG,
        )

    return boto3.client(
        "mediaconvert",
        region_name=settings.aws_region,
        endpoint_url=settings.mediaconvert_endpoint,
        config=AWS_CONFIG,
    )


@lru_cache(maxsize=1)
def get_dynamodb_client() -> Any:
    """Get cached DynamoDB client.

    Returns:
        boto3 DynamoDB client for idempotency table access
    """
    settings = get_settings()
    return boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        config=AWS_CONFIG,
    )


@lru_cache(maxsize=1)
def get_dynamodb_resource() -> Any:
    """Get cached DynamoDB resource (higher-level API).

    Returns:
        boto3 DynamoDB resource
    """
    settings = get_settings()
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
    )


@lru_cache(maxsize=1)
def get_sns_client() -> Any:
    """Get cached SNS client.

    Returns:
        boto3 SNS client for notifications
    """
    settings = get_settings()
    return boto3.client(
        "sns",
        region_name=settings.aws_region,
        config=AWS_CONFIG,
    )


@lru_cache(maxsize=1)
def get_stepfunctions_client() -> Any:
    """Get cached Step Functions client.

    Returns:
        boto3 Step Functions client
    """
    settings = get_settings()
    return boto3.client(
        "stepfunctions",
        region_name=settings.aws_region,
        config=AWS_CONFIG,
    )


@lru_cache(maxsize=1)
def get_cloudwatch_client() -> Any:
    """Get cached CloudWatch client.

    Returns:
        boto3 CloudWatch client for metrics
    """
    settings = get_settings()
    return boto3.client(
        "cloudwatch",
        region_name=settings.aws_region,
        config=AWS_CONFIG,
    )


def is_retryable_error(error: ClientError) -> bool:
    """Check if an AWS error is retryable.

    Args:
        error: boto3 ClientError exception

    Returns:
        True if the error indicates a transient failure
    """
    error_code = error.response.get("Error", {}).get("Code", "")
    return error_code in RETRYABLE_ERROR_CODES


def retry_with_backoff(
    func: Callable[..., Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Any:
    """Execute a function with exponential backoff retry.

    Args:
        func: Callable to execute
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)

    Returns:
        Result of successful function execution

    Raises:
        RetryableError: If all retries are exhausted
        ClientError: For non-retryable AWS errors
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except ClientError as e:
            if not is_retryable_error(e):
                raise

            last_error = e

            if attempt < max_retries:
                # Calculate delay with exponential backoff and jitter
                delay = min(base_delay * (2**attempt), max_delay)
                # Add jitter (±25%)
                delay *= 0.75 + random.random() * 0.5
                time.sleep(delay)

    raise RetryableError(
        f"Operation failed after {max_retries + 1} attempts",
        original_error=last_error,
    )


def clear_client_cache() -> None:
    """Clear all cached AWS clients.

    Useful for testing when mocking needs to be reset.
    """
    get_s3_client.cache_clear()
    get_mediaconvert_client.cache_clear()
    get_dynamodb_client.cache_clear()
    get_dynamodb_resource.cache_clear()
    get_sns_client.cache_clear()
    get_stepfunctions_client.cache_clear()
    get_cloudwatch_client.cache_clear()
