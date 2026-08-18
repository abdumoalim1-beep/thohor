import pytest

from app.crawler.security import UnsafeURLError, validate_url


def test_blocks_localhost():
    with pytest.raises(UnsafeURLError):
        validate_url("http://localhost:8000/")


def test_blocks_loopback_ip():
    with pytest.raises(UnsafeURLError):
        validate_url("http://127.0.0.1/")


def test_blocks_private_ip_range():
    with pytest.raises(UnsafeURLError):
        validate_url("http://192.168.1.10/")


def test_blocks_cloud_metadata_endpoint():
    with pytest.raises(UnsafeURLError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_blocks_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        validate_url("file:///etc/passwd")


def test_allows_public_ip_literal():
    # IP literal — getaddrinfo resolves it without a DNS lookup, keeping
    # this test hermetic (no network dependency in the unit suite).
    validate_url("https://8.8.8.8/")  # should not raise
