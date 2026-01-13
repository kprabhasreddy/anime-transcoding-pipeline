"""Unit tests for manifest parser module."""

import pytest
from unittest.mock import MagicMock, patch

from src.manifest_parser.xml_parser import parse_manifest_xml, ManifestParseError
from src.manifest_parser.validators import (
    validate_manifest_schema,
    validate_business_rules,
    ValidationError,
)


class TestXMLParser:
    """Tests for XML parsing functionality."""

    def test_parse_valid_manifest(self, sample_manifest_xml: str):
        """Test parsing a valid anime manifest."""
        result = parse_manifest_xml(sample_manifest_xml)

        assert result["manifest_id"] == "aot-s01e01-2024-001"
        assert result["episode"]["series_id"] == "attack-on-titan"
        assert result["episode"]["series_title"] == "Attack on Titan"
        assert result["episode"]["season_number"] == 1
        assert result["episode"]["episode_number"] == 1
        assert result["mezzanine"]["resolution_width"] == 1920
        assert result["mezzanine"]["resolution_height"] == 1080

    def test_parse_manifest_with_japanese_title(self, sample_manifest_xml: str):
        """Test parsing manifest with Japanese title."""
        result = parse_manifest_xml(sample_manifest_xml)

        assert result["episode"]["series_title_ja"] == "進撃の巨人"

    def test_parse_audio_tracks(self, sample_manifest_xml: str):
        """Test parsing audio track information."""
        result = parse_manifest_xml(sample_manifest_xml)

        assert len(result["audio_tracks"]) == 2
        assert result["audio_tracks"][0]["language"] == "ja"
        assert result["audio_tracks"][0]["is_default"] is True
        assert result["audio_tracks"][1]["language"] == "en"

    def test_parse_subtitle_tracks(self, sample_manifest_xml: str):
        """Test parsing subtitle track information."""
        result = parse_manifest_xml(sample_manifest_xml)

        assert len(result["subtitle_tracks"]) == 1
        assert result["subtitle_tracks"][0]["language"] == "en"

    def test_parse_invalid_xml_raises_error(self):
        """Test that invalid XML raises ManifestParseError."""
        invalid_xml = "<invalid><unclosed>"

        with pytest.raises(ManifestParseError) as exc_info:
            parse_manifest_xml(invalid_xml)

        assert "Failed to parse" in str(exc_info.value)

    def test_parse_missing_required_element(self):
        """Test that missing required elements raise error."""
        incomplete_xml = """<?xml version="1.0"?>
        <AnimeTranscodeManifest version="1.0">
            <ManifestId>test-001</ManifestId>
        </AnimeTranscodeManifest>
        """

        with pytest.raises(ManifestParseError) as exc_info:
            parse_manifest_xml(incomplete_xml)

        assert "Missing required element" in str(exc_info.value)

    def test_parse_empty_xml_raises_error(self):
        """Test that empty XML raises error."""
        with pytest.raises(ManifestParseError):
            parse_manifest_xml("")

    def test_parse_non_manifest_xml_raises_error(self):
        """Test that non-manifest XML raises error."""
        wrong_xml = """<?xml version="1.0"?>
        <SomeOtherDocument>
            <Content>Not a manifest</Content>
        </SomeOtherDocument>
        """

        with pytest.raises(ManifestParseError) as exc_info:
            parse_manifest_xml(wrong_xml)

        assert "Invalid root element" in str(exc_info.value)


