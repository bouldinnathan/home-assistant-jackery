"""Jackery custom integration for Home Assistant."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_COMMAND,
    ATTR_DEVICE_ID,
    CONF_GITHUB_REPO,
    CONF_GITHUB_REPORTING_ENABLED,
    CONF_GITHUB_TOKEN,
    DOMAIN,
    EVENT_RAW_COMMAND_RESPONSE,
    PLATFORMS,
    SERVICE_REFRESH,
    SERVICE_SEND_RAW_COMMAND,
)
from .coordinator import JackeryCoordinator
from .github_reporter import GitHubIssueReporter

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one Jackery unit from a config entry."""
    _LOGGER.debug("Setting up Jackery config entry %s (%s)", entry.entry_id, entry.title)

    error_reporter = None
    if entry.options.get(CONF_GITHUB_REPORTING_ENABLED):
        repo = entry.options.get(CONF_GITHUB_REPO)
        token = entry.options.get(CONF_GITHUB_TOKEN)
        if repo and token:
            _LOGGER.info(
                "GitHub automatic issue reporting enabled for entry %s, target repo %s", entry.entry_id, repo
            )
            reporter = GitHubIssueReporter(hass, repo=repo, token=token)
            error_reporter = reporter.async_report
        else:
            _LOGGER.warning(
                "GitHub issue reporting is enabled for entry %s but repo/token is missing; disabling it",
                entry.entry_id,
            )

    coordinator = JackeryCoordinator(hass, entry, error_reporter=error_reporter)
    _LOGGER.debug("Requesting first refresh for Jackery entry %s before finishing setup", entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _LOGGER.debug("Forwarding Jackery entry %s to platforms: %s", entry.entry_id, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    _LOGGER.info("Jackery config entry %s set up (%s)", entry.entry_id, entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one Jackery config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        _LOGGER.info("Jackery config entry %s unloaded", entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change (e.g. scan interval, GitHub reporting)."""
    _LOGGER.debug("Reloading Jackery config entry %s after options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        _LOGGER.debug("Jackery services already registered, skipping")
        return
    _LOGGER.debug("Registering Jackery services: %s, %s", SERVICE_REFRESH, SERVICE_SEND_RAW_COMMAND)

    async def _refresh(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_DEVICE_ID))
        _LOGGER.info("Manual refresh requested for Jackery unit %s", coordinator.address)
        await coordinator.async_request_refresh()

    async def _send_raw_command(call: ServiceCall) -> dict[str, Any] | None:
        coordinator = _resolve_coordinator(hass, call.data.get(ATTR_DEVICE_ID))
        raw = call.data[ATTR_COMMAND]
        try:
            command = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"command must be a JSON object: {err}") from err
        if not isinstance(command, dict):
            raise HomeAssistantError("command must decode to a JSON object")

        _LOGGER.info("Raw command requested for Jackery unit %s: %s", coordinator.address, command)
        frames = await coordinator.async_send_raw_command(command)
        hass.bus.async_fire(EVENT_RAW_COMMAND_RESPONSE, {"address": coordinator.address, "frames": frames})
        if getattr(call, "return_response", True):
            return {"frames": frames}
        return None

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _refresh,
        schema=vol.Schema({vol.Optional(ATTR_DEVICE_ID): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        _send_raw_command,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_DEVICE_ID): cv.string,
                vol.Required(ATTR_COMMAND): vol.Any(cv.string, dict),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )


def _resolve_coordinator(hass: HomeAssistant, device_id: str | None) -> JackeryCoordinator:
    entries: dict[str, JackeryCoordinator] = hass.data.get(DOMAIN, {})
    if not entries:
        _LOGGER.debug("Cannot resolve a Jackery coordinator: no config entries are set up")
        raise HomeAssistantError("No Jackery device is configured")

    if device_id is None:
        if len(entries) == 1:
            coordinator = next(iter(entries.values()))
            _LOGGER.debug("No device_id given; using the only configured Jackery unit %s", coordinator.address)
            return coordinator
        raise HomeAssistantError("device_id is required when more than one Jackery unit is configured")

    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is not None:
        for entry_id in device.config_entries:
            if entry_id in entries:
                _LOGGER.debug("Resolved device_id %s to Jackery unit %s", device_id, entries[entry_id].address)
                return entries[entry_id]
    if device_id in entries:
        return entries[device_id]
    _LOGGER.debug("device_id %s did not match any configured Jackery unit", device_id)
    raise HomeAssistantError(f"No Jackery device found for device_id {device_id}")
