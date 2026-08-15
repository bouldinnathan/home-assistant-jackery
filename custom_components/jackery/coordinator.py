"""Data update coordinator for one Jackery power station config entry."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble_client import JackeryBLEClient, JackeryBLEError
from .const import (
    CONF_BLE_ADDRESS,
    CONF_COMMAND_TIMEOUT,
    CONF_CONNECT_TIMEOUT,
    CONF_SCAN_INTERVAL,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .models import DeviceTelemetry
from .protocol import POLL_REQUEST_SEQUENCE, build_set_command

_LOGGER = logging.getLogger(__name__)

# Errors that mean "the device didn't answer this time" rather than "this
# integration has a bug." These never trigger the GitHub crash reporter -
# doing so would flood the issue tracker with routine Bluetooth flakiness
# from every user's environment instead of surfacing real defects.
_EXPECTED_ERRORS = (JackeryBLEError, TimeoutError, OSError, EOFError)

ErrorReporter = Callable[[Exception, str], Awaitable[None]]


class JackeryCoordinator(DataUpdateCoordinator[DeviceTelemetry]):
    """Poll one Jackery unit over BLE and expose read/write helpers to entities."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        error_reporter: ErrorReporter | None = None,
    ) -> None:
        self.address: str = entry.data[CONF_BLE_ADDRESS]
        options = entry.options
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.connect_timeout: float = options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)
        self.command_timeout: float = options.get(CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT)
        self._error_reporter = error_reporter
        self._client = JackeryBLEClient(self.address)
        self._telemetry = DeviceTelemetry(address=self.address)
        self._consecutive_failures = 0

        import datetime as dt

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.address}",
            update_interval=dt.timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        _LOGGER.debug(
            "Coordinator created for Jackery unit %s: scan_interval=%ss, connect_timeout=%ss, "
            "command_timeout=%ss, error_reporter=%s",
            self.address,
            scan_interval,
            self.connect_timeout,
            self.command_timeout,
            "enabled" if error_reporter is not None else "disabled",
        )

    @property
    def telemetry(self) -> DeviceTelemetry:
        """Return the most recently merged telemetry snapshot."""
        return self._telemetry

    def _get_ble_device(self) -> Any:
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            _LOGGER.debug(
                "Jackery unit %s not currently visible to any Bluetooth adapter/proxy", self.address
            )
        else:
            _LOGGER.debug(
                "Jackery unit %s resolved to BLE device %s (rssi=%s)",
                self.address,
                ble_device,
                getattr(ble_device, "rssi", "unknown"),
            )
        return ble_device

    async def _async_update_data(self) -> DeviceTelemetry:
        _LOGGER.debug("Starting poll cycle for Jackery unit %s", self.address)
        started = time.monotonic()
        ble_device = self._get_ble_device()
        if ble_device is None:
            self._telemetry.connected = False
            raise UpdateFailed(f"Jackery unit {self.address} is not visible to Bluetooth right now")

        try:
            frames = await self._client.async_run_session(
                ble_device,
                list(POLL_REQUEST_SEQUENCE),
                connect_timeout=self.connect_timeout,
                command_timeout=self.command_timeout,
            )
        except _EXPECTED_ERRORS as err:
            self._consecutive_failures += 1
            self._telemetry.connected = False
            _LOGGER.warning(
                "Poll of Jackery unit %s failed (%d consecutive failure(s)): %s",
                self.address,
                self._consecutive_failures,
                err,
            )
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            self._telemetry.connected = False
            _LOGGER.error("Unexpected error polling Jackery unit %s", self.address, exc_info=True)
            await self._report(err, "poll")
            raise UpdateFailed(f"Unexpected error polling {self.address}: {err}") from err

        if self._consecutive_failures > 0:
            _LOGGER.info(
                "Jackery unit %s recovered after %d consecutive failure(s)",
                self.address,
                self._consecutive_failures,
            )
        self._consecutive_failures = 0
        self._telemetry.connected = True
        self._telemetry.rssi = getattr(ble_device, "rssi", None)
        _LOGGER.debug(
            "Merging %d response frame(s) from Jackery unit %s (rssi=%s)",
            len(frames),
            self.address,
            self._telemetry.rssi,
        )
        for index, frame in enumerate(frames):
            _LOGGER.debug("Merging frame %d/%d for %s: %s", index + 1, len(frames), self.address, frame)
            self._telemetry.merge(frame)
        duration = time.monotonic() - started
        _LOGGER.info(
            "Poll of Jackery unit %s succeeded in %.2fs, %d field(s) known",
            self.address,
            duration,
            len(self._telemetry.fields),
        )
        return self._telemetry

    async def async_write_field(self, path: str, value: Any) -> None:
        """Send a best-effort write command for one telemetry field, then refresh.

        See docs/PROTOCOL.md: the write envelope is not independently
        confirmed against real hardware. Failures are logged loudly and
        surfaced to the calling entity so Home Assistant shows the write as
        failed rather than silently pretending it worked.
        """
        ble_device = self._get_ble_device()
        if ble_device is None:
            raise UpdateFailed(f"Jackery unit {self.address} is not visible to Bluetooth right now")

        command = build_set_command(path, value)
        _LOGGER.info("Writing %s=%r to Jackery unit %s", path, value, self.address)
        try:
            await self._client.async_run_session(
                ble_device,
                [command],
                connect_timeout=self.connect_timeout,
                command_timeout=self.command_timeout,
            )
        except _EXPECTED_ERRORS as err:
            _LOGGER.warning("Write %s=%r to Jackery unit %s failed: %s", path, value, self.address, err)
            raise
        except Exception as err:
            _LOGGER.error(
                "Unexpected error writing %s=%r to Jackery unit %s", path, value, self.address, exc_info=True
            )
            await self._report(err, "write")
            raise

        # Optimistically reflect the write locally so the UI updates
        # immediately; the next poll cycle will correct it if the device
        # rejected the command.
        self._telemetry.fields[path] = value
        self.async_set_updated_data(self._telemetry)
        _LOGGER.debug("Write %s=%r to Jackery unit %s acknowledged, requesting refresh", path, value, self.address)
        await self.async_request_refresh()

    async def async_send_raw_command(self, command: dict[str, Any]) -> list[dict[str, Any]]:
        """Send an arbitrary JSON command and return whatever the device sends back.

        Escape hatch for the ``jackery.send_raw_command`` service: lets a user
        test/replace commands (e.g. after sniffing their own app's BLE
        traffic) without waiting on an integration code change. Results are
        also emitted as the ``jackery_raw_command_response`` event and logged
        at INFO so they're easy to find either way.
        """
        ble_device = self._get_ble_device()
        if ble_device is None:
            raise UpdateFailed(f"Jackery unit {self.address} is not visible to Bluetooth right now")

        _LOGGER.info("Sending raw command to Jackery unit %s: %s", self.address, command)
        try:
            frames = await self._client.async_run_session(
                ble_device,
                [command],
                connect_timeout=self.connect_timeout,
                command_timeout=self.command_timeout,
            )
        except _EXPECTED_ERRORS as err:
            _LOGGER.warning("Raw command to Jackery unit %s failed: %s", self.address, err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error sending raw command to Jackery unit %s", self.address, exc_info=True)
            await self._report(err, "send_raw_command")
            raise

        _LOGGER.info("Raw command to Jackery unit %s returned %d frame(s): %s", self.address, len(frames), frames)
        for frame in frames:
            self._telemetry.merge(frame)
        self.async_set_updated_data(self._telemetry)
        return frames

    async def _report(self, error: Exception, context: str) -> None:
        if self._error_reporter is None:
            _LOGGER.debug(
                "GitHub crash reporting is not configured for %s; not reporting %s during %s",
                self.address,
                type(error).__name__,
                context,
            )
            return
        _LOGGER.debug("Reporting %s during %s for %s to the configured GitHub crash reporter", type(error).__name__, context, self.address)
        try:
            await self._error_reporter(error, context)
        except Exception:  # noqa: BLE001 - the reporter must never break the coordinator
            _LOGGER.warning("GitHub crash reporter itself raised an error", exc_info=True)
