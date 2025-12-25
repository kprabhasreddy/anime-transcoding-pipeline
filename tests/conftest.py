"""Pytest configuration and shared fixtures.

This module provides:
- AWS credential mocking for moto
- Pre-configured AWS service clients
- Sample test data (manifests, playlists)
- Environment variable setup
"""

import os
from datetime import datetime
from typing import Any, Generator

import boto3
import pytest
from moto import mock_aws

# Set dummy AWS credentials BEFORE importing any application code
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

# Set application environment variables
os.environ["ENVIRONMENT"] = "dev"
os.environ["INPUT_BUCKET"] = "test-input-bucket"
os.environ["OUTPUT_BUCKET"] = "test-output-bucket"
os.environ["MEDIACONVERT_ENDPOINT"] = "https://test.mediaconvert.us-east-1.amazonaws.com"
os.environ["MEDIACONVERT_ROLE_ARN"] = "arn:aws:iam::123456789012:role/MediaConvertRole"
os.environ["MEDIACONVERT_QUEUE_ARN"] = "arn:aws:mediaconvert:us-east-1:123456789012:queues/Default"
os.environ["MOCK_MODE"] = "true"
os.environ["LOG_LEVEL"] = "DEBUG"


# =============================================================================
# AWS Fixtures
# =============================================================================


@pytest.fixture
def aws_credentials() -> None:
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client(aws_credentials: None) -> Generator[Any, None, None]:
    """Mocked S3 client."""
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def dynamodb_client(aws_credentials: None) -> Generator[Any, None, None]:
    """Mocked DynamoDB client."""
    with mock_aws():
        yield boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def sns_client(aws_credentials: None) -> Generator[Any, None, None]:
    """Mocked SNS client."""
    with mock_aws():
        yield boto3.client("sns", region_name="us-east-1")


@pytest.fixture
def s3_buckets(s3_client: Any) -> dict[str, str]:
    """Create test S3 buckets."""
    s3_client.create_bucket(Bucket="test-input-bucket")
    s3_client.create_bucket(Bucket="test-output-bucket")
    return {
        "input": "test-input-bucket",
        "output": "test-output-bucket",
    }


@pytest.fixture
def idempotency_table(dynamodb_client: Any) -> str:
    """Create DynamoDB idempotency table."""
    table_name = "test-idempotency"
    dynamodb_client.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName": "idempotency_token", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "idempotency_token", "KeyType": "HASH"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table_name


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_manifest_xml() -> str:
    """Complete valid anime manifest XML."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<AnimeTranscodeManifest version="1.0">
    <ManifestId>aot-s01e01-2024-001</ManifestId>

    <Episode>
        <SeriesId>attack-on-titan</SeriesId>
        <SeriesTitle>Attack on Titan</SeriesTitle>
        <SeriesTitleJa>進撃の巨人</SeriesTitleJa>
        <SeasonNumber>1</SeasonNumber>
        <EpisodeNumber>1</EpisodeNumber>
        <EpisodeTitle>To You, in 2000 Years: The Fall of Shiganshina, Part 1</EpisodeTitle>
        <EpisodeTitleJa>二千年後の君へ ―シガンシナ陥落①―</EpisodeTitleJa>
        <EpisodeDescription>After 100 years of peace, humanity is reminded of the terror of being at the Titans' mercy.</EpisodeDescription>
        <DurationSeconds>1440.5</DurationSeconds>
        <ReleaseDate>2013-04-07T00:00:00Z</ReleaseDate>
        <ContentRating>TV-MA</ContentRating>
        <IsSimulcast>false</IsSimulcast>
        <IsDubbed>true</IsDubbed>
    </Episode>

    <Mezzanine>
        <FilePath>mezzanines/attack-on-titan/s01/e01/aot_s01e01_mezzanine.mxf</FilePath>
        <ChecksumMD5>d41d8cd98f00b204e9800998ecf8427e</ChecksumMD5>
        <ChecksumXXHash>a2b9c3d4e5f67890</ChecksumXXHash>
        <FileSizeBytes>15728640000</FileSizeBytes>
        <DurationSeconds>1440.5</DurationSeconds>
        <VideoCodec>ProRes 422 HQ</VideoCodec>
        <AudioCodec>PCM</AudioCodec>
        <ResolutionWidth>1920</ResolutionWidth>
        <ResolutionHeight>1080</ResolutionHeight>
        <FrameRate>23.976</FrameRate>
        <BitrateKbps>220000</BitrateKbps>
        <ColorSpace>BT.709</ColorSpace>
        <BitDepth>10</BitDepth>
    </Mezzanine>

    <AudioTracks>
        <AudioTrack>
            <Language>ja</Language>
            <Label>Japanese</Label>
            <IsDefault>true</IsDefault>
            <Channels>2</Channels>
            <TrackIndex>1</TrackIndex>
        </AudioTrack>
        <AudioTrack>
            <Language>en</Language>
            <Label>English (Funimation Dub)</Label>
            <IsDefault>false</IsDefault>
            <Channels>2</Channels>
            <TrackIndex>2</TrackIndex>
        </AudioTrack>
    </AudioTracks>

    <SubtitleTracks>
        <SubtitleTrack>
            <Language>en</Language>
            <Label>English</Label>
            <FilePath>subtitles/attack-on-titan/s01/e01/aot_s01e01_en.vtt</FilePath>
            <IsDefault>true</IsDefault>
            <IsForced>false</IsForced>
            <Format>WebVTT</Format>
        </SubtitleTrack>
        <SubtitleTrack>
            <Language>es-419</Language>
            <Label>Spanish (Latin America)</Label>
            <FilePath>subtitles/attack-on-titan/s01/e01/aot_s01e01_es-latam.vtt</FilePath>
            <IsDefault>false</IsDefault>
            <IsForced>false</IsForced>
            <Format>WebVTT</Format>
        </SubtitleTrack>
    </SubtitleTracks>

    <Priority>5</Priority>
</AnimeTranscodeManifest>
"""


