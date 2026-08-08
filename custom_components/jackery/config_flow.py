"""Config flow for the Jackery integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.core import callback

from .const import (
    CONF_BLE_ADDRESS,
    CONF_COMMAND_TIMEOUT,
    CONF_CONNECT_TIMEOUT,
    CONF_GITHUB_REPO,
    CONF_GITHUB_REPORTING_ENABLED,
    CONF_GITHUB_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _looks_like_jackery(name: str | None) -> bool:
    return bool(name) and name.casefold().startswith("jackery")


class JackeryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual setup of one Jackery power station."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_address: str | None = None
        self._discovered_name: str | None = None
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak):
        """Handle a Bluetooth advertisement matching the Jackery GATT service."""
        _LOGGER.debug(
            "Bluetooth discovery for Jackery: address=%s name=%s", discovery_info.address, discovery_info.name
        )
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered_address = discovery_info.address
        self._discovered_name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None):
        """Confirm adding the Bluetooth-discovered Jackery unit."""
        assert self._discovered_address is not None
        if user_input is not None:
            return self._async_create(self._discovered_address, self._discovered_name or self._discovered_address)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": self._discovered_name or self._discovered_address},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle manual setup, offering any already-seen Jackery-looking devices."""
        errors: dict[str, str] = {}
        current_addresses = self._async_current_ids()
        self._discovered_devices = {
            info.address: info.name or info.address
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.address not in current_addresses and _looks_like_jackery(info.name)
        }

        if user_input is not None:
            address = user_input[CONF_BLE_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            name = self._discovered_devices.get(address, address)
            return self._async_create(address, name)

        if self._discovered_devices:
            schema = vol.Schema({vol.Required(CONF_BLE_ADDRESS): vol.In(self._discovered_devices)})
        else:
            schema = vol.Schema({vol.Required(CONF_BLE_ADDRESS): str})

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @callback
    def _async_create(self, address: str, name: str):
        return self.async_create_entry(title=name, data={CONF_BLE_ADDRESS: address})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> JackeryOptionsFlow:
        """Return the options flow for this entry."""
        return JackeryOptionsFlow()


class JackeryOptionsFlow(config_entries.OptionsFlow):
    """Options: polling/timeouts and opt-in GitHub crash reporting."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        options = self.config_entry.options

        if user_input is not None:
            if user_input.get(CONF_GITHUB_REPORTING_ENABLED):
                repo = user_input.get(CONF_GITHUB_REPO, "").strip()
                token = user_input.get(CONF_GITHUB_TOKEN, "").strip()
                if not repo or "/" not in repo:
                    errors[CONF_GITHUB_REPO] = "invalid_repo"
                if not token:
                    errors[CONF_GITHUB_TOKEN] = "token_required"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_CONNECT_TIMEOUT,
                    default=options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=120)),
                vol.Optional(
                    CONF_COMMAND_TIMEOUT,
                    default=options.get(CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=120)),
                vol.Optional(
                    CONF_GITHUB_REPORTING_ENABLED,
                    default=options.get(CONF_GITHUB_REPORTING_ENABLED, False),
                ): bool,
                vol.Optional(CONF_GITHUB_REPO, default=options.get(CONF_GITHUB_REPO, "")): str,
                vol.Optional(CONF_GITHUB_TOKEN, default=options.get(CONF_GITHUB_TOKEN, "")): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
