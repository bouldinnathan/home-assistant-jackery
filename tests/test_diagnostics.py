"""Tests for redacted diagnostics output."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jackery.const import CONF_BLE_ADDRESS, DOMAIN
from custom_components.jackery.diagnostics import async_get_config_entry_diagnostics

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture(autouse=True)
def _mock_ble_layer(monkeypatch):
    monkeypatch.setattr(
        "custom_components.jackery.coordinator.bluetooth.async_ble_device_from_address",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        "custom_components.jackery.ble_client.JackeryBLEClient.async_run_session",
        AsyncMock(return_value=[{"soc": 87, "sn": "SERIAL12345"}]),
    )


async def test_diagnostics_redacts_github_token_and_omits_address(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_BLE_ADDRESS: ADDRESS},
        options={"github_reporting_enabled": True, "github_repo": "o/r", "github_token": "ghp_secretvalue123456"},
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_options"]["github_token"] == "**REDACTED**"
    assert ADDRESS not in str(diagnostics)
    assert diagnostics["telemetry"]["connected"] is True
    assert diagnostics["telemetry"]["field_count"] == 2


async def test_diagnostics_handle_unloaded_entry_gracefully(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)
    # Entry deliberately not set up: coordinator absent from hass.data.

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["coordinator"]["loaded"] is False
    assert diagnostics["telemetry"]["connected"] is None


async def test_diagnostics_generation_is_logged_at_debug(hass, caplog) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with caplog.at_level("DEBUG", logger="custom_components.jackery.diagnostics"):
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["telemetry"]["field_count"] == 2
    messages = [record.message for record in caplog.records]
    assert any("Generating diagnostics" in message for message in messages)
    assert any("ready" in message for message in messages)
