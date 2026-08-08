"""Binary sensor platform for Jackery: dynamically discovered boolean fields.

Boolean telemetry fields that don't look like a controllable output (see
models.classify_field / switch.py) are exposed here as read-only binary
sensors - e.g. charging state, fault flags, or output-active indicators that
aren't also writable.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_SWITCH_KEY_HINTS, DOMAIN
from .coordinator import JackeryCoordinator
from .entity import JackeryEntity
from .models import FieldKind, classify_field, humanize_field

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Jackery binary sensors, then keep adding new ones as fields appear."""
    coordinator: JackeryCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_keys: set[str] = set()

    @callback
    def _add_new_binary_sensors() -> None:
        new_entities: list[JackeryBinarySensor] = []
        for key, value in coordinator.telemetry.fields.items():
            if key in known_keys:
                continue
            kind = classify_field(key, value, switch_key_hints=DEFAULT_SWITCH_KEY_HINTS)
            if kind is not FieldKind.BINARY_SENSOR:
                continue
            known_keys.add(key)
            new_entities.append(JackeryBinarySensor(coordinator, key))
        if new_entities:
            _LOGGER.debug(
                "Adding %d new Jackery binary_sensor entit(y/ies): %s",
                len(new_entities),
                [entity.unique_id for entity in new_entities],
            )
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_binary_sensors))
    _add_new_binary_sensors()


class JackeryBinarySensor(JackeryEntity, BinarySensorEntity):
    """A dynamically discovered boolean telemetry field."""

    def __init__(self, coordinator: JackeryCoordinator, field_key: str) -> None:
        super().__init__(coordinator, f"binary_{field_key}")
        self._field_key = field_key
        self._attr_name = humanize_field(field_key)

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.telemetry.fields.get(self._field_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"raw_field_key": self._field_key}
