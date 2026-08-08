"""Tests for JackeryCoordinator, especially the expected-vs-unexpected error boundary.

The most important behavior here: routine BLE/Bluetooth failures must never
reach the (opt-in) GitHub crash reporter, only genuine unexpected exceptions
should. Getting this wrong would mean every user's Bluetooth flakiness spams
the maintainer's issue tracker.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jackery.ble_client import JackeryConnectionError
from custom_components.jackery.const import CONF_BLE_ADDRESS, DOMAIN
from custom_components.jackery.coordinator import JackeryCoordinator

ADDRESS = "AA:BB:CC:DD:EE:FF"


def _make_entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, options={})


@pytest.fixture
def error_reporter():
    return AsyncMock()


@pytest.fixture
def coordinator(hass, error_reporter) -> JackeryCoordinator:
    entry = _make_entry()
    entry.add_to_hass(hass)
    return JackeryCoordinator(hass, entry, error_reporter=error_reporter)


async def test_successful_poll_merges_frames_and_marks_connected(hass, coordinator, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        coordinator._client,
        "async_run_session",
        AsyncMock(return_value=[{"soc": 87}, {"outputWatts": 45}]),
    )

    telemetry = await coordinator._async_update_data()

    assert telemetry.connected is True
    assert telemetry.fields == {"soc": 87, "outputWatts": 45}


async def test_device_not_visible_raises_update_failed_without_reporting(
    hass, coordinator, error_reporter, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: None,
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator.telemetry.connected is False
    error_reporter.assert_not_called()


async def test_expected_ble_error_raises_update_failed_without_reporting(
    hass, coordinator, error_reporter, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        coordinator._client,
        "async_run_session",
        AsyncMock(side_effect=JackeryConnectionError("could not connect")),
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator.telemetry.connected is False
    error_reporter.assert_not_called()


async def test_unexpected_error_raises_update_failed_and_reports_it(
    hass, coordinator, error_reporter, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    bug = ValueError("a genuine integration bug")
    monkeypatch.setattr(coordinator._client, "async_run_session", AsyncMock(side_effect=bug))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    error_reporter.assert_awaited_once_with(bug, "poll")


async def test_reporter_failure_does_not_propagate(hass, coordinator, error_reporter, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(coordinator._client, "async_run_session", AsyncMock(side_effect=ValueError("bug")))
    error_reporter.side_effect = RuntimeError("GitHub API is down")

    # Must still surface as UpdateFailed, not the reporter's own RuntimeError.
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_write_field_optimistically_updates_then_refreshes(hass, coordinator, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(coordinator._client, "async_run_session", AsyncMock(return_value=[]))
    monkeypatch.setattr(coordinator, "async_request_refresh", AsyncMock())

    await coordinator.async_write_field("port.acOutput", True)

    assert coordinator.telemetry.fields["port.acOutput"] is True
    coordinator.async_request_refresh.assert_awaited_once()


async def test_write_field_expected_error_propagates_without_reporting(
    hass, coordinator, error_reporter, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        coordinator._client,
        "async_run_session",
        AsyncMock(side_effect=JackeryConnectionError("no answer")),
    )

    with pytest.raises(JackeryConnectionError):
        await coordinator.async_write_field("port.acOutput", True)

    assert "port.acOutput" not in coordinator.telemetry.fields
    error_reporter.assert_not_called()


async def test_write_field_unexpected_error_is_reported_and_reraised(
    hass, coordinator, error_reporter, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    bug = KeyError("unexpected shape")
    monkeypatch.setattr(coordinator._client, "async_run_session", AsyncMock(side_effect=bug))

    with pytest.raises(KeyError):
        await coordinator.async_write_field("port.acOutput", True)

    error_reporter.assert_awaited_once_with(bug, "write")


async def test_send_raw_command_merges_response_frames(hass, coordinator, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        coordinator._client,
        "async_run_session",
        AsyncMock(return_value=[{"customField": 123}]),
    )

    frames = await coordinator.async_send_raw_command({"cmd": "custom"})

    assert frames == [{"customField": 123}]
    assert coordinator.telemetry.fields["customField"] == 123
