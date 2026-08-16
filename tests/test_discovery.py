"""Tests for the shared Bluetooth discovery helpers."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.jackery.discovery import (
    describe_bluetooth_device,
    list_visible_devices,
    looks_like_jackery_name,
)


def test_looks_like_jackery_name_matches_prefix_case_insensitively() -> None:
    assert looks_like_jackery_name("Jackery_HL1234") is True
    assert looks_like_jackery_name("jackery explorer") is True


def test_looks_like_jackery_name_rejects_unrelated_or_missing_names() -> None:
    assert looks_like_jackery_name("SomeOtherBLEGadget") is False
    assert looks_like_jackery_name(None) is False
    assert looks_like_jackery_name("") is False


def test_describe_bluetooth_device_summarizes_without_raw_advertisement_bytes() -> None:
    info = SimpleNamespace(
        address="AA:BB:CC:DD:EE:FF",
        name="Jackery_HL1234",
        rssi=-55,
        service_uuids=["0000ffff-0000-1000-8000-00805f9b34fb"],
    )

    result = describe_bluetooth_device(info)

    assert result == {
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "Jackery_HL1234",
        "rssi": -55,
        "service_uuids": ["0000ffff-0000-1000-8000-00805f9b34fb"],
        "looks_like_jackery": True,
    }


def test_list_visible_devices_excludes_given_addresses(monkeypatch) -> None:
    devices = [
        SimpleNamespace(address="AA:BB:CC:DD:EE:01", name="Jackery_HL1234", rssi=-50, service_uuids=[]),
        SimpleNamespace(address="AA:BB:CC:DD:EE:02", name="AlreadyConfigured", rssi=-60, service_uuids=[]),
    ]
    monkeypatch.setattr(
        "homeassistant.components.bluetooth.async_discovered_service_info",
        lambda *_a, **_k: devices,
    )

    result = list_visible_devices(hass=None, exclude_addresses={"AA:BB:CC:DD:EE:02"})

    assert len(result) == 1
    assert result[0]["address"] == "AA:BB:CC:DD:EE:01"


def test_list_visible_devices_logs_a_summary_at_debug(monkeypatch, caplog) -> None:
    devices = [SimpleNamespace(address="AA:BB:CC:DD:EE:01", name="Jackery_HL1234", rssi=-50, service_uuids=[])]
    monkeypatch.setattr(
        "homeassistant.components.bluetooth.async_discovered_service_info",
        lambda *_a, **_k: devices,
    )

    with caplog.at_level("DEBUG", logger="custom_components.jackery.discovery"):
        list_visible_devices(hass=None)

    assert any("Listed 1 visible" in record.message for record in caplog.records)
