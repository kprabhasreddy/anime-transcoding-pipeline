# Anime Transcoding Pipeline - Development Commands
# =================================================
#
# Quick reference:
#   make local    - Start LocalStack and initialize resources
#   make test     - Run all tests
#   make demo     - Run pipeline with sample manifest
#   make deploy   - Deploy to AWS (requires credentials)

.PHONY: help install dev-install local local-down init-resources test test-unit test-integration \
        lint format typecheck security demo deploy clean

# Default target
help:
	@echo "Anime Transcoding Pipeline - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install production dependencies"
	@echo "  make dev-install   Install all dependencies (including dev)"
	@echo ""
	@echo "Local Development:"
	@echo "  make local         Start LocalStack and create resources"
	@echo "  make local-down    Stop LocalStack and clean up"
	@echo "  make demo          Run pipeline with sample manifest"
	@echo ""
	@echo "Testing:"
	@echo "  make test          Run all tests with coverage"
	@echo "  make test-unit     Run unit tests only"
	@echo "  make test-integration  Run integration tests (requires LocalStack)"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          Run linters (ruff)"
	@echo "  make format        Format code (black + ruff)"
	@echo "  make typecheck     Run type checker (mypy)"
	@echo "  make security      Run security checks"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy ENV=dev    Deploy to specified environment"
	@echo "  make plan ENV=dev      Preview terraform changes"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove build artifacts and caches"

# =============================================================================
# Setup
# =============================================================================

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	pre-commit install

# =============================================================================
# Local Development
# =============================================================================

local: local-up init-resources
	@echo ""
	@echo "✅ LocalStack is running and resources are initialized"
	@echo ""
	@echo "Endpoints:"
	@echo "  - LocalStack: http://localhost:4566"
	@echo "  - DynamoDB Admin: http://localhost:8001"
	@echo ""
	@echo "Run 'make demo' to test the pipeline with a sample manifest"

local-up:
	docker-compose up -d
	@echo "Waiting for LocalStack to be healthy..."
	@until curl -s http://localhost:4566/_localstack/health | grep -q '"s3": "running"'; do \
		sleep 2; \
	done
	@echo "LocalStack is ready!"

local-down:
	docker-compose down -v

# Initialize AWS resources in LocalStack
init-resources:
	@echo "Creating S3 buckets..."
	aws --endpoint-url=http://localhost:4566 s3 mb s3://anime-transcode-input-dev 2>/dev/null || true
	aws --endpoint-url=http://localhost:4566 s3 mb s3://anime-transcode-output-dev 2>/dev/null || true

	@echo "Creating DynamoDB table..."
	aws --endpoint-url=http://localhost:4566 dynamodb create-table \
		--table-name anime-transcode-idempotency \
		--attribute-definitions AttributeName=idempotency_token,AttributeType=S \
		--key-schema AttributeName=idempotency_token,KeyType=HASH \
		--billing-mode PAY_PER_REQUEST \
		2>/dev/null || true

	@echo "Creating SNS topics..."
	aws --endpoint-url=http://localhost:4566 sns create-topic --name anime-transcode-success 2>/dev/null || true
	aws --endpoint-url=http://localhost:4566 sns create-topic --name anime-transcode-errors 2>/dev/null || true

	@echo "Creating KMS key..."
	aws --endpoint-url=http://localhost:4566 kms create-key --description "Anime transcode encryption key" 2>/dev/null || true

	@echo "Resources initialized!"

# =============================================================================
# Testing
# =============================================================================

test:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-unit:
	pytest tests/unit/ -v -m "not integration and not e2e"

test-integration:
	pytest tests/integration/ -v -m "integration"

test-e2e:
	pytest tests/e2e/ -v -m "e2e"

test-fast:
	pytest tests/unit/ -v -x --tb=short

# =============================================================================
# Code Quality
# =============================================================================

lint:
	ruff check src/ tests/

format:
	black src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy src/

security:
	pip-audit
	bandit -r src/ -ll

quality: format lint typecheck
	@echo "All quality checks passed!"

# =============================================================================
# Demo
# =============================================================================

demo: check-localstack
	@echo "Uploading sample manifest to trigger pipeline..."
	aws --endpoint-url=http://localhost:4566 s3 cp \
		sample-data/manifests/attack-on-titan-s1e1.xml \
		s3://anime-transcode-input-dev/manifests/
	@echo ""
	@echo "Manifest uploaded! Check CloudWatch logs for processing status."
	@echo "View DynamoDB: http://localhost:8001"

check-localstack:
	@curl -s http://localhost:4566/_localstack/health > /dev/null || \
		(echo "❌ LocalStack is not running. Run 'make local' first." && exit 1)

# =============================================================================
# Deployment
# =============================================================================

ENV ?= dev

deploy: validate-env
	cd terraform/environments/$(ENV) && \
		terraform init && \
		terraform apply -auto-approve

plan: validate-env
	cd terraform/environments/$(ENV) && \
		terraform init && \
		terraform plan

destroy: validate-env
	@echo "⚠️  This will destroy all resources in $(ENV)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	cd terraform/environments/$(ENV) && \
		terraform destroy

validate-env:
	@if [ ! -d "terraform/environments/$(ENV)" ]; then \
		echo "❌ Invalid environment: $(ENV)"; \
		echo "Valid environments: dev, staging, prod"; \
		exit 1; \
	fi

# =============================================================================
# Cleanup
# =============================================================================

clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf coverage_html
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf *.egg-info
	rm -rf build/
	rm -rf dist/
	rm -rf volume/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# =============================================================================
# Utilities
# =============================================================================

# Generate a 5-second test video clip using FFmpeg
create-test-video:
	./scripts/create-test-video.sh

# Generate CloudFront signed URL for a transcoded asset
signed-url:
	python scripts/generate-signed-url.py

# Show project structure
tree:
	@tree -I '__pycache__|*.egg-info|.git|.pytest_cache|.mypy_cache|volume|htmlcov|coverage_html' -a
