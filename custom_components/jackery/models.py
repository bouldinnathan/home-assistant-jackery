"""Data models and field-classification heuristics for Jackery telemetry.

The BLE protocol's exact JSON schema is not publicly documented (see
docs/PROTOCOL.md), so entities are not hardcoded against specific field
names. Instead, whatever fields a given unit actually reports are flattened
and classified here, and the sensor/binary_sensor/switch platforms turn that
classification into entities dynamically. This makes the integration work
across firmware/model variations that use different field names, at the cost
of slightly less polished default entity names.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_LOGGER = logging.getLogger(__name__)


class FieldKind(Enum):
    """How a telemetry field should be represented as an entity."""

    POWER_W = "power_w"
    ENERGY_WH = "energy_wh"
    PERCENT = "percent"
    TEMPERATURE_C = "temperature_c"
    VOLTAGE_V = "voltage_v"
    CURRENT_A = "current_a"
    DURATION_MIN = "duration_min"
    SWITCH = "switch"
    BINARY_SENSOR = "binary_sensor"
    GENERIC_NUMERIC = "generic_numeric"
    GENERIC_TEXT = "generic_text"
    IGNORED = "ignored"


_KEY_PATTERNS: tuple[tuple[re.Pattern[str], FieldKind], ...] = (
    (re.compile(r"(soc|battery).*(level|percent|pct)|^soc$|batterylevel|batterypercent", re.I), FieldKind.PERCENT),
    (re.compile(r"temp", re.I), FieldKind.TEMPERATURE_C),
    (re.compile(r"volt", re.I), FieldKind.VOLTAGE_V),
    (re.compile(r"current|amps?\b", re.I), FieldKind.CURRENT_A),
    (re.compile(r"remain.*time|eta|runtime|minutes?left", re.I), FieldKind.DURATION_MIN),
    (re.compile(r"capacity.*wh|wh.*capacity|energy", re.I), FieldKind.ENERGY_WH),
    (re.compile(r"watt|power(?!.*(mode|off|on))|pwr", re.I), FieldKind.POWER_W),
)

_IGNORED_KEY_PATTERNS = re.compile(
    r"^(msgid|messageid|seq|sequence|ts|timestamp|token|sign|signature|checksum|crc|reserved|pad)\d*$",
    re.I,
)


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def humanize_field(key: str) -> str:
    """Turn a flattened telemetry key like ``port.acOutputWatts`` into a label."""
    tail = key.rsplit(".", 1)[-1]
    words = _CAMEL_RE.sub(" ", tail).replace("_", " ").strip()
    return f"{words[:1].upper()}{words[1:]}" if words else key


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested JSON into dotted keys, e.g. ``{"port": {"ac": 1}}`` -> ``{"port.ac": 1}``."""
    flat: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flat.update(flatten(value, child_prefix))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            flat.update(flatten(value, f"{prefix}[{index}]"))
    else:
        if prefix:
            flat[prefix] = data
    return flat


def classify_field(key: str, value: Any, *, switch_key_hints: tuple[str, ...] = ()) -> FieldKind:
    """Guess how a flattened telemetry field should be exposed as an entity."""
    normalized = key.rsplit(".", 1)[-1].casefold()
    if _IGNORED_KEY_PATTERNS.match(normalized.replace("[", "").replace("]", "")):
        return FieldKind.IGNORED

    if isinstance(value, bool):
        if any(hint in normalized.replace("_", "").replace("-", "") for hint in switch_key_hints):
            return FieldKind.SWITCH
        return FieldKind.BINARY_SENSOR

    if isinstance(value, (int, float)):
        for pattern, kind in _KEY_PATTERNS:
            if pattern.search(normalized):
                return kind
        return FieldKind.GENERIC_NUMERIC

    return FieldKind.GENERIC_TEXT


@dataclass
class DeviceTelemetry:
    """Latest known state of one Jackery unit, as flattened key/value pairs."""

    address: str
    fields: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    serial: str | None = None
    firmware_version: str | None = None
    connected: bool = False
    rssi: int | None = None

    def merge(self, payload: dict[str, Any]) -> None:
        """Merge a newly decoded JSON payload's flattened fields into state."""
        new_fields = flatten(payload)
        new_keys = [key for key in new_fields if key not in self.fields]
        self.fields.update(new_fields)
        if new_keys:
            _LOGGER.debug("Telemetry for %s: %d new field(s) discovered: %s", self.address, len(new_keys), new_keys)

        previous_model, previous_serial, previous_firmware = self.model, self.serial, self.firmware_version
        self.model = self._first_string_field(("model", "deviceModel", "productModel"))
        self.serial = self._first_string_field(("sn", "serial", "serialNumber", "deviceSn"))
        self.firmware_version = self._first_string_field(("fw", "firmware", "firmwareVersion", "fwVersion"))

        if self.model is not None and self.model != previous_model:
            _LOGGER.info("Identified Jackery unit %s as model %s", self.address, self.model)
        if self.serial is not None and self.serial != previous_serial:
            _LOGGER.debug("Discovered serial number for Jackery unit %s", self.address)
        if self.firmware_version is not None and self.firmware_version != previous_firmware:
            _LOGGER.info("Jackery unit %s reports firmware version %s", self.address, self.firmware_version)

    def _first_string_field(self, keys: tuple[str, ...]) -> str | None:
        """Return the first string value found in ``self.fields`` for ``keys``, in priority order."""
        for key in keys:
            value = self.fields.get(key)
            if isinstance(value, str):
                return value
        return None
