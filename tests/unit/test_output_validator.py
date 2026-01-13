"""Unit tests for output validator module."""

import pytest
from unittest.mock import MagicMock, patch

from src.output_validator.hls_validator import (
    validate_hls_master,
    parse_hls_playlist,
    HLSValidationError,
)
from src.output_validator.dash_validator import (
    validate_dash_manifest,
    parse_mpd,
    DASHValidationError,
)
from src.output_validator.duration_checker import (
    validate_duration,
    extract_hls_duration,
)


class TestHLSValidator:
    """Tests for HLS playlist validation."""

    def test_validate_valid_hls_master(self, sample_hls_master: str):
        """Test validation passes for valid HLS master playlist."""
        result = validate_hls_master(
            content=sample_hls_master,
            expected_variants=[
                {"resolution": "1920x1080", "bitrate_kbps": 6000},
                {"resolution": "1280x720", "bitrate_kbps": 3500},
                {"resolution": "854x480", "bitrate_kbps": 1800},
            ],
        )

        assert result["passed"] is True
        assert len(result["checks"]) > 0

    def test_validate_hls_missing_extm3u(self):
        """Test validation fails without #EXTM3U header."""
        invalid_playlist = """
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=6000000
1080p/playlist.m3u8
        """

        result = validate_hls_master(invalid_playlist, [])

        assert result["passed"] is False
        assert any("EXTM3U" in c.get("message", "") for c in result["checks"])

    def test_validate_hls_missing_variants(self, sample_hls_master: str):
        """Test validation warns when expected variants are missing."""
        result = validate_hls_master(
            content=sample_hls_master,
            expected_variants=[
                {"resolution": "3840x2160", "bitrate_kbps": 15000},  # 4K not present
            ],
        )

        # Should have warning about missing variant
        variant_checks = [c for c in result["checks"] if "variant" in c.get("check", "").lower()]
        assert len(variant_checks) > 0

    def test_parse_hls_playlist_extracts_variants(self, sample_hls_master: str):
        """Test HLS playlist parsing extracts variant information."""
        variants = parse_hls_playlist(sample_hls_master)

        assert len(variants) >= 3
        assert all("bandwidth" in v for v in variants)
        assert all("uri" in v for v in variants)

    def test_parse_hls_playlist_extracts_resolution(self, sample_hls_master: str):
        """Test HLS playlist parsing extracts resolution."""
        variants = parse_hls_playlist(sample_hls_master)

        # At least one variant should have resolution
        resolutions = [v.get("resolution") for v in variants if v.get("resolution")]
        assert len(resolutions) > 0

    def test_validate_hls_empty_playlist(self):
        """Test validation fails for empty playlist."""
        result = validate_hls_master("", [])

        assert result["passed"] is False

    def test_validate_hls_media_playlist(self, sample_hls_media: str):
        """Test validation handles media playlist (not master)."""
        # Media playlists have #EXTINF tags instead of #EXT-X-STREAM-INF
        result = validate_hls_master(sample_hls_media, [])

        # Should indicate this is not a master playlist
        assert any("master" in c.get("message", "").lower() for c in result["checks"])


class TestDASHValidator:
    """Tests for DASH manifest validation."""

    def test_validate_valid_dash_manifest(self, sample_dash_mpd: str):
        """Test validation passes for valid DASH MPD."""
        result = validate_dash_manifest(
            content=sample_dash_mpd,
            expected_variants=[
                {"resolution": "1920x1080", "bitrate_kbps": 6000},
                {"resolution": "1280x720", "bitrate_kbps": 3500},
            ],
        )

        assert result["passed"] is True
        assert len(result["checks"]) > 0

    def test_validate_dash_missing_mpd_element(self):
        """Test validation fails without MPD root element."""
        invalid_mpd = """<?xml version="1.0"?>
        <NotMPD>
            <Content>Invalid</Content>
        </NotMPD>
        """

        result = validate_dash_manifest(invalid_mpd, [])

        assert result["passed"] is False

    def test_validate_dash_invalid_xml(self):
        """Test validation fails for invalid XML."""
        result = validate_dash_manifest("<invalid>", [])

        assert result["passed"] is False
        assert any("xml" in c.get("message", "").lower() for c in result["checks"])

    def test_parse_mpd_extracts_adaptation_sets(self, sample_dash_mpd: str):
        """Test MPD parsing extracts adaptation sets."""
        mpd_data = parse_mpd(sample_dash_mpd)

        assert "adaptation_sets" in mpd_data
        assert len(mpd_data["adaptation_sets"]) > 0

    def test_parse_mpd_extracts_representations(self, sample_dash_mpd: str):
        """Test MPD parsing extracts representations."""
        mpd_data = parse_mpd(sample_dash_mpd)

        # Video adaptation set should have representations
        video_sets = [
            a for a in mpd_data["adaptation_sets"]
            if a.get("content_type") == "video"
        ]

        if video_sets:
            assert "representations" in video_sets[0]
            assert len(video_sets[0]["representations"]) > 0

    def test_validate_dash_checks_duration(self, sample_dash_mpd: str):
        """Test validation checks MPD duration attribute."""
        result = validate_dash_manifest(sample_dash_mpd, [])

        duration_checks = [c for c in result["checks"] if "duration" in c.get("check", "").lower()]
        assert len(duration_checks) > 0


