"""Base entity for the Jackery integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import JackeryCoordinator

_LOGGER = logging.getLogger(__name__)

# Sentinel distinct from any real telemetry value (including None), so the
# first coordinator update after an entity is created is always treated as a
# change worth logging.
_UNSET = object()


class JackeryEntity(CoordinatorEntity[JackeryCoordinator]):
    """Base entity bound to one Jackery unit's coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JackeryCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{unique_suffix}"
        self._last_logged_value: Any = _UNSET
        _LOGGER.debug(
            "Created entity %s for Jackery unit %s", self._attr_unique_id, coordinator.address
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the single power-station device this entity belongs to."""
        telemetry = self.coordinator.telemetry
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, self.coordinator.address)},
            name=self.coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=telemetry.model,
            sw_version=telemetry.firmware_version,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Log this entity's value whenever it changes, then update HA state as usual."""
        field_key = getattr(self, "_field_key", None)
        if field_key is not None:
            value = self.coordinator.telemetry.fields.get(field_key)
            if value != self._last_logged_value:
                _LOGGER.debug(
                    "Entity %s (%s) value changed: %r -> %r",
                    self._attr_unique_id,
                    field_key,
                    self._last_logged_value,
                    value,
                )
                self._last_logged_value = value
        super()._handle_coordinator_update()
