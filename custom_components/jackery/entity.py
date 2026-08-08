"""Base entity for the Jackery integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import JackeryCoordinator


class JackeryEntity(CoordinatorEntity[JackeryCoordinator]):
    """Base entity bound to one Jackery unit's coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JackeryCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{unique_suffix}"

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
