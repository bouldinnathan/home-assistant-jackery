"""Sensor platform for Jackery: dynamically discovered telemetry fields.

The BLE protocol's exact field names aren't publicly documented (see
docs/PROTOCOL.md), so entities aren't hardcoded against specific keys.
Instead, every numeric/text field the device actually reports is classified
by models.classify_field and turned into a sensor here, with new fields
picked up automatically as later polls reveal them (e.g. fields only present
in the "full" data_get response).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JackeryCoordinator
from .entity import JackeryEntity
from .models import FieldKind, classify_field, humanize_field

_LOGGER = logging.getLogger(__name__)

_SENSOR_KINDS: dict[FieldKind, dict[str, Any]] = {
    FieldKind.POWER_W: {
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    FieldKind.ENERGY_WH: {
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergy.WATT_HOUR,
    },
    FieldKind.PERCENT: {
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
    },
    FieldKind.TEMPERATURE_C: {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
    },
    FieldKind.VOLTAGE_V: {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
    },
    FieldKind.CURRENT_A: {
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
    },
    FieldKind.DURATION_MIN: {
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
    },
    FieldKind.GENERIC_NUMERIC: {
        "state_class": SensorStateClass.MEASUREMENT,
    },
    FieldKind.GENERIC_TEXT: {},
}

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Jackery sensors, then keep adding new ones as fields appear."""
    coordinator: JackeryCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up sensor platform for Jackery entry %s", entry.entry_id)
    known_keys: set[str] = set()

    @callback
    def _add_new_sensors() -> None:
        new_entities: list[JackerySensor] = []
        for key, value in coordinator.telemetry.fields.items():
            if key in known_keys:
                continue
            kind = classify_field(key, value)
            if kind not in _SENSOR_KINDS:
                continue
            known_keys.add(key)
            new_entities.append(JackerySensor(coordinator, key, kind))
        if new_entities:
            _LOGGER.debug(
                "Adding %d new Jackery sensor entit(y/ies): %s",
                len(new_entities),
                [entity.unique_id for entity in new_entities],
            )
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_sensors))
    _add_new_sensors()


class JackerySensor(JackeryEntity, SensorEntity):
    """A dynamically discovered telemetry field exposed as a sensor."""

    def __init__(self, coordinator: JackeryCoordinator, field_key: str, kind: FieldKind) -> None:
        super().__init__(coordinator, f"sensor_{field_key}")
        self._field_key = field_key
        self._attr_name = humanize_field(field_key)
        options = _SENSOR_KINDS[kind]
        self._attr_device_class = options.get("device_class")
        self._attr_state_class = options.get("state_class")
        self._attr_native_unit_of_measurement = options.get("unit")

    @property
    def native_value(self) -> Any:
        return self.coordinator.telemetry.fields.get(self._field_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"raw_field_key": self._field_key}
