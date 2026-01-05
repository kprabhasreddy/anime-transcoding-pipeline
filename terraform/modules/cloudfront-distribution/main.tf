# CloudFront Distribution Module for Anime Transcoding Pipeline
# ==============================================================
# Creates:
# - CloudFront distribution for video delivery
# - Origin Access Control for S3
# - Cache behaviors for HLS/DASH
# - CloudFront public key for signed URLs

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# Origin Access Control for S3
# -----------------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "main" {
  name                              = "${var.project_name}-oac-${var.environment}"
  description                       = "OAC for anime transcoding output bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# -----------------------------------------------------------------------------
# CloudFront Key Group for Signed URLs
# -----------------------------------------------------------------------------

# Public key for signed URL verification
resource "aws_cloudfront_public_key" "main" {
  count = var.cloudfront_public_key_pem != "" ? 1 : 0

  name        = "${var.project_name}-public-key-${var.environment}"
  comment     = "Public key for signed URL verification"
  encoded_key = var.cloudfront_public_key_pem
}

# Key group containing the public key
resource "aws_cloudfront_key_group" "main" {
  count = var.cloudfront_public_key_pem != "" ? 1 : 0

  name    = "${var.project_name}-key-group-${var.environment}"
  comment = "Key group for anime transcoding signed URLs"
  items   = [aws_cloudfront_public_key.main[0].id]
}

# -----------------------------------------------------------------------------
# Cache Policies
# -----------------------------------------------------------------------------

# Cache policy for video segments (aggressive caching)
resource "aws_cloudfront_cache_policy" "video_segments" {
  name        = "${var.project_name}-video-segments-${var.environment}"
  comment     = "Cache policy for video segments (.ts, .m4s)"
  min_ttl     = 86400     # 1 day
  default_ttl = 604800    # 7 days
  max_ttl     = 31536000  # 1 year

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# Cache policy for playlists (shorter TTL for live-like behavior)
resource "aws_cloudfront_cache_policy" "playlists" {
  name        = "${var.project_name}-playlists-${var.environment}"
  comment     = "Cache policy for HLS/DASH playlists"
  min_ttl     = 0
  default_ttl = 30    # 30 seconds
  max_ttl     = 3600  # 1 hour

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# -----------------------------------------------------------------------------
# Response Headers Policy
# -----------------------------------------------------------------------------

resource "aws_cloudfront_response_headers_policy" "streaming" {
  name    = "${var.project_name}-streaming-headers-${var.environment}"
  comment = "Response headers for video streaming"

  cors_config {
    access_control_allow_credentials = false
    access_control_max_age_sec       = 86400

    access_control_allow_headers {
      items = ["*"]
    }

    access_control_allow_methods {
      items = ["GET", "HEAD", "OPTIONS"]
    }

    access_control_allow_origins {
      items = var.cors_allowed_origins
    }

    access_control_expose_headers {
      items = ["Content-Length", "Content-Range", "Content-Type"]
    }

    origin_override = true
  }

  security_headers_config {
    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "SAMEORIGIN"
      override     = true
    }

    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
  }
}

# -----------------------------------------------------------------------------
# CloudFront Distribution
# -----------------------------------------------------------------------------

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Anime transcoding CDN - ${var.environment}"
  default_root_object = ""
  price_class         = var.price_class
  http_version        = "http2and3"

  # Custom domain (optional)
  aliases = var.domain_names

  # S3 Origin
  origin {
    domain_name              = var.output_bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
    origin_id                = "S3-${var.output_bucket_name}"
    origin_path              = ""
  }

  # Default cache behavior (for segments)
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "S3-${var.output_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.video_segments.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.streaming.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Require signed URLs if key group is configured
    trusted_key_groups = var.cloudfront_public_key_pem != "" && var.require_signed_urls ? [aws_cloudfront_key_group.main[0].id] : []
  }

  # Cache behavior for HLS playlists (.m3u8)
  ordered_cache_behavior {
    path_pattern     = "*.m3u8"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "S3-${var.output_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.playlists.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.streaming.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    trusted_key_groups = var.cloudfront_public_key_pem != "" && var.require_signed_urls ? [aws_cloudfront_key_group.main[0].id] : []
  }

  # Cache behavior for DASH manifests (.mpd)
  ordered_cache_behavior {
    path_pattern     = "*.mpd"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "S3-${var.output_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.playlists.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.streaming.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    trusted_key_groups = var.cloudfront_public_key_pem != "" && var.require_signed_urls ? [aws_cloudfront_key_group.main[0].id] : []
  }

  # Geo restrictions (optional)
  restrictions {
    geo_restriction {
      restriction_type = var.geo_restriction_type
      locations        = var.geo_restriction_locations
    }
  }

  # SSL certificate
  viewer_certificate {
    cloudfront_default_certificate = var.acm_certificate_arn == ""
    acm_certificate_arn            = var.acm_certificate_arn != "" ? var.acm_certificate_arn : null
    ssl_support_method             = var.acm_certificate_arn != "" ? "sni-only" : null
    minimum_protocol_version       = var.acm_certificate_arn != "" ? "TLSv1.2_2021" : null
  }

  # Logging (optional)
  dynamic "logging_config" {
    for_each = var.access_log_bucket != "" ? [1] : []
    content {
      bucket          = var.access_log_bucket
      prefix          = "cloudfront/${var.project_name}-${var.environment}/"
      include_cookies = false
    }
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-cdn"
    Environment = var.environment
  })
}

# -----------------------------------------------------------------------------
# S3 Bucket Policy for CloudFront OAC
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "cloudfront_oac" {
  statement {
    sid    = "AllowCloudFrontServicePrincipal"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions   = ["s3:GetObject"]
    resources = ["${var.output_bucket_arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudfront_access" {
  bucket = var.output_bucket_name
  policy = data.aws_iam_policy_document.cloudfront_oac.json
}
