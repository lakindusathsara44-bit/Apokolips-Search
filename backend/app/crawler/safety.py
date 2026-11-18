"""URL validation and public-address checks used by every outbound request."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit

class UnsafeTargetError(ValueError):
    """Raised when a URL could target a non-public or unsupported destination."""

_BLOCKED_SUFFIXES = (
    ".localhost", ".local", ".internal", ".home", ".lan",
    ".test", ".invalid", ".example",
)
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}

def normalize_url(raw_url: str) -> str:
    """Return a normalized HTTP(S) URL or reject unsafe/non-web destinations."""
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > 2048:
        raise UnsafeTargetError("URL must contain 1–2048 characters")
    if any(ord(char) < 32 for char in raw_url):
        raise UnsafeTargetError("URL contains control characters")
    try:
        parts = urlsplit(raw_url.strip())
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"}:
            raise UnsafeTargetError("Only HTTP and HTTPS URLs are supported")
        if parts.username is not None or parts.password is not None:
            raise UnsafeTargetError("URLs containing credentials are not allowed")
        if not parts.hostname:
            raise UnsafeTargetError("URL must include a hostname")
        hostname = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parts.port
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, UnsafeTargetError):
            raise
        raise UnsafeTargetError("URL is malformed") from exc

    if not hostname or hostname in _BLOCKED_HOSTS or hostname.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeTargetError("Local and reserved hostnames are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise UnsafeTargetError("IP address is not globally routable")

    expected_port = 80 if scheme == "http" else 443
    if port is not None and port != expected_port:
        raise UnsafeTargetError("Only the standard HTTP and HTTPS ports are allowed")
    authority = f"[{hostname}]" if ":" in hostname else hostname
    return urlunsplit((scheme, authority, parts.path or "/", parts.query, ""))

def validate_resolved_addresses(records: list[dict]) -> None:
    """Reject a DNS answer if any returned address is not globally routable."""
    if not records:
        raise UnsafeTargetError("Hostname did not resolve to a public address")
    for record in records:
        raw_address = str(record.get("host", "")).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise UnsafeTargetError("DNS returned an invalid IP address") from exc
        if not address.is_global:
            raise UnsafeTargetError("DNS resolved to a non-public IP address")
