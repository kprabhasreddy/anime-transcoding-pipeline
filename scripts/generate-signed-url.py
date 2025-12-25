#!/usr/bin/env python3
"""Generate CloudFront signed URLs for video content.

This script generates signed URLs for accessing transcoded video content
through CloudFront. Signed URLs provide time-limited, secure access to
protected content.

Usage:
    python generate-signed-url.py --key-pair-id APKAXXXX --private-key-file private_key.pem --url https://dxxxx.cloudfront.net/path/to/video.m3u8

    # With custom expiry (default is 24 hours)
    python generate-signed-url.py --key-pair-id APKAXXXX --private-key-file private_key.pem --url https://dxxxx.cloudfront.net/path/to/video.m3u8 --expires-in 3600

    # Generate wildcard policy for all variants
    python generate-signed-url.py --key-pair-id APKAXXXX --private-key-file private_key.pem --url "https://dxxxx.cloudfront.net/series/s01/e01/*" --policy wildcard
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    import base64
except ImportError:
    print("Error: cryptography package required. Install with: pip install cryptography")
    sys.exit(1)


def load_private_key(key_path: str):
    """Load RSA private key from PEM file."""
    key_file = Path(key_path)
    if not key_file.exists():
        raise FileNotFoundError(f"Private key file not found: {key_path}")

    with open(key_file, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    return private_key


def create_canned_policy(url: str, expires: datetime) -> str:
    """Create a canned policy for a specific URL.

    Canned policies are simpler and result in shorter signed URLs,
    but only work for exact URL matches.
    """
    policy = {
        "Statement": [
            {
                "Resource": url,
                "Condition": {
                    "DateLessThan": {
                        "AWS:EpochTime": int(expires.timestamp())
                    }
                }
            }
        ]
    }
    return json.dumps(policy, separators=(",", ":"))


def create_custom_policy(
    url: str,
    expires: datetime,
    ip_address: str | None = None,
    date_greater_than: datetime | None = None,
) -> str:
    """Create a custom policy with advanced conditions.

    Custom policies support:
    - Wildcard URLs (e.g., https://example.com/videos/*)
    - IP address restrictions
    - Start time restrictions (DateGreaterThan)
    """
    condition = {
        "DateLessThan": {"AWS:EpochTime": int(expires.timestamp())}
    }

    if date_greater_than:
        condition["DateGreaterThan"] = {
            "AWS:EpochTime": int(date_greater_than.timestamp())
        }

    if ip_address:
        condition["IpAddress"] = {"AWS:SourceIp": ip_address}

    policy = {
        "Statement": [
            {
                "Resource": url,
                "Condition": condition
            }
        ]
    }
    return json.dumps(policy, separators=(",", ":"))


def sign_string(private_key, message: str) -> bytes:
    """Sign a string using RSA-SHA1 (required by CloudFront)."""
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA1()  # CloudFront requires SHA1
    )
    return signature


def make_url_safe(data: bytes) -> str:
    """Convert bytes to URL-safe base64 string."""
    b64 = base64.b64encode(data).decode("utf-8")
    # Replace characters that are not URL-safe
    return b64.replace("+", "-").replace("=", "_").replace("/", "~")


def generate_signed_url_canned(
    url: str,
    key_pair_id: str,
    private_key,
    expires: datetime,
) -> str:
    """Generate a signed URL using a canned policy.

    This produces shorter URLs but only works for exact URL matches.
    """
    expires_epoch = int(expires.timestamp())

    # Create signature
    policy = create_canned_policy(url, expires)
    signature = sign_string(private_key, policy)
    signature_b64 = make_url_safe(signature)

    # Build signed URL
    separator = "&" if "?" in url else "?"
    signed_url = (
        f"{url}{separator}"
        f"Expires={expires_epoch}&"
        f"Signature={signature_b64}&"
        f"Key-Pair-Id={key_pair_id}"
    )

    return signed_url


def generate_signed_url_custom(
    url: str,
    key_pair_id: str,
    private_key,
    expires: datetime,
    ip_address: str | None = None,
    date_greater_than: datetime | None = None,
) -> str:
    """Generate a signed URL using a custom policy.

    This produces longer URLs but supports wildcards and advanced conditions.
    """
    # Create policy
    policy = create_custom_policy(url, expires, ip_address, date_greater_than)
    policy_b64 = make_url_safe(policy.encode("utf-8"))

    # Create signature
    signature = sign_string(private_key, policy)
    signature_b64 = make_url_safe(signature)

    # Build signed URL
    separator = "&" if "?" in url else "?"
    signed_url = (
        f"{url}{separator}"
        f"Policy={policy_b64}&"
        f"Signature={signature_b64}&"
        f"Key-Pair-Id={key_pair_id}"
    )

    return signed_url


def generate_signed_cookies(
    resource_url: str,
    key_pair_id: str,
    private_key,
    expires: datetime,
) -> dict[str, str]:
    """Generate signed cookies for CloudFront access.

    Signed cookies are useful when you need to provide access to
    multiple restricted files (e.g., all segments of a video).
    """
    policy = create_custom_policy(resource_url, expires)
    policy_b64 = make_url_safe(policy.encode("utf-8"))

    signature = sign_string(private_key, policy)
    signature_b64 = make_url_safe(signature)

    return {
        "CloudFront-Policy": policy_b64,
        "CloudFront-Signature": signature_b64,
        "CloudFront-Key-Pair-Id": key_pair_id,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate CloudFront signed URLs for video content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate signed URL for HLS master playlist
  %(prog)s --key-pair-id APKAXXXX --private-key-file private_key.pem \\
           --url https://dxxxx.cloudfront.net/series/s01/e01/hls/master.m3u8

  # Generate wildcard URL for all content under a path
  %(prog)s --key-pair-id APKAXXXX --private-key-file private_key.pem \\
           --url "https://dxxxx.cloudfront.net/series/s01/e01/*" --policy custom

  # Generate URL with IP restriction
  %(prog)s --key-pair-id APKAXXXX --private-key-file private_key.pem \\
           --url https://dxxxx.cloudfront.net/video.m3u8 --ip-address 192.168.1.0/24

  # Generate signed cookies
  %(prog)s --key-pair-id APKAXXXX --private-key-file private_key.pem \\
           --url "https://dxxxx.cloudfront.net/series/*" --cookies
        """
    )

    parser.add_argument(
        "--key-pair-id",
        required=True,
        help="CloudFront key pair ID (e.g., APKAXXXXXXXXXX)"
    )
    parser.add_argument(
        "--private-key-file",
        required=True,
        help="Path to RSA private key PEM file"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL to sign (use * for wildcards with custom policy)"
    )
    parser.add_argument(
        "--expires-in",
        type=int,
        default=86400,
        help="URL expiry time in seconds (default: 86400 = 24 hours)"
    )
    parser.add_argument(
        "--policy",
        choices=["canned", "custom"],
        default="canned",
        help="Policy type: canned (shorter URL) or custom (supports wildcards)"
    )
    parser.add_argument(
        "--ip-address",
        help="Restrict access to specific IP address or CIDR (requires custom policy)"
    )
    parser.add_argument(
        "--cookies",
        action="store_true",
        help="Generate signed cookies instead of signed URL"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.ip_address and args.policy == "canned":
        print("Error: IP restriction requires --policy custom")
        sys.exit(1)

    if "*" in args.url and args.policy == "canned":
        print("Warning: Wildcards require custom policy. Switching to --policy custom")
        args.policy = "custom"

    # Load private key
    try:
        private_key = load_private_key(args.private_key_file)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading private key: {e}")
        sys.exit(1)

    # Calculate expiry time
    expires = datetime.now(timezone.utc) + timedelta(seconds=args.expires_in)

    if args.cookies:
        # Generate signed cookies
        cookies = generate_signed_cookies(
            resource_url=args.url,
            key_pair_id=args.key_pair_id,
            private_key=private_key,
            expires=expires,
        )

        if args.json:
            print(json.dumps({
                "cookies": cookies,
                "expires": expires.isoformat(),
                "resource": args.url,
            }, indent=2))
        else:
            print("\nSigned Cookies:")
            print("-" * 60)
            for name, value in cookies.items():
                print(f"{name}={value}")
            print("-" * 60)
            print(f"\nExpires: {expires.isoformat()}")
            print(f"Resource: {args.url}")
            print("\nSet these cookies in the browser or HTTP client to access the content.")

    else:
        # Generate signed URL
        if args.policy == "canned":
            signed_url = generate_signed_url_canned(
                url=args.url,
                key_pair_id=args.key_pair_id,
                private_key=private_key,
                expires=expires,
            )
        else:
            signed_url = generate_signed_url_custom(
                url=args.url,
                key_pair_id=args.key_pair_id,
                private_key=private_key,
                expires=expires,
                ip_address=args.ip_address,
            )

        if args.json:
            print(json.dumps({
                "signed_url": signed_url,
                "expires": expires.isoformat(),
                "policy_type": args.policy,
            }, indent=2))
        else:
            print("\nSigned URL:")
            print("-" * 60)
            print(signed_url)
            print("-" * 60)
            print(f"\nExpires: {expires.isoformat()}")
            print(f"Policy Type: {args.policy}")
            if args.ip_address:
                print(f"IP Restriction: {args.ip_address}")


if __name__ == "__main__":
    main()