@pytest.fixture
def invalid_manifest_xml() -> str:
    """Invalid manifest XML (missing required elements)."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<AnimeTranscodeManifest version="1.0">
    <ManifestId>invalid-001</ManifestId>
    <!-- Missing Episode and Mezzanine elements -->
</AnimeTranscodeManifest>
"""


@pytest.fixture
def malformed_manifest_xml() -> str:
    """Malformed XML (syntax error)."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<AnimeTranscodeManifest>
    <ManifestId>broken
    <!-- Missing closing tags -->
"""


@pytest.fixture
def sample_hls_master() -> str:
    """Sample HLS master playlist."""
    return """#EXTM3U
#EXT-X-VERSION:4

#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,CODECS="avc1.640028,mp4a.40.2",AUDIO="audio"
h264_1080p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=3500000,RESOLUTION=1280x720,CODECS="avc1.640020,mp4a.40.2",AUDIO="audio"
h264_720p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=1800000,RESOLUTION=854x480,CODECS="avc1.4d401f,mp4a.40.2",AUDIO="audio"
h264_480p/playlist.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2",AUDIO="audio"
h264_360p/playlist.m3u8

#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="ja",NAME="Japanese",DEFAULT=YES,AUTOSELECT=YES,URI="audio_ja/playlist.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="en",NAME="English",DEFAULT=NO,AUTOSELECT=YES,URI="audio_en/playlist.m3u8"
"""


@pytest.fixture
def sample_hls_media() -> str:
    """Sample HLS media playlist (video segments)."""
    return """#EXTM3U
#EXT-X-VERSION:4
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD

#EXTINF:6.000,
segment_000.ts
#EXTINF:6.000,
segment_001.ts
#EXTINF:6.000,
segment_002.ts
#EXTINF:6.000,
segment_003.ts
#EXTINF:5.500,
segment_004.ts

#EXT-X-ENDLIST
"""


