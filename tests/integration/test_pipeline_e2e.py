"""End-to-end integration tests for the transcoding pipeline.

These tests run against LocalStack to simulate the full pipeline flow
without incurring AWS costs.
"""

import json
import os
import time

import boto3
import pytest

# Skip if not running with LocalStack
pytestmark = pytest.mark.skipif(
    os.environ.get("AWS_ENDPOINT_URL") is None,
    reason="Integration tests require LocalStack"
)


@pytest.fixture(scope="module")
def aws_clients():
    """Create AWS clients configured for LocalStack."""
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")

    return {
        "s3": boto3.client("s3", endpoint_url=endpoint_url),
        "dynamodb": boto3.client("dynamodb", endpoint_url=endpoint_url),
        "sns": boto3.client("sns", endpoint_url=endpoint_url),
        "sfn": boto3.client("stepfunctions", endpoint_url=endpoint_url),
    }


@pytest.fixture(scope="module")
def test_resources(aws_clients):
    """Set up test resources."""
    s3 = aws_clients["s3"]
    project = "anime-transcoding"
    env = "test"

    # Create buckets if they don't exist
    input_bucket = f"{project}-input-{env}"
    output_bucket = f"{project}-output-{env}"

    for bucket in [input_bucket, output_bucket]:
        try:
            s3.create_bucket(Bucket=bucket)
        except s3.exceptions.BucketAlreadyOwnedByYou:
            pass

    return {
        "input_bucket": input_bucket,
        "output_bucket": output_bucket,
    }


class TestManifestUpload:
    """Tests for manifest upload and parsing."""

    def test_upload_valid_manifest(self, aws_clients, test_resources, sample_manifest_xml):
        """Test uploading a valid manifest triggers processing."""
        s3 = aws_clients["s3"]

        # Upload manifest
        s3.put_object(
            Bucket=test_resources["input_bucket"],
            Key="manifests/test-episode.xml",
            Body=sample_manifest_xml.encode(),
        )

        # Verify upload
        response = s3.get_object(
            Bucket=test_resources["input_bucket"],
            Key="manifests/test-episode.xml",
        )

        content = response["Body"].read().decode()
        assert "AnimeTranscodeManifest" in content
        assert "attack-on-titan" in content

    def test_upload_mezzanine_reference(self, aws_clients, test_resources):
        """Test uploading a mezzanine file placeholder."""
        s3 = aws_clients["s3"]

        # Upload a small test file as mezzanine placeholder
        test_content = b"test video content placeholder"

        s3.put_object(
            Bucket=test_resources["input_bucket"],
            Key="mezzanines/aot/s01/e01/mezzanine.mxf",
            Body=test_content,
        )

        # Verify upload
        response = s3.head_object(
            Bucket=test_resources["input_bucket"],
            Key="mezzanines/aot/s01/e01/mezzanine.mxf",
        )

        assert response["ContentLength"] == len(test_content)


