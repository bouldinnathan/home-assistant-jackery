"""End-to-end entity tests: dynamic discovery and the switch write path.

These go through the real entity platforms (not just the coordinator), to
confirm that whatever fields a device reports actually turn into working
Home Assistant states, and that flipping a switch calls through to the BLE
write path. Entities are looked up by unique_id via the entity registry
rather than by guessing generated entity_id slugs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jackery.const import CONF_BLE_ADDRESS, DOMAIN

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def mock_ble_poll(monkeypatch):
    """Patch the BLE layer; returns the AsyncMock so a test can set its return value."""
    run_session = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        "custom_components.jackery.ble_client.JackeryBLEClient.async_run_session",
        run_session,
    )
    return run_session


async def _setup_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id_for(hass, entry: MockConfigEntry, unique_suffix: str) -> str | None:
    registry = er.async_get(hass)
    target = f"{ADDRESS}_{unique_suffix}"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id == target:
            return entity.entity_id
    return None


async def test_numeric_field_becomes_a_sensor_with_correct_state(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"soc": 87, "outputWatts": 120}]
    entry = await _setup_entry(hass)

    soc_entity_id = _entity_id_for(hass, entry, "sensor_soc")
    assert soc_entity_id is not None
    assert hass.states.get(soc_entity_id).state == "87"

    watts_entity_id = _entity_id_for(hass, entry, "sensor_outputWatts")
    assert watts_entity_id is not None
    watts_state = hass.states.get(watts_entity_id)
    assert watts_state.state == "120"
    assert watts_state.attributes["unit_of_measurement"] == "W"


async def test_boolean_output_field_becomes_a_switch(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"acOutput": True}]
    entry = await _setup_entry(hass)

    entity_id = _entity_id_for(hass, entry, "switch_acOutput")
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "on"


async def test_boolean_non_output_field_becomes_a_read_only_binary_sensor(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"chargingFault": False}]
    entry = await _setup_entry(hass)

    assert _entity_id_for(hass, entry, "binary_chargingFault") is not None
    assert _entity_id_for(hass, entry, "switch_chargingFault") is None


async def test_turning_on_switch_calls_the_ble_write_path(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"acOutput": False}]
    entry = await _setup_entry(hass)
    entity_id = _entity_id_for(hass, entry, "switch_acOutput")
    assert hass.states.get(entity_id).state == "off"

    mock_ble_poll.reset_mock()
    mock_ble_poll.return_value = []

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()

    # First call is the write itself; a second (poll) call follows from the
    # coordinator's post-write refresh, so check the first call specifically.
    mock_ble_poll.assert_awaited()
    first_call_commands = mock_ble_poll.await_args_list[0].args[1]
    assert first_call_commands == [{"cmd": "data_set", "data": {"acOutput": True}}]
    assert hass.states.get(entity_id).state == "on"


async def test_turning_off_switch_calls_the_ble_write_path(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"acOutput": True}]
    entry = await _setup_entry(hass)
    entity_id = _entity_id_for(hass, entry, "switch_acOutput")
    assert hass.states.get(entity_id).state == "on"

    mock_ble_poll.reset_mock()
    mock_ble_poll.return_value = []

    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()

    first_call_commands = mock_ble_poll.await_args_list[0].args[1]
    assert first_call_commands == [{"cmd": "data_set", "data": {"acOutput": False}}]
    assert hass.states.get(entity_id).state == "off"


async def test_device_info_reflects_identified_model_and_firmware(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"soc": 87, "deviceModel": "Explorer 2000 Plus", "fwVersion": "1.2.3"}]
    entry = await _setup_entry(hass)

    device_registry = dr.async_get(hass)
    device = next(d for d in device_registry.devices.values() if entry.entry_id in d.config_entries)

    assert device.manufacturer == "Jackery"
    assert device.model == "Explorer 2000 Plus"
    assert device.sw_version == "1.2.3"
    assert (CONNECTION_BLUETOOTH, ADDRESS) in device.connections


async def test_new_fields_on_a_later_poll_add_new_entities(hass, mock_ble_poll) -> None:
    mock_ble_poll.return_value = [{"soc": 50}]
    entry = await _setup_entry(hass)
    assert _entity_id_for(hass, entry, "sensor_cellTemp") is None

    mock_ble_poll.return_value = [{"soc": 51, "cellTemp": 25}]
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()

    entity_id = _entity_id_for(hass, entry, "sensor_cellTemp")
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "25"
