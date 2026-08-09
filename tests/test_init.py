"""Tests for config entry setup/unload and the jackery.* services."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jackery.const import (
    ATTR_COMMAND,
    ATTR_DEVICE_ID,
    CONF_BLE_ADDRESS,
    DOMAIN,
    SERVICE_REFRESH,
    SERVICE_SEND_RAW_COMMAND,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture(autouse=True)
def _mock_ble_layer(monkeypatch):
    """Make BLE polling succeed instantly with one field, so entities/devices get created."""
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        "custom_components.jackery.ble_client.JackeryBLEClient.async_run_session",
        AsyncMock(return_value=[{"soc": 50}]),
    )


async def _setup_entry(hass, *, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BLE_ADDRESS: ADDRESS},
        options=options or {},
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_entry_stores_coordinator_and_forwards_platforms(hass) -> None:
    entry = await _setup_entry(hass)
    assert entry.entry_id in hass.data[DOMAIN]


async def test_unload_entry_removes_coordinator(hass) -> None:
    entry = await _setup_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_setup_with_incomplete_github_reporting_config_does_not_fail(hass) -> None:
    # repo/token missing even though enabled: __init__ should warn and disable,
    # not crash setup.
    entry = await _setup_entry(hass, options={"github_reporting_enabled": True})
    assert entry.entry_id in hass.data[DOMAIN]


async def test_refresh_service_calls_coordinator_refresh(hass) -> None:
    entry = await _setup_entry(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_request_refresh = AsyncMock()

    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)

    coordinator.async_request_refresh.assert_awaited_once()


async def test_send_raw_command_service_parses_json_string_and_fires_event(hass) -> None:
    entry = await _setup_entry(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_send_raw_command = AsyncMock(return_value=[{"ok": True}])

    events = []
    hass.bus.async_listen("jackery_raw_command_response", lambda event: events.append(event))

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        {ATTR_COMMAND: json.dumps({"cmd": "data_get"})},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    coordinator.async_send_raw_command.assert_awaited_once_with({"cmd": "data_get"})
    assert result["frames"] == [{"ok": True}]
    assert len(events) == 1
    assert events[0].data["frames"] == [{"ok": True}]


async def test_send_raw_command_service_accepts_a_dict_directly(hass) -> None:
    entry = await _setup_entry(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_send_raw_command = AsyncMock(return_value=[{"ok": True}])

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        {ATTR_COMMAND: {"cmd": "data_get"}},
        blocking=True,
        return_response=True,
    )

    coordinator.async_send_raw_command.assert_awaited_once_with({"cmd": "data_get"})
    assert result["frames"] == [{"ok": True}]


async def test_send_raw_command_rejects_non_json_string(hass) -> None:
    await _setup_entry(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_RAW_COMMAND,
            {ATTR_COMMAND: "not json"},
            blocking=True,
        )


async def test_services_require_device_id_when_multiple_entries_configured(hass) -> None:
    await _setup_entry(hass)
    second = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BLE_ADDRESS: "11:22:33:44:55:66"},
        unique_id="11:22:33:44:55:66",
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)


async def test_services_use_device_id_to_pick_the_right_coordinator(hass) -> None:
    first = await _setup_entry(hass)
    second = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BLE_ADDRESS: "11:22:33:44:55:66"},
        unique_id="11:22:33:44:55:66",
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    first_coordinator = hass.data[DOMAIN][first.entry_id]
    first_coordinator.async_request_refresh = AsyncMock()
    second_coordinator = hass.data[DOMAIN][second.entry_id]
    second_coordinator.async_request_refresh = AsyncMock()

    device_registry = dr.async_get(hass)
    device = next(
        d for d in device_registry.devices.values() if first.entry_id in d.config_entries
    )

    await hass.services.async_call(
        DOMAIN, SERVICE_REFRESH, {ATTR_DEVICE_ID: device.id}, blocking=True
    )

    first_coordinator.async_request_refresh.assert_awaited_once()
    second_coordinator.async_request_refresh.assert_not_called()


async def test_no_configured_devices_raises_clear_error(hass) -> None:
    # Set up once (so the service gets registered), then unload it, leaving
    # the service present but no coordinator for it to act on.
    entry = await _setup_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError, match="No Jackery device is configured"):
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)


async def test_unknown_device_id_raises_clear_error(hass) -> None:
    await _setup_entry(hass)

    with pytest.raises(HomeAssistantError, match="No Jackery device found"):
        await hass.services.async_call(
            DOMAIN, SERVICE_REFRESH, {ATTR_DEVICE_ID: "does-not-exist"}, blocking=True
        )


async def test_changing_options_reloads_the_config_entry(hass) -> None:
    entry = await _setup_entry(hass)
    first_coordinator = hass.data[DOMAIN][entry.entry_id]

    hass.config_entries.async_update_entry(entry, options={"scan_interval": 60})
    await hass.async_block_till_done()

    assert hass.data[DOMAIN][entry.entry_id] is not first_coordinator
    assert hass.data[DOMAIN][entry.entry_id].update_interval.total_seconds() == 60
