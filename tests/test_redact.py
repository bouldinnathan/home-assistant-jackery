"""Tests for shared redaction helpers used by diagnostics and the crash reporter."""

from __future__ import annotations

from custom_components.jackery.redact import sanitize_data, sanitize_string


def test_sanitize_string_removes_urls() -> None:
    assert "**REDACTED**" in sanitize_string("see https://example.com/foo?token=abc for details")
    assert "example.com" not in sanitize_string("see https://example.com/foo for details")


def test_sanitize_string_removes_mac_addresses() -> None:
    result = sanitize_string("device AA:BB:CC:DD:EE:FF connected")
    assert "AA:BB:CC:DD:EE:FF" not in result


def test_sanitize_string_removes_github_tokens() -> None:
    result = sanitize_string("token=ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    assert "ghp_" not in result


def test_sanitize_string_removes_secret_assignments() -> None:
    result = sanitize_string("password: hunter2, api_key=sk-12345")
    assert "hunter2" not in result
    assert "sk-12345" not in result


def test_sanitize_data_redacts_sensitive_keys_entirely() -> None:
    data = {"github_token": "ghp_supersecrettoken1234567890", "soc": 87}
    result = sanitize_data(data)
    assert result["github_token"] == "**REDACTED**"
    assert result["soc"] == 87


def test_sanitize_data_recurses_into_nested_structures() -> None:
    data = {"entry": {"options": {"github_token": "secret-value"}}}
    result = sanitize_data(data)
    assert result["entry"]["options"]["github_token"] == "**REDACTED**"


def test_sanitize_data_recurses_into_lists() -> None:
    data = {"items": [{"password": "hunter2"}, {"soc": 50}]}
    result = sanitize_data(data)
    assert result["items"][0]["password"] == "**REDACTED**"
    assert result["items"][1]["soc"] == 50


def test_sanitize_data_passes_through_plain_values() -> None:
    assert sanitize_data(42) == 42
    assert sanitize_data(True) is True
    assert sanitize_data(None) is None
