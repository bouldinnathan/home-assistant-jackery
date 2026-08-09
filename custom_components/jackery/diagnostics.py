"""Diagnostics support for Jackery."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DIAGNOSTIC_REDACT, DOMAIN, VERSION
from .coordinator import JackeryCoordinator
from .redact import sanitize_data

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return a redacted diagnostics snapshot for one Jackery config entry."""
    _LOGGER.debug("Generating diagnostics for Jackery entry %s", entry.entry_id)
    coordinator: JackeryCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    telemetry = coordinator.telemetry if coordinator is not None else None
    if coordinator is None:
        _LOGGER.debug("Diagnostics for entry %s: no coordinator loaded (entry not set up)", entry.entry_id)

    diagnostics: dict[str, Any] = {
        "integration_version": VERSION,
        "entry_options": dict(entry.options),
        "coordinator": {
            "loaded": coordinator is not None,
            "last_update_success": coordinator.last_update_success if coordinator else None,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator is not None and coordinator.update_interval
                else None
            ),
        },
        "telemetry": {
            "connected": telemetry.connected if telemetry else None,
            "model": telemetry.model if telemetry else None,
            "firmware_version": telemetry.firmware_version if telemetry else None,
            "field_count": len(telemetry.fields) if telemetry else 0,
            "fields": telemetry.fields if telemetry else {},
        },
    }
    sanitized = sanitize_data(diagnostics)
    _LOGGER.debug(
        "Diagnostics for entry %s ready: %d field(s), connected=%s",
        entry.entry_id,
        diagnostics["telemetry"]["field_count"],
        diagnostics["telemetry"]["connected"],
    )
    return async_redact_data(sanitized, DIAGNOSTIC_REDACT)
