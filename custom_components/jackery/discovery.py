"""Shared Bluetooth device-discovery helpers.

Used by the config flow (to widen the "pick a device" list beyond just
Jackery-looking names, since a unit that advertises under an unexpected or
custom name would otherwise never show up) and by the
``jackery.scan_bluetooth_devices`` service (a post-setup diagnostic that
lists every connectable BLE device Home Assistant currently sees, for
finding additional units or debugging why one isn't showing up).
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def looks_like_jackery_name(name: str | None) -> bool:
    """Return True if a Bluetooth advertised name looks like a Jackery unit."""
    return bool(name) and name.casefold().startswith("jackery")


def describe_bluetooth_device(info: Any) -> dict[str, Any]:
    """Return a plain-dict summary of one discovered BLE device.

    Deliberately omits raw advertisement/manufacturer bytes - this is meant
    for logs and service responses, not a full packet dump. See "Finding
    your unit over Bluetooth" in the README if a packet-level capture is
    what you actually need (e.g. Wireshark with a BLE-capable adapter).
    """
    return {
        "address": info.address,
        "name": info.name,
        "rssi": info.rssi,
        "service_uuids": list(info.service_uuids),
        "looks_like_jackery": looks_like_jackery_name(info.name),
    }


def list_visible_devices(hass: Any, *, exclude_addresses: set[str] | None = None) -> list[dict[str, Any]]:
    """Return every currently visible connectable BLE device as plain dicts.

    Home Assistant's Bluetooth stack scans continuously in the background
    via local adapters and any configured proxies, so this always reflects
    the live cache - there's no separate "start a scan" step to trigger
    first, and calling this repeatedly gives you a fresh live snapshot each
    time.
    """
    from homeassistant.components.bluetooth import async_discovered_service_info

    exclude = exclude_addresses or set()
    devices = [
        describe_bluetooth_device(info)
        for info in async_discovered_service_info(hass, connectable=True)
        if info.address not in exclude
    ]
    for device in devices:
        _LOGGER.debug(
            "Visible BLE device: address=%s name=%s rssi=%s jackery_like=%s service_uuids=%s",
            device["address"],
            device["name"],
            device["rssi"],
            device["looks_like_jackery"],
            device["service_uuids"],
        )
    jackery_like_count = sum(1 for device in devices if device["looks_like_jackery"])
    _LOGGER.debug(
        "Listed %d visible connectable BLE device(s) (%d Jackery-looking, %d excluded as already configured)",
        len(devices),
        jackery_like_count,
        len(exclude),
    )
    return devices
