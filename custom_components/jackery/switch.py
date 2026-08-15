"""Switch platform for Jackery: dynamically discovered controllable outputs.

Boolean fields whose key matches a known output-ish pattern (AC/DC/USB
output; see const.DEFAULT_SWITCH_KEY_HINTS, extendable via the
``extra_switch_keys`` option) become switches instead of read-only binary
sensors. Writing is best-effort - see docs/PROTOCOL.md for why the write
command envelope isn't independently confirmed against real hardware. Use
the ``jackery.send_raw_command`` service plus DEBUG logging to verify or
correct it against your own unit.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_SWITCH_KEY_HINTS, DOMAIN
from .coordinator import JackeryCoordinator
from .entity import JackeryEntity
from .models import FieldKind, classify_field, humanize_field

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Jackery switches, then keep adding new ones as fields appear."""
    coordinator: JackeryCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up switch platform for Jackery entry %s", entry.entry_id)
    known_keys: set[str] = set()

    @callback
    def _add_new_switches() -> None:
        new_entities: list[JackerySwitch] = []
        for key, value in coordinator.telemetry.fields.items():
            if key in known_keys:
                continue
            kind = classify_field(key, value, switch_key_hints=DEFAULT_SWITCH_KEY_HINTS)
            if kind is not FieldKind.SWITCH:
                continue
            known_keys.add(key)
            new_entities.append(JackerySwitch(coordinator, key))
        if new_entities:
            _LOGGER.debug(
                "Adding %d new Jackery switch entit(y/ies): %s",
                len(new_entities),
                [entity.unique_id for entity in new_entities],
            )
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_switches))
    _add_new_switches()


class JackerySwitch(JackeryEntity, SwitchEntity):
    """A dynamically discovered writable output, controlled via best-effort BLE commands."""

    def __init__(self, coordinator: JackeryCoordinator, field_key: str) -> None:
        super().__init__(coordinator, f"switch_{field_key}")
        self._field_key = field_key
        self._attr_name = humanize_field(field_key)

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.telemetry.fields.get(self._field_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"raw_field_key": self._field_key}

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.debug("User requested turn_on for %s", self._field_key)
        await self.coordinator.async_write_field(self._field_key, True)
        _LOGGER.debug("turn_on for %s completed", self._field_key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.debug("User requested turn_off for %s", self._field_key)
        await self.coordinator.async_write_field(self._field_key, False)
        _LOGGER.debug("turn_off for %s completed", self._field_key)
