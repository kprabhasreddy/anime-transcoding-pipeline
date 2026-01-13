#!/bin/bash
# Setup LocalStack for local development
# ======================================
# This script initializes LocalStack with the required AWS resources
# for running the transcoding pipeline locally without AWS costs.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Anime Transcoding Pipeline - LocalStack Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# Configuration
PROJECT_NAME="anime-transcoding"
ENVIRONMENT="local"
REGION="us-east-1"
LOCALSTACK_ENDPOINT="http://localhost:4566"

# Check if LocalStack is running
echo -e "\n${YELLOW}Checking LocalStack status...${NC}"
if ! curl -s "${LOCALSTACK_ENDPOINT}/_localstack/health" > /dev/null 2>&1; then
    echo -e "${RED}Error: LocalStack is not running!${NC}"
    echo "Please start LocalStack with: docker-compose up -d"
    exit 1
fi
echo -e "${GREEN}LocalStack is running${NC}"

# Configure AWS CLI for LocalStack
export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="${REGION}"

# Helper function for AWS CLI with LocalStack
awslocal() {
    aws --endpoint-url="${LOCALSTACK_ENDPOINT}" "$@"
}

# -----------------------------------------------------------------------------
# Create S3 Buckets
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}Creating S3 buckets...${NC}"

# Input bucket
awslocal s3 mb "s3://${PROJECT_NAME}-input-${ENVIRONMENT}" 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-input-${ENVIRONMENT}"

# Output bucket
awslocal s3 mb "s3://${PROJECT_NAME}-output-${ENVIRONMENT}" 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-output-${ENVIRONMENT}"

# Enable versioning on input bucket
awslocal s3api put-bucket-versioning \
    --bucket "${PROJECT_NAME}-input-${ENVIRONMENT}" \
    --versioning-configuration Status=Enabled

echo -e "${GREEN}S3 buckets created${NC}"

# -----------------------------------------------------------------------------
# Create DynamoDB Tables
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}Creating DynamoDB tables...${NC}"

# Idempotency table
awslocal dynamodb create-table \
    --table-name "${PROJECT_NAME}-idempotency-${ENVIRONMENT}" \
    --attribute-definitions \
        AttributeName=idempotency_token,AttributeType=S \
        AttributeName=manifest_id,AttributeType=S \
        AttributeName=created_at,AttributeType=S \
    --key-schema \
        AttributeName=idempotency_token,KeyType=HASH \
    --global-secondary-indexes \
        "[{\"IndexName\": \"manifest-id-index\", \"KeySchema\": [{\"AttributeName\": \"manifest_id\", \"KeyType\": \"HASH\"}, {\"AttributeName\": \"created_at\", \"KeyType\": \"RANGE\"}], \"Projection\": {\"ProjectionType\": \"ALL\"}}]" \
    --billing-mode PAY_PER_REQUEST \
    2>/dev/null || echo "  Table already exists"
echo "  Created: ${PROJECT_NAME}-idempotency-${ENVIRONMENT}"

# Job status table
awslocal dynamodb create-table \
    --table-name "${PROJECT_NAME}-job-status-${ENVIRONMENT}" \
    --attribute-definitions \
        AttributeName=job_id,AttributeType=S \
        AttributeName=manifest_id,AttributeType=S \
        AttributeName=status,AttributeType=S \
    --key-schema \
        AttributeName=job_id,KeyType=HASH \
    --global-secondary-indexes \
        "[{\"IndexName\": \"manifest-id-index\", \"KeySchema\": [{\"AttributeName\": \"manifest_id\", \"KeyType\": \"HASH\"}], \"Projection\": {\"ProjectionType\": \"ALL\"}}, {\"IndexName\": \"status-index\", \"KeySchema\": [{\"AttributeName\": \"status\", \"KeyType\": \"HASH\"}], \"Projection\": {\"ProjectionType\": \"KEYS_ONLY\"}}]" \
    --billing-mode PAY_PER_REQUEST \
    2>/dev/null || echo "  Table already exists"
