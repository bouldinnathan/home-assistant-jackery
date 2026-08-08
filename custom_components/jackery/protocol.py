"""Jackery BLE JSON-over-GATT protocol.

Reverse-engineered facts (see docs/PROTOCOL.md for sourcing and confidence):
  * GATT service ``0xFFFF``, write characteristic ``0xFF01``, notify
    characteristic ``0xFF02``.
  * Payloads are unencrypted, newline-free JSON objects, UTF-8 encoded.
  * A poll cycle is: connect -> send ``device_get`` -> send ``data_get``
    (init) -> send ``data_get`` (full) -> disconnect. Some units stop
    responding if the connection is held open longer than one poll cycle.

NOT independently verified (best-effort defaults, override via
``docs/PROTOCOL.md`` guidance or the ``jackery.send_raw_command`` service if
your unit uses a different envelope):
  * The exact JSON keys inside each request object.
  * The write ("set") command envelope, since no public source documents
    Jackery BLE write commands. ``build_set_command`` mirrors the shape of
    the read commands (a ``cmd`` + ``data`` envelope), which is the most
    common pattern in this device family's other (cloud/MQTT) protocols, but
    it has not been confirmed against real BLE hardware.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

MAX_FRAME_BUFFER_BYTES = 65536

REQUEST_DEVICE_GET: dict[str, Any] = {"cmd": "device_get"}
REQUEST_DATA_GET_INIT: dict[str, Any] = {"cmd": "data_get", "type": "init"}
REQUEST_DATA_GET_FULL: dict[str, Any] = {"cmd": "data_get", "type": "full"}

POLL_REQUEST_SEQUENCE: tuple[dict[str, Any], ...] = (
    REQUEST_DEVICE_GET,
    REQUEST_DATA_GET_INIT,
    REQUEST_DATA_GET_FULL,
)


def build_set_command(path: str, value: Any) -> dict[str, Any]:
    """Build a best-effort write command for one flattened telemetry field.

    See the module docstring: this envelope shape is not independently
    confirmed against real Jackery BLE hardware.
    """
    return {"cmd": "data_set", "data": {path: value}}


def encode(payload: dict[str, Any]) -> bytes:
    """Encode a command object as the bytes written to the BLE write characteristic."""
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class JsonFrameAssembler:
    """Reassemble JSON objects that may arrive split across BLE notify packets."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        """Add a notify payload chunk and return any complete JSON objects it completes."""
        _LOGGER.debug("BLE notify chunk received (%d bytes): %s", len(chunk), chunk[:200])
        self._buffer.extend(chunk)
        if len(self._buffer) > MAX_FRAME_BUFFER_BYTES:
            _LOGGER.warning(
                "Discarding %d-byte notify buffer after exceeding %d-byte limit "
                "without a parseable JSON object; the device may be sending an "
                "unexpected format",
                len(self._buffer),
                MAX_FRAME_BUFFER_BYTES,
            )
            self._buffer.clear()
            return []

        frames: list[dict[str, Any]] = []
        while True:
            frame, consumed = self._try_extract_one(self._buffer)
            if frame is None:
                break
            frames.append(frame)
            del self._buffer[:consumed]
        if frames:
            _LOGGER.debug("Decoded %d JSON frame(s) from notify buffer: %s", len(frames), frames)
        return frames

    def reset(self) -> None:
        """Drop any partially-buffered data, e.g. after a connection is torn down."""
        if self._buffer:
            _LOGGER.debug("Resetting JSON frame assembler, discarding %d buffered byte(s)", len(self._buffer))
        self._buffer.clear()

    @staticmethod
    def _try_extract_one(buffer: bytearray) -> tuple[dict[str, Any] | None, int]:
        """Return the first complete top-level JSON object in ``buffer``, if any."""
        text_start = None
        for index, byte in enumerate(buffer):
            if byte == 0x7B:  # '{'
                text_start = index
                break
        if text_start is None:
            return None, 0

        decoder = json.JSONDecoder()
        try:
            text = buffer[text_start:].decode("utf-8")
        except UnicodeDecodeError:
            return None, 0
        try:
            # Anchored at a literal '{', so a successful parse is always a dict.
            obj, end_index = decoder.raw_decode(text)
        except json.JSONDecodeError:
            return None, 0
        consumed_bytes = text_start + len(text[:end_index].encode("utf-8"))
        return obj, consumed_bytes