class TestManifestValidation:
    """Tests for manifest validation."""

    def test_validate_valid_manifest(self, sample_manifest_dict: dict):
        """Test validation passes for valid manifest."""
        # Should not raise
        validate_manifest_schema(sample_manifest_dict)
        validate_business_rules(sample_manifest_dict)

    def test_validate_missing_manifest_id(self, sample_manifest_dict: dict):
        """Test validation fails for missing manifest_id."""
        del sample_manifest_dict["manifest_id"]

        with pytest.raises(ValidationError) as exc_info:
            validate_manifest_schema(sample_manifest_dict)

        assert "manifest_id" in str(exc_info.value)

    def test_validate_invalid_resolution(self, sample_manifest_dict: dict):
        """Test validation fails for invalid resolution."""
        sample_manifest_dict["mezzanine"]["resolution_width"] = 100  # Too small

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "resolution" in str(exc_info.value).lower()

    def test_validate_resolution_too_large(self, sample_manifest_dict: dict):
        """Test validation fails for resolution too large."""
        sample_manifest_dict["mezzanine"]["resolution_width"] = 10000

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "resolution" in str(exc_info.value).lower()

    def test_validate_invalid_frame_rate(self, sample_manifest_dict: dict):
        """Test validation fails for invalid frame rate."""
        sample_manifest_dict["mezzanine"]["frame_rate"] = 1.0  # Too low

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "frame_rate" in str(exc_info.value).lower()

    def test_validate_negative_duration(self, sample_manifest_dict: dict):
        """Test validation fails for negative duration."""
        sample_manifest_dict["mezzanine"]["duration_seconds"] = -100

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "duration" in str(exc_info.value).lower()

    def test_validate_invalid_checksum_format(self, sample_manifest_dict: dict):
        """Test validation fails for invalid checksum format."""
        sample_manifest_dict["mezzanine"]["checksum_md5"] = "invalid"

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "checksum" in str(exc_info.value).lower()

    def test_validate_no_audio_tracks(self, sample_manifest_dict: dict):
        """Test validation fails when no audio tracks present."""
        sample_manifest_dict["audio_tracks"] = []

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "audio" in str(exc_info.value).lower()

    def test_validate_unsupported_codec(self, sample_manifest_dict: dict):
        """Test validation fails for unsupported codec."""
        sample_manifest_dict["mezzanine"]["video_codec"] = "UNSUPPORTED_CODEC"

        with pytest.raises(ValidationError) as exc_info:
            validate_business_rules(sample_manifest_dict)

        assert "codec" in str(exc_info.value).lower()


class TestManifestHandler:
    """Tests for the Lambda handler."""

    @patch("src.manifest_parser.handler.get_s3_client")
    @patch("src.manifest_parser.handler.get_sfn_client")
    def test_handler_success(
        self,
        mock_sfn: MagicMock,
        mock_s3: MagicMock,
        sample_manifest_xml: str,
        s3_event: dict,
    ):
        """Test handler successfully processes manifest."""
        from src.manifest_parser.handler import handler

        # Mock S3 response
        mock_s3.return_value.get_object.return_value = {
            "Body": MagicMock(read=lambda: sample_manifest_xml.encode())
        }

        # Mock Step Functions response
        mock_sfn.return_value.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789:execution:test:abc123"
        }

        result = handler(s3_event, MagicMock())

        assert result["status"] == "PIPELINE_STARTED"
        assert "execution_arn" in result
        mock_sfn.return_value.start_execution.assert_called_once()

    @patch("src.manifest_parser.handler.get_s3_client")
    def test_handler_invalid_manifest(
        self,
        mock_s3: MagicMock,
        s3_event: dict,
    ):
        """Test handler raises error for invalid manifest."""
        from src.manifest_parser.handler import handler
        from src.shared.exceptions import ManifestValidationError

        # Mock S3 response with invalid XML
        mock_s3.return_value.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"<invalid>")
        }

        with pytest.raises(ManifestValidationError):
            handler(s3_event, MagicMock())

    @patch("src.manifest_parser.handler.get_s3_client")
    def test_handler_s3_not_found(
        self,
        mock_s3: MagicMock,
        s3_event: dict,
    ):
        """Test handler raises error when file not found."""
        from src.manifest_parser.handler import handler
        from botocore.exceptions import ClientError

        mock_s3.return_value.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}},
            "GetObject"
        )

        with pytest.raises(ClientError):
            handler(s3_event, MagicMock())
