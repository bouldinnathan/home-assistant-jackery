"""Shared redaction helpers for diagnostics and GitHub crash reports.

Both consumers need the same guarantee: nothing that identifies the user's
hardware, network, or credentials leaves the device. Centralizing the regexes
here means a new sensitive pattern only needs to be taught once.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_REDACTED = "**REDACTED**"

_SENSITIVE_KEYS = {
    "address",
    "adapter_address",
    "api_key",
    "authorization",
    "ble_address",
    "bluetooth_address",
    "client_secret",
    "credential",
    "credentials",
    "device_id",
    "email",
    "entry_id",
    "github_token",
    "host",
    "hostname",
    "ip_address",
    "mac",
    "password",
    "passphrase",
    "pin",
    "private_key",
    "secret",
    "secret_key",
    "serial",
    "ssid",
    "token",
    "unique_id",
    "wifi_password",
}

_URL_RE = re.compile(r"(?i)\b(?:https?|ws|wss)://[^\s]+")
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_MAC_RE = re.compile(r"(?i)\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|authorization|password|passphrase|pin|secret|token)\s*[:=]\s*[^\s,;]+"
)
_GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")
_LONG_HEX_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    if normalized in _SENSITIVE_KEYS:
        return True
    words = set(normalized.split("_"))
    return bool(words & {"address", "credential", "credentials", "email", "password", "secret", "token"})


def sanitize_string(value: str) -> str:
    """Strip URLs, IPs, MACs, emails, and credential-shaped substrings."""
    sanitized = value
    for pattern in (
        _GITHUB_TOKEN_RE,
        _SECRET_ASSIGNMENT_RE,
        _URL_RE,
        _IPV4_RE,
        _MAC_RE,
        _EMAIL_RE,
        _LONG_HEX_RE,
    ):
        sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def sanitize_data(value: Any, *, depth: int = 0) -> Any:
    """Recursively return a JSON-safe, redacted copy of ``value``."""
    if depth > 12:
        return "<max depth reached>"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                result[key] = _REDACTED
                continue
            result[sanitize_string(key)] = sanitize_data(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_data(item, depth=depth + 1) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, str):
        return sanitize_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, bytes):
        return {"type": "bytes", "length": len(value)}
    return f"<{type(value).__name__}>"
