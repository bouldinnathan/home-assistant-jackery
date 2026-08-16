"""Constants for the Jackery integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "jackery"
NAME: Final = "Jackery"
VERSION: Final = "0.1.0"
MANUFACTURER: Final = "Jackery"

PLATFORMS: Final = ["sensor", "binary_sensor", "switch"]

# GATT service/characteristic UUIDs reverse-engineered from the Jackery mobile
# app's BLE traffic against Explorer/Plus/Ultra-series portable power stations
# (see docs/PROTOCOL.md). Jackery has never published these publicly, so a
# firmware or app update could change them without notice.
BLE_SERVICE_UUID: Final = "0000ffff-0000-1000-8000-00805f9b34fb"
BLE_WRITE_CHAR_UUID: Final = "0000ff01-0000-1000-8000-00805f9b34fb"
BLE_NOTIFY_CHAR_UUID: Final = "0000ff02-0000-1000-8000-00805f9b34fb"

CONF_BLE_ADDRESS: Final = "ble_address"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_CONNECT_TIMEOUT: Final = "connect_timeout"
CONF_COMMAND_TIMEOUT: Final = "command_timeout"
CONF_GITHUB_REPORTING_ENABLED: Final = "github_reporting_enabled"
CONF_GITHUB_REPO: Final = "github_repo"
CONF_GITHUB_TOKEN: Final = "github_token"

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600
DEFAULT_CONNECT_TIMEOUT: Final = 15.0
DEFAULT_COMMAND_TIMEOUT: Final = 10.0

# Home Assistant device_info fields for the power station itself.
ATTR_MODEL: Final = "model"
ATTR_SERIAL: Final = "serial"
ATTR_FIRMWARE: Final = "firmware_version"

SERVICE_REFRESH: Final = "refresh"
SERVICE_SEND_RAW_COMMAND: Final = "send_raw_command"
SERVICE_SCAN_BLUETOOTH_DEVICES: Final = "scan_bluetooth_devices"
ATTR_DEVICE_ID: Final = "device_id"
ATTR_COMMAND: Final = "command"

EVENT_RAW_COMMAND_RESPONSE: Final = "jackery_raw_command_response"

# Keys treated as controllable on/off outputs when discovered in device
# telemetry. Matched case-insensitively as a substring of the flattened
# telemetry key (see protocol.classify_field). Extend via the
# ``extra_switch_keys`` option if your unit reports a different name.
DEFAULT_SWITCH_KEY_HINTS: Final = (
    "acoutput",
    "ac_switch",
    "acswitch",
    "dcoutput",
    "dc_switch",
    "dcswitch",
    "usboutput",
    "usb_switch",
    "usbswitch",
    "outputswitch",
)

DIAGNOSTIC_REDACT: Final = [
    "address",
    "ble_address",
    "github_token",
    "mac",
    "serial",
    "token",
    "unique_id",
]