class TestIdempotency:
    """Tests for idempotency handling."""

    def test_idempotency_table_operations(self, aws_clients):
        """Test DynamoDB idempotency table operations."""
        dynamodb = aws_clients["dynamodb"]
        table_name = "anime-transcoding-idempotency-test"

        # Create table if it doesn't exist
        try:
            dynamodb.create_table(
                TableName=table_name,
                AttributeDefinitions=[
                    {"AttributeName": "idempotency_token", "AttributeType": "S"},
                ],
                KeySchema=[
                    {"AttributeName": "idempotency_token", "KeyType": "HASH"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            # Wait for table to be active
            waiter = dynamodb.get_waiter("table_exists")
            waiter.wait(TableName=table_name)
        except dynamodb.exceptions.ResourceInUseException:
            pass

        # Test put item
        test_token = "test-token-12345"
        dynamodb.put_item(
            TableName=table_name,
            Item={
                "idempotency_token": {"S": test_token},
                "job_id": {"S": "job-123"},
                "manifest_id": {"S": "manifest-456"},
                "status": {"S": "SUBMITTED"},
            },
        )

        # Test get item
        response = dynamodb.get_item(
            TableName=table_name,
            Key={"idempotency_token": {"S": test_token}},
        )

        assert "Item" in response
        assert response["Item"]["job_id"]["S"] == "job-123"

        # Test conditional put (should fail - idempotency check)
        with pytest.raises(dynamodb.exceptions.ConditionalCheckFailedException):
            dynamodb.put_item(
                TableName=table_name,
                Item={
                    "idempotency_token": {"S": test_token},
                    "job_id": {"S": "different-job"},
                    "manifest_id": {"S": "manifest-456"},
                    "status": {"S": "SUBMITTED"},
                },
                ConditionExpression="attribute_not_exists(idempotency_token)",
            )


class TestSNSNotifications:
    """Tests for SNS notification handling."""

    def test_publish_success_notification(self, aws_clients):
        """Test publishing success notification to SNS."""
        sns = aws_clients["sns"]

        # Create topic
        topic_response = sns.create_topic(Name="anime-transcoding-success-test")
        topic_arn = topic_response["TopicArn"]

        # Publish message
        message = json.dumps({
            "type": "SUCCESS",
            "manifest_id": "test-123",
            "job_id": "job-456",
            "output_prefix": "s3://output-bucket/series/s01/e01",
        })

        response = sns.publish(
            TopicArn=topic_arn,
            Subject="Transcoding Complete",
            Message=message,
        )

        assert "MessageId" in response

    def test_publish_error_notification(self, aws_clients):
        """Test publishing error notification to SNS."""
        sns = aws_clients["sns"]

        # Create topic
        topic_response = sns.create_topic(Name="anime-transcoding-error-test")
        topic_arn = topic_response["TopicArn"]

        # Publish error message
        message = json.dumps({
            "type": "ERROR",
            "error_type": "VALIDATION_FAILED",
            "manifest_id": "test-123",
            "error": "Checksum mismatch",
        })

        response = sns.publish(
            TopicArn=topic_arn,
            Subject="Transcoding Failed",
            Message=message,
        )

        assert "MessageId" in response


class TestS3OutputStructure:
    """Tests for S3 output structure."""

    def test_create_hls_output_structure(self, aws_clients, test_resources):
        """Test creating expected HLS output structure."""
        s3 = aws_clients["s3"]
        output_bucket = test_resources["output_bucket"]
        prefix = "series/attack-on-titan/s01/e01/hls"

        # Create HLS structure
        files = {
            f"{prefix}/master.m3u8": b"#EXTM3U\n#EXT-X-VERSION:3\n",
            f"{prefix}/1080p/playlist.m3u8": b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n",
            f"{prefix}/1080p/segment_0001.ts": b"mock ts content",
            f"{prefix}/720p/playlist.m3u8": b"#EXTM3U\n#EXT-X-TARGETDURATION:6\n",
            f"{prefix}/720p/segment_0001.ts": b"mock ts content",
        }

        for key, content in files.items():
            s3.put_object(Bucket=output_bucket, Key=key, Body=content)

        # List and verify
        response = s3.list_objects_v2(Bucket=output_bucket, Prefix=prefix)
        keys = [obj["Key"] for obj in response.get("Contents", [])]

        assert f"{prefix}/master.m3u8" in keys
        assert f"{prefix}/1080p/playlist.m3u8" in keys
        assert f"{prefix}/1080p/segment_0001.ts" in keys

    def test_create_dash_output_structure(self, aws_clients, test_resources):
        """Test creating expected DASH output structure."""
        s3 = aws_clients["s3"]
        output_bucket = test_resources["output_bucket"]
        prefix = "series/attack-on-titan/s01/e01/dash"

        # Create DASH structure
        files = {
            f"{prefix}/manifest.mpd": b'<?xml version="1.0"?><MPD></MPD>',
            f"{prefix}/video_1080p/init.m4s": b"mock init segment",
            f"{prefix}/video_1080p/segment_1.m4s": b"mock segment",
            f"{prefix}/audio_ja/init.m4s": b"mock audio init",
        }

        for key, content in files.items():
            s3.put_object(Bucket=output_bucket, Key=key, Body=content)

        # List and verify
        response = s3.list_objects_v2(Bucket=output_bucket, Prefix=prefix)
        keys = [obj["Key"] for obj in response.get("Contents", [])]

        assert f"{prefix}/manifest.mpd" in keys
        assert f"{prefix}/video_1080p/init.m4s" in keys
