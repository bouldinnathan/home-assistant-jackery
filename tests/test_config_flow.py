"""Tests for the Jackery config and options flows, driven through the real FlowManager."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jackery.const import CONF_BLE_ADDRESS, DOMAIN

ADDRESS = "AA:BB:CC:DD:EE:FF"


async def test_user_step_shows_manual_text_field_when_nothing_discovered(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.config_flow.async_discovered_service_info",
        lambda *_a, **_k: [],
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry_for_manually_entered_address(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.jackery.config_flow.async_discovered_service_info",
        lambda *_a, **_k: [],
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BLE_ADDRESS: ADDRESS}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BLE_ADDRESS] == ADDRESS


async def test_user_step_offers_discovered_jackery_devices(hass, monkeypatch) -> None:
    discovered = SimpleNamespace(address=ADDRESS, name="Jackery_HL1234")
    monkeypatch.setattr(
        "custom_components.jackery.config_flow.async_discovered_service_info",
        lambda *_a, **_k: [discovered],
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    schema_keys = list(result["data_schema"].schema.keys())
    assert any(str(key) == CONF_BLE_ADDRESS for key in schema_keys)


async def test_user_step_excludes_already_configured_discovered_devices(hass, monkeypatch) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)
    already_configured = SimpleNamespace(address=ADDRESS, name="Jackery_HL1234")
    other = SimpleNamespace(address="11:22:33:44:55:66", name="Jackery_HL9999")
    monkeypatch.setattr(
        "custom_components.jackery.config_flow.async_discovered_service_info",
        lambda *_a, **_k: [already_configured, other],
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    schema_keys = result["data_schema"].schema[CONF_BLE_ADDRESS].container
    assert ADDRESS not in schema_keys
    assert "11:22:33:44:55:66" in schema_keys


async def test_manual_entry_of_a_discovered_address_uses_its_advertised_name(hass, monkeypatch) -> None:
    discovered = SimpleNamespace(address=ADDRESS, name="Jackery_HL1234")
    monkeypatch.setattr(
        "custom_components.jackery.config_flow.async_discovered_service_info",
        lambda *_a, **_k: [discovered],
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_BLE_ADDRESS: ADDRESS})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jackery_HL1234"


async def test_duplicate_address_aborts_as_already_configured(hass, monkeypatch) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)
    monkeypatch.setattr(
        "custom_components.jackery.config_flow.async_discovered_service_info",
        lambda *_a, **_k: [],
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BLE_ADDRESS: ADDRESS}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_discovery_confirms_and_creates_entry(hass) -> None:
    discovery_info = SimpleNamespace(address=ADDRESS, name="Jackery_HL1234")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=discovery_info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BLE_ADDRESS] == ADDRESS


async def test_bluetooth_discovery_of_already_configured_address_aborts(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)
    discovery_info = SimpleNamespace(address=ADDRESS, name="Jackery_HL1234")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=discovery_info
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_scan_interval(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval": 60,
            "connect_timeout": 15,
            "command_timeout": 10,
            "github_reporting_enabled": False,
            "github_repo": "",
            "github_token": "",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["scan_interval"] == 60


async def test_options_flow_requires_repo_and_token_when_github_reporting_enabled(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval": 30,
            "connect_timeout": 15,
            "command_timeout": 10,
            "github_reporting_enabled": True,
            "github_repo": "",
            "github_token": "",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["github_repo"] == "invalid_repo"
    assert result["errors"]["github_token"] == "token_required"


async def test_bluetooth_discovery_and_entry_creation_are_logged_at_info(hass, caplog) -> None:
    discovery_info = SimpleNamespace(address=ADDRESS, name="Jackery_HL1234")

    with caplog.at_level("INFO", logger="custom_components.jackery.config_flow"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=discovery_info
        )
        await hass.config_entries.flow.async_configure(result["flow_id"], {})

    messages = [record.message for record in caplog.records]
    assert any("Discovered new Jackery unit" in message for message in messages)
    assert any("Creating Jackery config entry" in message for message in messages)


async def test_options_flow_accepts_valid_github_reporting_config(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BLE_ADDRESS: ADDRESS}, unique_id=ADDRESS)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval": 30,
            "connect_timeout": 15,
            "command_timeout": 10,
            "github_reporting_enabled": True,
            "github_repo": "bouldinnathan/home-assistant-jackery",
            "github_token": "fake-token",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["github_repo"] == "bouldinnathan/home-assistant-jackery"
