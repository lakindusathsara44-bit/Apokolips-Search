import pytest

from app.crawler.safety import (
    UnsafeTargetError,
    normalize_url,
    validate_resolved_addresses,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.COM/path#section", "https://example.com/path"),
        ("http://example.com:80", "http://example.com/"),
        ("https://example.com:443/search?q=abc", "https://example.com/search?q=abc"),
    ],
)
def test_normalize_public_web_urls(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected

@pytest.mark.parametrize(
    "raw",
    [
        "file:///etc/passwd", "ftp://example.com/file", "http://127.0.0.1/",
        "http://10.0.0.1/", "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/", "http://localhost/", "http://printer.local/",
        "http://user:password@example.com/", "http://example.com:8080/",
        "https://example.com:444/",
    ],
)
def test_reject_unsafe_urls(raw: str) -> None:
    with pytest.raises(UnsafeTargetError):
        normalize_url(raw)

def test_reject_mixed_public_and_private_dns_answers() -> None:
    records = [{"host": "1.1.1.1"}, {"host": "192.168.1.10"}]
    with pytest.raises(UnsafeTargetError):
        validate_resolved_addresses(records)

def test_reject_empty_dns_answers() -> None:
    with pytest.raises(UnsafeTargetError):
        validate_resolved_addresses([])
