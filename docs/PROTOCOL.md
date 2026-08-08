# Jackery BLE protocol notes

Jackery has never published a public API or BLE protocol specification for
its portable power stations. Everything this integration knows comes from
community reverse-engineering of the official mobile app's Bluetooth
traffic. This document separates what's independently confirmed from what's
a best-effort default, so you know what to trust and what to verify against
your own hardware.

## Confirmed (community-documented, used as-is)

- GATT service UUID `0000ffff-0000-1000-8000-00805f9b34fb`.
- Write characteristic `0000ff01-0000-1000-8000-00805f9b34fb`.
- Notify characteristic `0000ff02-0000-1000-8000-00805f9b34fb`.
- Payloads are unencrypted, UTF-8 JSON objects with no framing beyond JSON's
  own `{...}` structure.
- A poll cycle is connect -> `device_get` -> `data_get` (init) -> `data_get`
  (full) -> disconnect. Holding the connection open past one cycle has been
  reported to make some units stop responding, which is why this integration
  reconnects for every poll and every write instead of keeping a persistent
  session (see `custom_components/jackery/ble_client.py`).
- Devices commonly advertise as `Jackery_HL*` or `Jackery*`.

Source: the `Wlad2288/Ultra_Jack` project's reverse-engineering of the
Explorer 2000 Ultra.

## Best-effort, NOT independently confirmed

- **The exact JSON keys inside each request object.** `protocol.py` sends
  `{"cmd": "device_get"}`, `{"cmd": "data_get", "type": "init"}`, and
  `{"cmd": "data_get", "type": "full"}`. The command *names* are documented;
  the surrounding envelope is a reasonable guess, not a confirmed capture.
- **The write ("set") command envelope.** No public source documents a
  Jackery BLE write command at all - every reverse-engineering project found
  during research covers read-only BLE telemetry. `build_set_command()`
  sends `{"cmd": "data_set", "data": {"<field>": <value>}}`, mirroring the
  shape used by this device family's other (cloud/MQTT) protocols. This is
  the single biggest unknown in the integration and the reason write
  entities are described as best-effort throughout the code and UI.
- **Field names themselves** (`soc`, `acOutput`, etc.) are not fixed by this
  integration at all - see "Why entities are dynamically discovered" below.

## Why entities are dynamically discovered

Because the telemetry schema isn't documented, `sensor.py`,
`binary_sensor.py`, and `switch.py` don't hardcode field names. Instead,
every field a device actually reports is flattened (`models.flatten`) and
classified by a small set of key-name heuristics (`models.classify_field`):
things that look like `*soc*`/`*battery*level*` become a battery-percent
sensor, `*watt*`/`*pwr*` becomes a power sensor, boolean fields matching an
output-ish name (`acOutput`, `dcSwitch`, ...) become a switch, other
booleans become a read-only binary sensor, and so on. This means the
integration should produce *something* useful against real hardware even
though the exact schema is unknown, and new fields discovered on a later
poll are added automatically without a restart.

If your unit uses field names the heuristics misclassify, extend
`DEFAULT_SWITCH_KEY_HINTS` in `const.py`, or open an issue with the raw
field names from your DEBUG logs.

## How to verify or correct the protocol against your own hardware

1. Turn on DEBUG logging for this integration (see the README). Every byte
   sent and every notify chunk received is logged.
2. Capture your phone's Bluetooth HCI snoop log while using the official
   Jackery app (Android: Developer Options -> "Enable Bluetooth HCI
   snoop log"; open in Wireshark).
3. Compare the JSON your phone sends/receives against what this
   integration logs. If the request/response envelopes differ, or the
   write command doesn't do what you expect, use the `jackery.send_raw_command`
   service to experiment with the correct envelope without a code change,
   then open a PR or issue with what you found - ideally including the
   corrected command shape and which model/firmware it's for.

## Why there's no cloud/MQTT fallback here

Some Jackery product lines (HomePower, SolarVault) expose a documented
cloud REST + MQTT protocol with real write support. This integration
deliberately doesn't use it: it targets local BLE control only, so it has
no dependency on Jackery's cloud staying online, no account credentials
to manage, and no MQTT broker to configure.