class TestDurationChecker:
    """Tests for duration validation."""

    def test_validate_duration_within_tolerance(self):
        """Test duration validation passes within tolerance."""
        result = validate_duration(
            output_prefix="s3://bucket/output",
            expected_duration=1440.0,
            actual_duration=1440.3,  # 0.3 second difference
            tolerance_seconds=0.5,
        )

        assert result["passed"] is True

    def test_validate_duration_exceeds_tolerance(self):
        """Test duration validation fails when exceeding tolerance."""
        result = validate_duration(
            output_prefix="s3://bucket/output",
            expected_duration=1440.0,
            actual_duration=1442.0,  # 2 second difference
            tolerance_seconds=0.5,
        )

        assert result["passed"] is False
        assert "mismatch" in result["checks"][0].get("message", "").lower()

    def test_validate_duration_exact_match(self):
        """Test duration validation passes for exact match."""
        result = validate_duration(
            output_prefix="s3://bucket/output",
            expected_duration=1440.0,
            actual_duration=1440.0,
        )

        assert result["passed"] is True

    def test_extract_hls_duration(self, sample_hls_media: str):
        """Test extracting duration from HLS media playlist."""
        duration = extract_hls_duration(sample_hls_media)

        # Duration should be calculated from segment lengths
        assert duration > 0

    def test_extract_hls_duration_empty_playlist(self):
        """Test extracting duration from empty playlist."""
        duration = extract_hls_duration("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ENDLIST")

        assert duration == 0


class TestOutputValidatorHandler:
    """Tests for the output validator Lambda handler."""

    @patch("src.output_validator.handler.get_s3_client")
    def test_handler_success(
        self,
        mock_s3: MagicMock,
        sample_hls_master: str,
        sample_dash_mpd: str,
    ):
        """Test handler successfully validates outputs."""
        from src.output_validator.handler import handler

        # Mock S3 list objects response
        mock_s3.return_value.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "output/hls/master.m3u8"},
                {"Key": "output/hls/1080p/playlist.m3u8"},
                {"Key": "output/hls/1080p/segment_0001.ts"},
                {"Key": "output/dash/manifest.mpd"},
                {"Key": "output/dash/video_1080p/init.m4s"},
            ]
        }

        # Mock S3 get object for playlists
        mock_s3.return_value.get_object.side_effect = [
            {"Body": MagicMock(read=lambda: sample_hls_master.encode())},
            {"Body": MagicMock(read=lambda: sample_dash_mpd.encode())},
        ]

        event = {
            "manifest": {"manifest_id": "test-123", "mezzanine": {"duration_seconds": 1440.0}},
            "job_id": "job-456",
            "output_prefix": "s3://bucket/output",
            "variants": [{"resolution": "1920x1080", "bitrate_kbps": 6000}],
        }

        with patch("src.output_validator.handler.get_settings") as mock_settings:
            mock_settings.return_value.enable_dash = True
            result = handler(event, MagicMock())

        assert "validation_passed" in result
        assert "validations" in result

    @patch("src.output_validator.handler.get_s3_client")
    def test_handler_missing_files(self, mock_s3: MagicMock):
        """Test handler fails when output files are missing."""
        from src.output_validator.handler import handler

        # Mock S3 list objects response with no files
        mock_s3.return_value.list_objects_v2.return_value = {"Contents": []}

        event = {
            "manifest": {"manifest_id": "test-123", "mezzanine": {"duration_seconds": 1440.0}},
            "job_id": "job-456",
            "output_prefix": "s3://bucket/output",
            "variants": [],
        }

        with patch("src.output_validator.handler.get_settings") as mock_settings:
            mock_settings.return_value.enable_dash = False
            result = handler(event, MagicMock())

        assert result["validation_passed"] is False
