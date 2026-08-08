"""Tests for the BLE transport session logic, with a fake bleak client."""

from __future__ import annotations

import asyncio
import json

import pytest

from custom_components.jackery.ble_client import (
    JackeryBLEClient,
    JackeryCommandTimeoutError,
    JackeryConnectionError,
)


class _FakeBleakClient:
    """Duck-types the subset of BleakClient used by JackeryBLEClient."""

    def __init__(self, responses: dict[str, list[dict]] | None = None, *, notify_delay: float = 0) -> None:
        self._responses = responses or {}
        self._notify_delay = notify_delay
        self._notify_callback = None
        self.written_commands: list[dict] = []
        self.disconnected = False

    async def start_notify(self, _char_uuid, callback) -> None:
        self._notify_callback = callback

    async def stop_notify(self, _char_uuid) -> None:
        self._notify_callback = None

    async def write_gatt_char(self, _char_uuid, payload: bytes, response: bool = True) -> None:
        command = json.loads(payload)
        self.written_commands.append(command)
        replies = self._responses.get(command.get("cmd"), [])

        async def _send_replies() -> None:
            if self._notify_delay:
                await asyncio.sleep(self._notify_delay)
            for reply in replies:
                if self._notify_callback is not None:
                    self._notify_callback(None, bytearray(json.dumps(reply).encode()))

        asyncio.get_event_loop().create_task(_send_replies())

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture
def fake_ble_device():
    return object()


async def test_run_session_collects_one_response_per_command(monkeypatch, fake_ble_device) -> None:
    fake_client = _FakeBleakClient(
        responses={
            "device_get": [{"model": "Explorer 2000"}],
            "data_get": [{"soc": 87}],
        }
    )

    async def _fake_establish_connection(_client_cls, _ble_device, _address):
        return fake_client

    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection",
        _fake_establish_connection,
    )

    client = JackeryBLEClient("AA:BB:CC:DD:EE:FF")
    frames = await client.async_run_session(
        fake_ble_device,
        [{"cmd": "device_get"}, {"cmd": "data_get"}],
        connect_timeout=1,
        command_timeout=1,
    )

    assert frames == [{"model": "Explorer 2000"}, {"soc": 87}]
    assert fake_client.disconnected is True


async def test_run_session_raises_on_connect_failure(monkeypatch, fake_ble_device) -> None:
    async def _fake_establish_connection(_client_cls, _ble_device, _address):
        raise OSError("no route to device")

    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection",
        _fake_establish_connection,
    )

    client = JackeryBLEClient("AA:BB:CC:DD:EE:FF")
    with pytest.raises(JackeryConnectionError):
        await client.async_run_session(fake_ble_device, [{"cmd": "device_get"}], connect_timeout=1, command_timeout=1)


async def test_run_session_raises_on_command_timeout(monkeypatch, fake_ble_device) -> None:
    fake_client = _FakeBleakClient(responses={})  # no replies configured, so it will never answer

    async def _fake_establish_connection(_client_cls, _ble_device, _address):
        return fake_client

    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection",
        _fake_establish_connection,
    )

    client = JackeryBLEClient("AA:BB:CC:DD:EE:FF")
    with pytest.raises(JackeryCommandTimeoutError):
        await client.async_run_session(
            fake_ble_device, [{"cmd": "device_get"}], connect_timeout=1, command_timeout=0.2
        )
    # Must still disconnect after a timeout rather than leaking the connection.
    assert fake_client.disconnected is True


async def test_sessions_are_serialized_by_the_internal_lock(monkeypatch, fake_ble_device) -> None:
    fake_client = _FakeBleakClient(responses={"device_get": [{"ok": True}]}, notify_delay=0.05)
    connect_calls = 0

    async def _fake_establish_connection(_client_cls, _ble_device, _address):
        nonlocal connect_calls
        connect_calls += 1
        return fake_client

    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection",
        _fake_establish_connection,
    )

    client = JackeryBLEClient("AA:BB:CC:DD:EE:FF")
    results = await asyncio.gather(
        client.async_run_session(fake_ble_device, [{"cmd": "device_get"}], connect_timeout=1, command_timeout=1),
        client.async_run_session(fake_ble_device, [{"cmd": "device_get"}], connect_timeout=1, command_timeout=1),
    )

    assert results == [[{"ok": True}], [{"ok": True}]]
    assert connect_calls == 2