echo "  Created: ${PROJECT_NAME}-job-status-${ENVIRONMENT}"

echo -e "${GREEN}DynamoDB tables created${NC}"

# -----------------------------------------------------------------------------
# Create SNS Topics
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}Creating SNS topics...${NC}"

awslocal sns create-topic --name "${PROJECT_NAME}-success-${ENVIRONMENT}" 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-success-${ENVIRONMENT}"

awslocal sns create-topic --name "${PROJECT_NAME}-error-${ENVIRONMENT}" 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-error-${ENVIRONMENT}"

awslocal sns create-topic --name "${PROJECT_NAME}-alarms-${ENVIRONMENT}" 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-alarms-${ENVIRONMENT}"

echo -e "${GREEN}SNS topics created${NC}"

# -----------------------------------------------------------------------------
# Create SQS Queue (for testing)
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}Creating SQS queues...${NC}"

awslocal sqs create-queue --queue-name "${PROJECT_NAME}-test-queue-${ENVIRONMENT}" 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-test-queue-${ENVIRONMENT}"

echo -e "${GREEN}SQS queues created${NC}"

# -----------------------------------------------------------------------------
# Upload Sample Data
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}Uploading sample data...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

# Upload sample manifest if it exists
if [ -f "${PROJECT_ROOT}/sample-data/manifests/attack-on-titan-s1e1.xml" ]; then
    awslocal s3 cp \
        "${PROJECT_ROOT}/sample-data/manifests/attack-on-titan-s1e1.xml" \
        "s3://${PROJECT_NAME}-input-${ENVIRONMENT}/manifests/"
    echo "  Uploaded: attack-on-titan-s1e1.xml"
fi

echo -e "${GREEN}Sample data uploaded${NC}"

# -----------------------------------------------------------------------------
# Create IAM Roles (mock)
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}Creating IAM roles...${NC}"

# Lambda execution role
awslocal iam create-role \
    --role-name "${PROJECT_NAME}-lambda-execution-${ENVIRONMENT}" \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-lambda-execution-${ENVIRONMENT}"

# MediaConvert role
awslocal iam create-role \
    --role-name "${PROJECT_NAME}-mediaconvert-${ENVIRONMENT}" \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "mediaconvert.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' 2>/dev/null || true
echo "  Created: ${PROJECT_NAME}-mediaconvert-${ENVIRONMENT}"

echo -e "${GREEN}IAM roles created${NC}"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}LocalStack Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Resources created:"
echo "  S3 Buckets:"
echo "    - ${PROJECT_NAME}-input-${ENVIRONMENT}"
echo "    - ${PROJECT_NAME}-output-${ENVIRONMENT}"
echo ""
echo "  DynamoDB Tables:"
echo "    - ${PROJECT_NAME}-idempotency-${ENVIRONMENT}"
echo "    - ${PROJECT_NAME}-job-status-${ENVIRONMENT}"
echo ""
echo "  SNS Topics:"
echo "    - ${PROJECT_NAME}-success-${ENVIRONMENT}"
echo "    - ${PROJECT_NAME}-error-${ENVIRONMENT}"
echo "    - ${PROJECT_NAME}-alarms-${ENVIRONMENT}"
echo ""
echo "Environment variables for local testing:"
echo "  export AWS_ENDPOINT_URL=${LOCALSTACK_ENDPOINT}"
echo "  export AWS_ACCESS_KEY_ID=test"
echo "  export AWS_SECRET_ACCESS_KEY=test"
echo "  export AWS_DEFAULT_REGION=${REGION}"
echo "  export ENVIRONMENT=${ENVIRONMENT}"
echo "  export MOCK_MODE=true"
echo ""
echo "To trigger the pipeline locally:"
echo "  aws --endpoint-url=${LOCALSTACK_ENDPOINT} s3 cp sample-manifest.xml s3://${PROJECT_NAME}-input-${ENVIRONMENT}/manifests/"
