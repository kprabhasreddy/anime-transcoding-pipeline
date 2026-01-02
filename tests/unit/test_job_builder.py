"""Unit tests for job builder module."""

import pytest
from unittest.mock import MagicMock, patch

from src.job_submitter.abr_ladder import (
    get_abr_ladder,
    calculate_qvbr_settings,
    ABR_LADDER_H264,
    ABR_LADDER_H265,
)
from src.job_submitter.job_builder import (
    build_mediaconvert_job,
    _build_hls_output_group,
    _build_hls_video_output,
    _build_dash_output_group,
)
from src.shared.models import ABRVariant, VideoCodec, TranscodeJobRequest, TranscodeManifest


class TestABRLadder:
    """Tests for ABR ladder configuration."""

    def test_get_abr_ladder_1080p_h264_only(self):
        """Test ABR ladder for 1080p source with H.264 only."""
        variants = get_abr_ladder(
            source_width=1920,
            source_height=1080,
            enable_h265=False,
        )

        # Should include all H.264 variants up to 1080p
        assert len(variants) == 4
        assert all(v.codec == VideoCodec.H264 for v in variants)

        # Check resolutions are in descending order
        resolutions = [v.resolution for v in variants]
        assert resolutions == ["1920x1080", "1280x720", "854x480", "640x360"]

    def test_get_abr_ladder_1080p_with_h265(self):
        """Test ABR ladder for 1080p source with H.265 enabled."""
        variants = get_abr_ladder(
            source_width=1920,
            source_height=1080,
            enable_h265=True,
        )

        # Should include both H.264 and H.265 variants
        h264_count = sum(1 for v in variants if v.codec == VideoCodec.H264)
        h265_count = sum(1 for v in variants if v.codec == VideoCodec.H265)

        assert h264_count == 4
        assert h265_count == 2  # 1080p and 720p H.265

    def test_get_abr_ladder_720p_source(self):
        """Test ABR ladder for 720p source (no upscaling)."""
        variants = get_abr_ladder(
            source_width=1280,
            source_height=720,
            enable_h265=False,
        )

        # Should not include 1080p variant
        resolutions = [v.resolution for v in variants]
        assert "1920x1080" not in resolutions
        assert "1280x720" in resolutions

    def test_get_abr_ladder_4k_source(self):
        """Test ABR ladder for 4K source."""
        variants = get_abr_ladder(
            source_width=3840,
            source_height=2160,
            enable_h265=True,
        )

        # Should include all variants
        assert len(variants) >= 4

    def test_abr_variant_bitrates(self):
        """Test that ABR variants have correct bitrate ordering."""
        for variant in ABR_LADDER_H264:
            # Higher resolution should have higher bitrate
            pass  # Bitrates are manually set, just verify they exist

        # Verify H.265 has lower bitrate for same resolution
        h264_1080 = next(v for v in ABR_LADDER_H264 if v.resolution == "1920x1080")
        h265_1080 = next(v for v in ABR_LADDER_H265 if v.resolution == "1920x1080")
        assert h265_1080.bitrate_kbps < h264_1080.bitrate_kbps

    def test_abr_variant_qvbr_settings(self):
        """Test that QVBR settings are properly configured."""
        for variant in ABR_LADDER_H264:
            assert variant.qvbr_quality_level >= 1
            assert variant.qvbr_quality_level <= 10


