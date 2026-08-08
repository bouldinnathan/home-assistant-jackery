"""Tests for the BLE JSON framing/command protocol helpers."""

from __future__ import annotations

import json

from custom_components.jackery.protocol import (
    REQUEST_DATA_GET_FULL,
    REQUEST_DATA_GET_INIT,
    REQUEST_DEVICE_GET,
    JsonFrameAssembler,
    build_set_command,
    encode,
)


def test_encode_round_trips_through_json() -> None:
    payload = {"cmd": "device_get"}
    assert json.loads(encode(payload)) == payload


def test_build_set_command_wraps_path_and_value() -> None:
    command = build_set_command("port.acOutput", True)
    assert command == {"cmd": "data_set", "data": {"port.acOutput": True}}


def test_poll_request_sequence_is_device_get_then_init_then_full() -> None:
    from custom_components.jackery.protocol import POLL_REQUEST_SEQUENCE

    assert POLL_REQUEST_SEQUENCE == (REQUEST_DEVICE_GET, REQUEST_DATA_GET_INIT, REQUEST_DATA_GET_FULL)


def test_assembler_parses_a_single_complete_frame() -> None:
    assembler = JsonFrameAssembler()
    frames = assembler.feed(b'{"soc": 87}')
    assert frames == [{"soc": 87}]


def test_assembler_reassembles_a_frame_split_across_chunks() -> None:
    assembler = JsonFrameAssembler()
    payload = json.dumps({"soc": 87, "acOutput": True}).encode()
    midpoint = len(payload) // 2
    assert assembler.feed(payload[:midpoint]) == []
    assert assembler.feed(payload[midpoint:]) == [{"soc": 87, "acOutput": True}]


def test_assembler_extracts_multiple_frames_from_one_chunk() -> None:
    assembler = JsonFrameAssembler()
    chunk = json.dumps({"a": 1}).encode() + json.dumps({"b": 2}).encode()
    assert assembler.feed(chunk) == [{"a": 1}, {"b": 2}]


def test_assembler_skips_leading_garbage_before_a_frame() -> None:
    assembler = JsonFrameAssembler()
    frames = assembler.feed(b"\x00\x01garbage" + json.dumps({"ok": True}).encode())
    assert frames == [{"ok": True}]


def test_assembler_reset_drops_partial_buffer() -> None:
    assembler = JsonFrameAssembler()
    assembler.feed(b'{"incomplete":')
    assembler.reset()
    # After reset, a previously-partial prefix must not contaminate a new frame.
    assert assembler.feed(b'{"fresh": 1}') == [{"fresh": 1}]


def test_assembler_discards_buffer_once_it_exceeds_the_size_limit() -> None:
    assembler = JsonFrameAssembler()
    huge_incomplete = b'{"key": "' + b"x" * 70000
    frames = assembler.feed(huge_incomplete)
    assert frames == []
    # The oversized, still-incomplete buffer should have been dropped, so a
    # fresh valid frame afterward parses cleanly rather than being appended
    # to 70KB of garbage.
    assert assembler.feed(b'{"ok": true}') == [{"ok": True}]