@pytest.fixture
def sample_dash_mpd() -> str:
    """Sample DASH MPD manifest."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     xmlns:cenc="urn:mpeg:cenc:2013"
     type="static"
     mediaPresentationDuration="PT24M0.5S"
     minBufferTime="PT2S"
     profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">

    <Period id="1" start="PT0S">
        <AdaptationSet id="1" mimeType="video/mp4" contentType="video" segmentAlignment="true">
            <Representation id="h264_1080p" bandwidth="6000000" width="1920" height="1080" codecs="avc1.640028">
                <SegmentTemplate media="h264_1080p/segment_$Number$.m4s" initialization="h264_1080p/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
            <Representation id="h264_720p" bandwidth="3500000" width="1280" height="720" codecs="avc1.640020">
                <SegmentTemplate media="h264_720p/segment_$Number$.m4s" initialization="h264_720p/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
            <Representation id="h264_480p" bandwidth="1800000" width="854" height="480" codecs="avc1.4d401f">
                <SegmentTemplate media="h264_480p/segment_$Number$.m4s" initialization="h264_480p/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
            <Representation id="h264_360p" bandwidth="800000" width="640" height="360" codecs="avc1.4d401e">
                <SegmentTemplate media="h264_360p/segment_$Number$.m4s" initialization="h264_360p/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
            <Representation id="h265_1080p" bandwidth="4500000" width="1920" height="1080" codecs="hvc1.1.6.L120">
                <SegmentTemplate media="h265_1080p/segment_$Number$.m4s" initialization="h265_1080p/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
        </AdaptationSet>

        <AdaptationSet id="2" mimeType="audio/mp4" contentType="audio" lang="ja" segmentAlignment="true">
            <Representation id="audio_ja" bandwidth="128000" codecs="mp4a.40.2" audioSamplingRate="48000">
                <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2"/>
                <SegmentTemplate media="audio_ja/segment_$Number$.m4s" initialization="audio_ja/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
        </AdaptationSet>

        <AdaptationSet id="3" mimeType="audio/mp4" contentType="audio" lang="en" segmentAlignment="true">
            <Representation id="audio_en" bandwidth="128000" codecs="mp4a.40.2" audioSamplingRate="48000">
                <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2"/>
                <SegmentTemplate media="audio_en/segment_$Number$.m4s" initialization="audio_en/init.m4s" duration="6000" timescale="1000"/>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>
"""


@pytest.fixture
def sample_manifest_dict() -> dict:
    """Parsed manifest as dictionary (matches Pydantic model structure)."""
    return {
        "manifest_version": "1.0",
        "manifest_id": "aot-s01e01-2024-001",
        "created_at": datetime(2024, 1, 15, 10, 0, 0),
        "episode": {
            "series_id": "attack-on-titan",
            "series_title": "Attack on Titan",
            "series_title_ja": "進撃の巨人",
            "season_number": 1,
            "episode_number": 1,
            "episode_title": "To You, in 2000 Years: The Fall of Shiganshina, Part 1",
            "episode_title_ja": "二千年後の君へ ―シガンシナ陥落①―",
            "episode_description": "After 100 years of peace, humanity is reminded of the terror.",
            "duration_seconds": 1440.5,
            "release_date": datetime(2013, 4, 7),
            "content_rating": "TV-MA",
            "is_simulcast": False,
            "is_dubbed": True,
        },
        "mezzanine": {
            "file_path": "mezzanines/attack-on-titan/s01/e01/aot_s01e01_mezzanine.mxf",
            "checksum_md5": "d41d8cd98f00b204e9800998ecf8427e",
            "checksum_xxhash": "a2b9c3d4e5f67890",
            "file_size_bytes": 15728640000,
            "duration_seconds": 1440.5,
            "video_codec": "ProRes 422 HQ",
            "audio_codec": "PCM",
            "resolution_width": 1920,
            "resolution_height": 1080,
            "frame_rate": 23.976,
            "bitrate_kbps": 220000,
            "color_space": "BT.709",
            "bit_depth": 10,
        },
        "audio_tracks": [
            {
                "language": "ja",
                "label": "Japanese",
                "is_default": True,
                "channels": 2,
                "track_index": 1,
            },
            {
                "language": "en",
                "label": "English (Funimation Dub)",
                "is_default": False,
                "channels": 2,
                "track_index": 2,
            },
        ],
        "subtitle_tracks": [
            {
                "language": "en",
                "label": "English",
                "file_path": "subtitles/attack-on-titan/s01/e01/aot_s01e01_en.vtt",
                "is_default": True,
                "is_forced": False,
                "format": "WebVTT",
            },
        ],
        "priority": 5,
        "callback_url": None,
    }


