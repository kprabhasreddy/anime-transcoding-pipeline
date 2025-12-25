# Anime Transcoding Pipeline

> Production-grade AWS video transcoding pipeline demonstrating enterprise streaming patterns

[![CI](https://github.com/kprabhasreddy/anime-transcoding-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/kprabhasreddy/anime-transcoding-pipeline/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/kprabhasreddy/anime-transcoding-pipeline/branch/main/graph/badge.svg)](https://codecov.io/gh/kprabhasreddy/anime-transcoding-pipeline)
[![Terraform](https://img.shields.io/badge/terraform-1.5+-purple.svg)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

A serverless video transcoding pipeline built for anime streaming, demonstrating the architecture patterns used by major streaming platforms. This project showcases expertise in:

- **Video Engineering**: ABR ladder configuration, QVBR encoding, HLS/DASH packaging
- **AWS Expertise**: MediaConvert, Step Functions, Lambda, CloudFront, S3
- **Infrastructure as Code**: Modular Terraform with security best practices
- **Quality Assurance**: Checksum validation, duration matching, playlist verification
- **Observability**: CloudWatch dashboards, alarms, structured logging with Powertools

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ANIME TRANSCODING PIPELINE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐     ┌─────────────┐     ┌──────────────────────────────────┐  │
│  │   XML    │────▶│  S3 Input   │────▶│      Lambda: Manifest Parser     │  │
│  │ Manifest │     │   Bucket    │     │  - Parse anime metadata          │  │
│  └──────────┘     │  (KMS enc)  │     │  - Validate schema               │  │
│                   └─────────────┘     │  - Trigger Step Functions        │  │
│  ┌──────────┐           │             └──────────────┬───────────────────┘  │
│  │Mezzanine │───────────┘                            │                      │
│  │  File    │                                        ▼                      │
│  └──────────┘                        ┌───────────────────────────────────┐  │
│                                      │     Step Functions Orchestrator   │  │
│                                      │  ┌─────────────────────────────┐  │  │
│                                      │  │  1. Input Validation        │  │  │
│                                      │  │     - Checksum (MD5/XXHash) │  │  │
│                                      │  │     - File size match       │  │  │
│                                      │  │     - Container validation  │  │  │
│                                      │  └──────────────┬──────────────┘  │  │
│                                      │                 ▼                  │  │
│                                      │  ┌─────────────────────────────┐  │  │
│                                      │  │  2. Job Submission          │  │  │
│                                      │  │     - Build ABR ladder      │  │  │
│                                      │  │     - Idempotency check     │  │  │
│                                      │  │     - Submit to MediaConvert│  │  │
│                                      │  └──────────────┬──────────────┘  │  │
│                                      │                 ▼                  │  │
│                                      │  ┌─────────────────────────────┐  │  │
│                                      │  │  3. MediaConvert            │  │  │
│                                      │  │     - H.264 + H.265 (QVBR)  │  │  │
│                                      │  │     - HLS + DASH outputs    │  │  │
│  ┌──────────────┐                    │  │     - Multiple bitrates     │  │  │
│  │  CloudWatch  │◀───────────────────│  └──────────────┬──────────────┘  │  │
│  │  Dashboard   │                    │                 ▼                  │  │
│  │  + Alarms    │                    │  ┌─────────────────────────────┐  │  │
│  └──────────────┘                    │  │  4. Output Validation       │  │  │
│         │                            │  │     - HLS playlist check    │  │  │
│         ▼                            │  │     - DASH MPD validation   │  │  │
│  ┌──────────────┐                    │  │     - Duration matching     │  │  │
│  │     SNS      │                    │  └──────────────┬──────────────┘  │  │
│  │Notifications │                    │                 ▼                  │  │
│  └──────────────┘                    │  ┌─────────────────────────────┐  │  │
│                                      │  │  5. Notification            │  │  │
│                                      │  │     - Success/Error alerts  │  │  │
│                                      │  └─────────────────────────────┘  │  │
│                                      └───────────────────────────────────┘  │
│                                                       │                      │
│                                                       ▼                      │
│                   ┌─────────────┐     ┌──────────────────────────────────┐  │
│                   │  S3 Output  │────▶│          CloudFront CDN          │  │
│                   │   Bucket    │     │  - Signed URLs for protection    │  │
│                   │  (KMS enc)  │     │  - Global edge caching           │  │
│                   └─────────────┘     │  - HLS/DASH streaming            │  │
│                                       └──────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Real-World Mapping

| This Project | Production Streaming Equivalent |
|--------------|--------------------------------|
| XML Manifest Parser | Content ingestion from licensors/studios |
| ABR Ladder Config | Adaptive streaming for global audience |
| Multi-audio tracks | Japanese + dub support |
| Checksum validation | QC before publishing |
| Duration matching | Sync validation for subtitles |
| CloudFront signed URLs | Subscriber-only content protection |
| QVBR encoding | Quality-optimized delivery |

## Quick Start

### Prerequisites

- Python 3.11+
- Terraform 1.5+
- Docker & Docker Compose
- AWS CLI (optional, for real deployments)

### One-Click Local Setup

```bash
# Clone the repository
git clone https://github.com/kprabhasreddy/anime-transcoding-pipeline.git
cd anime-transcoding-pipeline

# Start LocalStack and initialize resources
make local

# Run the demo with sample anime episode
make demo
```

### Deploy to AWS

```bash
# Configure AWS credentials
aws configure

# Deploy to development environment
make deploy ENV=dev

# Deploy to production (requires approval)
make deploy ENV=prod
```

## Project Structure

```
anime-transcoding-pipeline/
├── src/
│   ├── shared/                 # Common utilities
│   │   ├── config.py           # Pydantic settings
│   │   ├── models.py           # Data models
│   │   ├── exceptions.py       # Custom exceptions
│   │   └── aws_clients.py      # Boto3 wrappers
│   ├── manifest_parser/        # Lambda: Parse XML manifests
│   ├── input_validator/        # Lambda: Validate mezzanines
│   ├── job_submitter/          # Lambda: Submit MediaConvert jobs
│   ├── output_validator/       # Lambda: Validate outputs
│   └── notification_handler/   # Lambda: Send notifications
│
├── terraform/
│   ├── modules/
│   │   ├── s3-buckets/         # Input/output storage
│   │   ├── kms-encryption/     # Customer-managed keys
│   │   ├── mediaconvert/       # Queues and IAM
│   │   ├── lambda-functions/   # All Lambdas
│   │   ├── step-functions/     # Pipeline orchestration
│   │   ├── cloudwatch-monitoring/  # Dashboards & alarms
│   │   ├── sns-notifications/  # Alert topics
│   │   ├── dynamodb/           # Idempotency tables
│   │   └── cloudfront-distribution/  # CDN delivery
│   └── environments/
│       ├── dev/
│       ├── staging/
│       └── prod/
│
├── tests/
│   ├── unit/                   # pytest + moto
│   ├── integration/            # LocalStack tests
│   └── fixtures/               # Sample data
│
├── scripts/
│   ├── setup-localstack.sh     # Initialize local AWS
│   ├── create-test-video.sh    # Generate test clips
│   └── generate-signed-url.py  # CloudFront URL tool
│
├── sample-data/
│   └── manifests/              # Sample anime manifests
│
└── docs/
    ├── architecture.md         # Detailed architecture
    └── runbook.md              # Operations guide
```

## Key Features

### 1. Anime-Focused XML Manifest

```xml
<AnimeTranscodeManifest version="1.0">
    <ManifestId>aot-s01e01-2024-001</ManifestId>
    <Episode>
        <SeriesId>attack-on-titan</SeriesId>
        <SeriesTitle>Attack on Titan</SeriesTitle>
        <SeriesTitle lang="ja">進撃の巨人</SeriesTitle>
        <SeasonNumber>1</SeasonNumber>
        <EpisodeNumber>1</EpisodeNumber>
        <EpisodeTitle>To You, in 2000 Years</EpisodeTitle>
    </Episode>
    <AudioTracks>
        <AudioTrack language="ja" default="true">Japanese</AudioTrack>
        <AudioTrack language="en">English (Funimation Dub)</AudioTrack>
    </AudioTracks>
    <!-- ... -->
</AnimeTranscodeManifest>
```

### 2. ABR Ladder Configuration

| Codec | Resolution | Bitrate | Profile | Use Case |
|-------|------------|---------|---------|----------|
| H.264 | 1920x1080 | 6.0 Mbps | High 4.2 | Desktop/TV |
| H.264 | 1280x720 | 3.5 Mbps | High 4.0 | Tablet |
| H.264 | 854x480 | 1.8 Mbps | Main 3.1 | Mobile |
| H.264 | 640x360 | 800 Kbps | Main 3.0 | Low bandwidth |
| H.265 | 1920x1080 | 4.5 Mbps | Main 4.0 | Modern devices |
| H.265 | 1280x720 | 2.5 Mbps | Main 4.0 | Modern mobile |

**Rate Control**: QVBR (Quality-Defined Variable Bitrate) at level 7 for optimal quality/size balance.

### 3. Comprehensive Validation

| Stage | Check | Action on Failure |
|-------|-------|-------------------|
| Pre-transcode | MD5 checksum | Reject, notify |
| Pre-transcode | File size match | Reject, notify |
| Pre-transcode | Resolution bounds | Reject, notify |
| Post-transcode | HLS playlist validity | Retry, then fail |
| Post-transcode | DASH MPD validity | Retry, then fail |
| Post-transcode | Duration match (±0.5s) | Warn |

### 4. CloudWatch Monitoring

- **Pipeline Dashboard**: Executions, duration, error rates
- **MediaConvert Metrics**: Jobs submitted/completed/errored
- **Lambda Metrics**: Invocations, errors, duration
- **Custom Metrics**: Validation success/failure rates

### 5. Security Best Practices

- **S3**: KMS encryption, versioning, public access blocked
- **IAM**: Least privilege, resource-specific ARNs
- **CloudFront**: Signed URLs with 24-hour expiry
- **Lambda**: Environment variable encryption
- **Audit**: CloudTrail for all operations

## Development

### Running Tests

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run with coverage report
make test-cov

# Run integration tests (requires LocalStack)
make test-integration
```

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Type checking
make typecheck
```

### Terraform Operations

```bash
# Validate terraform
make tf-validate

# Plan changes
make tf-plan ENV=dev

# Apply changes
make tf-apply ENV=dev
```

## Cost Optimization

This project is designed for **zero-cost demos**:

1. **LocalStack**: Runs all AWS services locally via Docker
2. **Moto Mocking**: Unit tests don't require AWS
3. **Mock Mode**: `MOCK_MODE=true` simulates MediaConvert
4. **On-Demand**: DynamoDB and Lambda use pay-per-request

For production estimates with real transcoding:
- ~$0.015/minute for MediaConvert (on-demand)
- ~$0.005/GB for S3 storage
- ~$0.085/GB for CloudFront transfer

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Deployment environment | `dev` |
| `MOCK_MODE` | Skip real MediaConvert calls | `false` |
| `ENABLE_H265` | Enable H.265 encoding | `true` |
| `ENABLE_DASH` | Generate DASH in addition to HLS | `true` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

### Terraform Variables

See [terraform/environments/dev/variables.tf](terraform/environments/dev/variables.tf) for all configuration options.

## API Reference

### Trigger Pipeline

Upload a manifest XML to S3:

```bash
aws s3 cp manifest.xml s3://anime-transcoding-input-dev/manifests/
```

### Generate Signed URL

```bash
python scripts/generate-signed-url.py \
    --key-pair-id APKAXXXXXXXXXX \
    --private-key-file private_key.pem \
    --url https://dxxxxxxxx.cloudfront.net/series/s01/e01/hls/master.m3u8 \
    --expires-in 86400
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS MediaConvert documentation and best practices
- [AWS Lambda Powertools](https://docs.powertools.aws.dev/lambda/python/) for observability
- LocalStack for enabling free local development
- The anime streaming community for inspiration

---

**Built with ❤️ for anime fans and video engineers**