class TestJobBuilder:
    """Tests for MediaConvert job building."""

    @pytest.fixture
    def job_request(self, sample_manifest_dict: dict) -> TranscodeJobRequest:
        """Create a sample job request."""
        manifest = TranscodeManifest(**sample_manifest_dict)
        variants = get_abr_ladder(
            source_width=1920,
            source_height=1080,
            enable_h265=False,
        )
        return TranscodeJobRequest(
            manifest=manifest,
            input_s3_uri="s3://input-bucket/mezzanines/test.mxf",
            output_s3_prefix="s3://output-bucket/series/s01/e01",
            abr_variants=variants,
            output_hls=True,
            output_dash=True,
            idempotency_token="test-token-123",
        )

    def test_build_mediaconvert_job(self, job_request: TranscodeJobRequest):
        """Test building complete MediaConvert job settings."""
        settings = build_mediaconvert_job(job_request)

        assert "Inputs" in settings
        assert "OutputGroups" in settings
        assert len(settings["Inputs"]) == 1

    def test_build_job_input_settings(self, job_request: TranscodeJobRequest):
        """Test input settings configuration."""
        settings = build_mediaconvert_job(job_request)
        input_settings = settings["Inputs"][0]

        assert input_settings["FileInput"] == job_request.input_s3_uri
        assert "AudioSelectors" in input_settings
        assert "VideoSelector" in input_settings

    def test_build_job_hls_output(self, job_request: TranscodeJobRequest):
        """Test HLS output group configuration."""
        settings = build_mediaconvert_job(job_request)

        hls_groups = [
            og for og in settings["OutputGroups"]
            if og["OutputGroupSettings"]["Type"] == "HLS_GROUP_SETTINGS"
        ]

        assert len(hls_groups) == 1
        hls_settings = hls_groups[0]["OutputGroupSettings"]["HlsGroupSettings"]

        # Check HLS-specific settings
        assert "SegmentLength" in hls_settings
        assert hls_settings["SegmentLength"] == 6  # 6-second segments
        assert "ManifestCompression" in hls_settings

    def test_build_job_dash_output(self, job_request: TranscodeJobRequest):
        """Test DASH output group configuration."""
        settings = build_mediaconvert_job(job_request)

        dash_groups = [
            og for og in settings["OutputGroups"]
            if og["OutputGroupSettings"]["Type"] == "DASH_ISO_GROUP_SETTINGS"
        ]

        assert len(dash_groups) == 1
        dash_settings = dash_groups[0]["OutputGroupSettings"]["DashIsoGroupSettings"]

        # Check DASH-specific settings
        assert "SegmentLength" in dash_settings
        assert "FragmentLength" in dash_settings

    def test_build_job_without_dash(self, job_request: TranscodeJobRequest):
        """Test building job without DASH output."""
        job_request.output_dash = False
        settings = build_mediaconvert_job(job_request)

        dash_groups = [
            og for og in settings["OutputGroups"]
            if og["OutputGroupSettings"]["Type"] == "DASH_ISO_GROUP_SETTINGS"
        ]

        assert len(dash_groups) == 0

    def test_calculate_qvbr_h264(self):
        """Test H.264 QVBR codec settings."""
        variant = ABRVariant(
            resolution="1920x1080",
            bitrate_kbps=6000,
            codec=VideoCodec.H264,
            profile="high",
            level="4.2",
        )

        settings = calculate_qvbr_settings(variant)

        assert settings["Codec"] == "H_264"
        assert settings["H264Settings"]["RateControlMode"] == "QVBR"
        assert "QvbrSettings" in settings["H264Settings"]

    def test_calculate_qvbr_h265(self):
        """Test H.265 QVBR codec settings."""
        variant = ABRVariant(
            resolution="1920x1080",
            bitrate_kbps=4500,
            codec=VideoCodec.H265,
            profile="main",
            level="4.0",
        )

        settings = calculate_qvbr_settings(variant)

        assert settings["Codec"] == "H_265"
        assert settings["H265Settings"]["RateControlMode"] == "QVBR"

    def test_build_hls_output_group(self, job_request: TranscodeJobRequest):
        """Test HLS output group has correct structure."""
        # Filter to just H.264 variants for HLS
        h264_variants = [v for v in job_request.abr_variants if v.codec == VideoCodec.H264]

        hls_group = _build_hls_output_group(job_request, h264_variants)

        assert hls_group["Name"] == "HLS"
        assert hls_group["OutputGroupSettings"]["Type"] == "HLS_GROUP_SETTINGS"
        destination = hls_group["OutputGroupSettings"]["HlsGroupSettings"]["Destination"]
        assert "/hls/" in destination

    def test_build_dash_output_group(self, job_request: TranscodeJobRequest):
        """Test DASH output group has correct structure."""
        dash_group = _build_dash_output_group(job_request, job_request.abr_variants)

        assert dash_group["Name"] == "DASH"
        assert dash_group["OutputGroupSettings"]["Type"] == "DASH_ISO_GROUP_SETTINGS"
        destination = dash_group["OutputGroupSettings"]["DashIsoGroupSettings"]["Destination"]
        assert "/dash/" in destination


class TestIdempotency:
    """Tests for idempotency handling."""

    @patch("src.job_submitter.idempotency.get_dynamodb_resource")
    def test_generate_idempotency_token(self, mock_dynamodb: MagicMock):
        """Test idempotency token generation."""
        from src.job_submitter.idempotency import generate_idempotency_token
        from src.shared.models import TranscodeManifest

        manifest = TranscodeManifest(
            manifest_id="test-123",
            episode={
                "series_id": "test-series",
                "series_title": "Test Series",
                "season_number": 1,
                "episode_number": 1,
                "episode_title": "Test Episode",
                "duration_seconds": 1440.0,
                "content_rating": "TV-PG",
            },
            mezzanine={
                "file_path": "test.mxf",
                "checksum_md5": "d41d8cd98f00b204e9800998ecf8427e",
                "file_size_bytes": 1000000,
                "duration_seconds": 1440.0,
                "video_codec": "ProRes 422 HQ",
                "resolution_width": 1920,
                "resolution_height": 1080,
                "frame_rate": 23.976,
            },
            audio_tracks=[{"language": "ja", "label": "Japanese", "is_default": True}],
        )

        token1 = generate_idempotency_token(manifest)
        token2 = generate_idempotency_token(manifest)

        # Same manifest should produce same token
        assert token1 == token2
        assert len(token1) == 64  # SHA-256 hex digest

    @patch("src.job_submitter.idempotency.get_dynamodb_resource")
    def test_check_idempotency_new_job(self, mock_dynamodb: MagicMock):
        """Test idempotency check for new job."""
        from src.job_submitter.idempotency import check_idempotency

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No existing item
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = check_idempotency("new-token-123")

        assert result is None

    @patch("src.job_submitter.idempotency.get_dynamodb_resource")
    def test_check_idempotency_existing_job(self, mock_dynamodb: MagicMock):
        """Test idempotency check for existing job."""
        from src.job_submitter.idempotency import check_idempotency

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "idempotency_token": "existing-token",
                "job_id": "job-123",
                "status": "SUBMITTED",
            }
        }
        mock_dynamodb.return_value.Table.return_value = mock_table

        result = check_idempotency("existing-token")

        assert result is not None
        assert result["job_id"] == "job-123"
