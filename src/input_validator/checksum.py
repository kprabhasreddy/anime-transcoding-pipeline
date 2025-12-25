"""Checksum calculation and verification utilities.

Supports:
- MD5 (industry standard for video workflows)
- XXHash64 (faster alternative for large files)

Streaming calculation for memory-efficient processing of large mezzanine files.
"""

import hashlib
from typing import BinaryIO

import xxhash

from ..shared.config import get_settings
from ..shared.exceptions import ChecksumMismatchError


def calculate_md5(
    file_obj: BinaryIO,
    chunk_size: int | None = None,
) -> str:
    """Calculate MD5 checksum of a file using streaming.

    Args:
        file_obj: File-like object to read from
        chunk_size: Bytes to read per chunk (default from settings)

    Returns:
        Lowercase hexadecimal MD5 hash string (32 characters)

    Example:
        >>> with open("video.mxf", "rb") as f:
        ...     checksum = calculate_md5(f)
        >>> print(checksum)
        'd41d8cd98f00b204e9800998ecf8427e'
    """
    if chunk_size is None:
        settings = get_settings()
        chunk_size = settings.checksum_chunk_size_bytes

    hasher = hashlib.md5()

    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)

    return hasher.hexdigest().lower()


def calculate_xxhash(
    file_obj: BinaryIO,
    chunk_size: int | None = None,
) -> str:
    """Calculate XXHash64 checksum of a file using streaming.

    XXHash is significantly faster than MD5 for large files while
    maintaining good collision resistance.

    Args:
        file_obj: File-like object to read from
        chunk_size: Bytes to read per chunk (default from settings)

    Returns:
        Lowercase hexadecimal XXHash64 string (16 characters)

    Example:
        >>> with open("video.mxf", "rb") as f:
        ...     checksum = calculate_xxhash(f)
        >>> print(checksum)
        'a2b9c3d4e5f67890'
    """
    if chunk_size is None:
        settings = get_settings()
        chunk_size = settings.checksum_chunk_size_bytes

    hasher = xxhash.xxh64()

    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)

    return hasher.hexdigest().lower()


def verify_checksum(
    file_obj: BinaryIO,
    expected_md5: str,
    expected_xxhash: str | None = None,
    file_path: str = "unknown",
) -> bool:
    """Verify file checksum against expected values.

    If XXHash is provided, it's verified first (faster).
    MD5 is always verified as the authoritative checksum.

    Args:
        file_obj: File-like object to read from
        expected_md5: Expected MD5 hash (32 hex characters)
        expected_xxhash: Expected XXHash64 (16 hex characters, optional)
        file_path: File path for error messages

    Returns:
        True if checksum matches

    Raises:
        ChecksumMismatchError: If checksum doesn't match
    """
    settings = get_settings()
    chunk_size = settings.checksum_chunk_size_bytes

    # Initialize hashers
    md5_hasher = hashlib.md5()
    xxhash_hasher = xxhash.xxh64() if expected_xxhash else None

    # Single-pass calculation of both checksums
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        md5_hasher.update(chunk)
        if xxhash_hasher:
            xxhash_hasher.update(chunk)

    # Verify XXHash first (if provided) - faster feedback
    if xxhash_hasher and expected_xxhash:
        actual_xxhash = xxhash_hasher.hexdigest().lower()
        if actual_xxhash != expected_xxhash.lower():
            raise ChecksumMismatchError(
                expected=expected_xxhash,
                actual=actual_xxhash,
                file_path=file_path,
            )

    # Verify MD5 (authoritative)
    actual_md5 = md5_hasher.hexdigest().lower()
    if actual_md5 != expected_md5.lower():
        raise ChecksumMismatchError(
            expected=expected_md5,
            actual=actual_md5,
            file_path=file_path,
        )

    return True


def calculate_checksums(
    file_obj: BinaryIO,
    chunk_size: int | None = None,
) -> dict[str, str]:
    """Calculate both MD5 and XXHash64 in a single pass.

    More efficient than calling calculate_md5 and calculate_xxhash separately.

    Args:
        file_obj: File-like object to read from
        chunk_size: Bytes to read per chunk

    Returns:
        Dictionary with 'md5' and 'xxhash64' keys

    Example:
        >>> with open("video.mxf", "rb") as f:
        ...     checksums = calculate_checksums(f)
        >>> print(checksums)
        {'md5': 'd41d8cd...', 'xxhash64': 'a2b9c3d4...'}
    """
    if chunk_size is None:
        settings = get_settings()
        chunk_size = settings.checksum_chunk_size_bytes

    md5_hasher = hashlib.md5()
    xxhash_hasher = xxhash.xxh64()

    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        md5_hasher.update(chunk)
        xxhash_hasher.update(chunk)

    return {
        "md5": md5_hasher.hexdigest().lower(),
        "xxhash64": xxhash_hasher.hexdigest().lower(),
    }
