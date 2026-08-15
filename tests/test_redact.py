"""Tests for shared redaction helpers used by diagnostics and the crash reporter."""

from __future__ import annotations

import logging

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


def test_sanitize_string_removes_ipv4_addresses() -> None:
    result = sanitize_string("device at 192.168.1.42 responded")
    assert "192.168.1.42" not in result
    assert "**REDACTED**" in result


def test_sanitize_string_removes_email_addresses() -> None:
    result = sanitize_string("contact user@example.com for support")
    assert "user@example.com" not in result


def test_sanitize_string_removes_long_hex_strings() -> None:
    result = sanitize_string("session id abcdef0123456789abcdef01 in use")
    assert "abcdef0123456789abcdef01" not in result


def test_sanitize_string_leaves_ordinary_text_untouched() -> None:
    assert sanitize_string("Battery at 87 percent, charging") == "Battery at 87 percent, charging"


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


def test_sanitize_data_redacts_keys_that_contain_a_sensitive_word() -> None:
    # _is_sensitive_key matches on whole underscore-separated words, so a
    # compound key like "user_email" or "device_password" is still caught.
    data = {"user_email": "person@example.com", "device_password": "hunter2", "soc": 87}
    result = sanitize_data(data)
    assert result["user_email"] == "**REDACTED**"
    assert result["device_password"] == "**REDACTED**"
    assert result["soc"] == 87


def test_sanitize_data_stringifies_non_string_keys() -> None:
    result = sanitize_data({1: "one"})
    assert result == {"1": "one"}


def test_sanitize_data_converts_sets_and_tuples_to_lists() -> None:
    assert sanitize_data((1, 2, 3)) == [1, 2, 3]
    assert sorted(sanitize_data({1, 2, 3})) == [1, 2, 3]


def test_sanitize_data_summarizes_bytes_without_leaking_content() -> None:
    result = sanitize_data(b"secret-binary-payload")
    assert result == {"type": "bytes", "length": 21}


def test_sanitize_data_serializes_datetime_as_utc_isoformat() -> None:
    from datetime import UTC, datetime

    result = sanitize_data(datetime(2026, 1, 1, tzinfo=UTC))
    assert result == "2026-01-01T00:00:00+00:00"


def test_sanitize_data_stops_recursing_past_max_depth() -> None:
    nested: dict = {}
    cursor = nested
    for _ in range(20):
        cursor["child"] = {}
        cursor = cursor["child"]

    result = sanitize_data(nested)
    # Walk down until we hit the depth-limit sentinel instead of another dict.
    cursor = result
    depths = 0
    while isinstance(cursor, dict) and "child" in cursor:
        cursor = cursor["child"]
        depths += 1
    assert cursor == "<max depth reached>"
    assert depths <= 13


def test_sanitize_string_logs_only_when_it_actually_redacts_something(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="custom_components.jackery.redact"):
        sanitize_string("Battery at 87 percent")
        assert not caplog.records

        sanitize_string("contact user@example.com")
        assert any("Redacted sensitive content" in record.message for record in caplog.records)


def test_sanitize_data_logs_sensitive_key_redaction(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="custom_components.jackery.redact"):
        sanitize_data({"github_token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"})

    assert any("Redacting value for sensitive key" in record.message for record in caplog.records)
