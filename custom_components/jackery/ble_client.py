"""Async BLE transport for one Jackery power station.

Connects per operation (poll or write) rather than holding a persistent
session, because field reports say some units stop responding to a
long-held GATT connection (see docs/PROTOCOL.md). Every connect, write,
notify, and disconnect is logged at DEBUG so a user capturing their own
Android Bluetooth HCI snoop log can line up what this integration sent
against what the real app sends, for debugging or protocol correction.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .const import BLE_NOTIFY_CHAR_UUID, BLE_WRITE_CHAR_UUID
from .protocol import JsonFrameAssembler, encode

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)


class JackeryBLEError(Exception):
    """Raised for any BLE transport failure talking to a Jackery unit."""


class JackeryConnectionError(JackeryBLEError):
    """Raised when the GATT connection could not be established."""


class JackeryCommandTimeoutError(JackeryBLEError):
    """Raised when the device did not respond to a command in time."""


class JackeryBLEClient:
    """One-shot connect/command/disconnect BLE sessions for a Jackery unit."""

    def __init__(self, address: str) -> None:
        self._address = address
        self._lock = asyncio.Lock()

    async def async_run_session(
        self,
        ble_device: BLEDevice,
        commands: list[dict[str, Any]],
        *,
        connect_timeout: float,
        command_timeout: float,
        responses_per_command: int = 1,
    ) -> list[dict[str, Any]]:
        """Connect, send each command in order, collect notify responses, disconnect.

        Serialized by an internal lock so a scheduled poll and a user-triggered
        write never share overlapping GATT sessions with the same device.
        """
        async with self._lock:
            _LOGGER.debug(
                "Starting BLE session with %s: %d command(s), connect_timeout=%.1fs, command_timeout=%.1fs",
                self._address,
                len(commands),
                connect_timeout,
                command_timeout,
            )
            client = await self._connect(ble_device, connect_timeout)
            try:
                return await self._send_commands(client, commands, command_timeout, responses_per_command)
            finally:
                await self._disconnect(client)

    async def _connect(self, ble_device: BLEDevice, connect_timeout: float) -> Any:
        from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

        _LOGGER.debug("Connecting to Jackery unit %s (timeout=%.1fs)", self._address, connect_timeout)
        try:
            async with asyncio.timeout(connect_timeout):
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self._address,
                )
        except TimeoutError as err:
            _LOGGER.warning("Timed out connecting to Jackery unit %s after %.1fs", self._address, connect_timeout)
            raise JackeryConnectionError(f"Timed out connecting to {self._address}") from err
        except Exception as err:
            _LOGGER.warning("Failed to connect to Jackery unit %s: %s", self._address, err)
            raise JackeryConnectionError(f"Failed to connect to {self._address}: {err}") from err
        _LOGGER.info("Connected to Jackery unit %s", self._address)
        return client

    async def _disconnect(self, client: Any) -> None:
        try:
            await client.disconnect()
            _LOGGER.debug("Disconnected from Jackery unit %s", self._address)
        except Exception as err:  # noqa: BLE001 - disconnect must never raise past cleanup
            _LOGGER.debug("Ignoring error disconnecting from Jackery unit %s: %s", self._address, err)

    async def _send_commands(
        self,
        client: Any,
        commands: list[dict[str, Any]],
        command_timeout: float,
        responses_per_command: int,
    ) -> list[dict[str, Any]]:
        assembler = JsonFrameAssembler()
        collected: list[dict[str, Any]] = []
        frame_event = asyncio.Event()

        def _on_notify(_characteristic: Any, data: bytearray) -> None:
            frames = assembler.feed(bytes(data))
            if frames:
                collected.extend(frames)
                frame_event.set()

        await client.start_notify(BLE_NOTIFY_CHAR_UUID, _on_notify)
        try:
            for command in commands:
                target_count = len(collected) + responses_per_command
                payload = encode(command)
                _LOGGER.debug("Writing command to %s: %s (%s)", self._address, command, payload)
                await client.write_gatt_char(BLE_WRITE_CHAR_UUID, payload, response=True)

                frame_event.clear()
                try:
                    async with asyncio.timeout(command_timeout):
                        while len(collected) < target_count:
                            await frame_event.wait()
                            frame_event.clear()
                except TimeoutError as err:
                    _LOGGER.warning(
                        "Jackery unit %s did not respond to command %s within %.1fs",
                        self._address,
                        command,
                        command_timeout,
                    )
                    raise JackeryCommandTimeoutError(
                        f"No response to {command.get('cmd', command)} within {command_timeout}s"
                    ) from err
        finally:
            assembler.reset()
            try:
                await client.stop_notify(BLE_NOTIFY_CHAR_UUID)
            except Exception as err:  # noqa: BLE001 - best-effort cleanup only
                _LOGGER.debug("Ignoring error stopping notify on %s: %s", self._address, err)

        _LOGGER.debug("BLE session with %s complete, collected %d frame(s)", self._address, len(collected))
        return collected