@pytest.fixture
def expected_abr_variants() -> list[dict]:
    """Expected ABR ladder variants for 1080p source."""
    return [
        {"resolution": "1920x1080", "bitrate_kbps": 6000, "codec": "h264"},
        {"resolution": "1280x720", "bitrate_kbps": 3500, "codec": "h264"},
        {"resolution": "854x480", "bitrate_kbps": 1800, "codec": "h264"},
        {"resolution": "640x360", "bitrate_kbps": 800, "codec": "h264"},
        {"resolution": "1920x1080", "bitrate_kbps": 4500, "codec": "h265"},
        {"resolution": "1280x720", "bitrate_kbps": 2500, "codec": "h265"},
    ]


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture
def mock_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up complete mock environment."""
    env_vars = {
        "ENVIRONMENT": "dev",
        "AWS_REGION": "us-east-1",
        "INPUT_BUCKET": "test-input-bucket",
        "OUTPUT_BUCKET": "test-output-bucket",
        "MEDIACONVERT_ENDPOINT": "https://test.mediaconvert.us-east-1.amazonaws.com",
        "MEDIACONVERT_ROLE_ARN": "arn:aws:iam::123456789012:role/MediaConvertRole",
        "MEDIACONVERT_QUEUE_ARN": "arn:aws:mediaconvert:us-east-1:123456789012:queues/Default",
        "STEP_FUNCTION_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:TranscodePipeline",
        "IDEMPOTENCY_TABLE": "test-idempotency",
        "KMS_KEY_ID": "alias/test-key",
        "SNS_SUCCESS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:success",
        "SNS_ERROR_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:errors",
        "MOCK_MODE": "true",
        "ENABLE_H265": "true",
        "ENABLE_DASH": "true",
        "LOG_LEVEL": "DEBUG",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    # Clear cached settings
    from src.shared.config import clear_settings_cache

    clear_settings_cache()


# =============================================================================
# S3 Event Fixtures
# =============================================================================


@pytest.fixture
def s3_put_event() -> dict:
    """Sample S3 PutObject event for manifest upload."""
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2024-01-15T10:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "test-input-bucket",
                        "arn": "arn:aws:s3:::test-input-bucket",
                    },
                    "object": {
                        "key": "manifests/attack-on-titan-s1e1.xml",
                        "size": 2048,
                        "eTag": "abc123",
                    },
                },
            }
        ]
    }


@pytest.fixture
def mediaconvert_complete_event() -> dict:
    """Sample MediaConvert job completion event."""
    return {
        "version": "0",
        "id": "abc123-def456",
        "detail-type": "MediaConvert Job State Change",
        "source": "aws.mediaconvert",
        "account": "123456789012",
        "time": "2024-01-15T10:30:00Z",
        "region": "us-east-1",
        "detail": {
            "status": "COMPLETE",
            "jobId": "1234567890123-abc123",
            "queue": "arn:aws:mediaconvert:us-east-1:123456789012:queues/Default",
            "userMetadata": {
                "manifest_id": "aot-s01e01-2024-001",
                "series_id": "attack-on-titan",
                "episode": "S01E001",
            },
            "outputGroupDetails": [
                {
                    "type": "HLS_GROUP",
                    "outputDetails": [
                        {"outputFilePaths": ["s3://test-output-bucket/hls/master.m3u8"]}
                    ],
                },
                {
                    "type": "DASH_ISO_GROUP",
                    "outputDetails": [
                        {"outputFilePaths": ["s3://test-output-bucket/dash/manifest.mpd"]}
                    ],
                },
            ],
        },
    }


@pytest.fixture
def mediaconvert_error_event() -> dict:
    """Sample MediaConvert job error event."""
    return {
        "version": "0",
        "id": "abc123-def456",
        "detail-type": "MediaConvert Job State Change",
        "source": "aws.mediaconvert",
        "account": "123456789012",
        "time": "2024-01-15T10:30:00Z",
        "region": "us-east-1",
        "detail": {
            "status": "ERROR",
            "jobId": "1234567890123-abc123",
            "queue": "arn:aws:mediaconvert:us-east-1:123456789012:queues/Default",
            "errorCode": "1000",
            "errorMessage": "Failed to read input file",
            "userMetadata": {
                "manifest_id": "aot-s01e01-2024-001",
            },
        },
    }
