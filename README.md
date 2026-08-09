# Jackery for Home Assistant

A local, Bluetooth LE, read **and** write custom integration for Jackery
portable power stations (Explorer / Plus / Ultra series). No cloud account,
no MQTT broker - Home Assistant talks directly to the device over BLE.

> **Protocol honesty note:** Jackery has never published a BLE protocol
> specification. This integration is built on community reverse-engineering
> (GATT service/characteristic UUIDs, JSON-over-BLE framing) plus a
> best-effort write command design, since no public source documents
> Jackery BLE *write* commands at all. Read [docs/PROTOCOL.md](docs/PROTOCOL.md)
> before relying on write entities for anything safety-critical, and see
> "Verifying the protocol against your hardware" below.

## Features

- **Bluetooth discovery** - devices advertising as `Jackery_HL*`/`Jackery*`
  or the known GATT service UUID are offered automatically; manual MAC-address
  entry also works.
- **Dynamically discovered entities** - rather than hardcoding field names
  that can't be verified against every model, every telemetry field the
  device reports is turned into a sensor, binary sensor, or (for
  output-like booleans) a switch. New fields discovered on a later poll are
  added automatically, no restart required.
- **Full read/write** - AC/DC/USB-style output fields become switches you
  can toggle from Home Assistant, dashboards, or automations.
- **`jackery.send_raw_command` service** - an escape hatch to send any JSON
  command directly to the device and see the raw response, for testing or
  correcting the protocol against your own hardware.
- **Extensive logging** - every BLE connect, disconnect, write, and notify
  chunk is logged at DEBUG; lifecycle events at INFO; failures at WARNING/ERROR.
- **Redacted diagnostics** download (Settings -> Devices & Services -> Jackery
  -> Download diagnostics) with addresses, tokens, and serials stripped.
- **Optional automatic GitHub issue filing** for unexpected (non-Bluetooth)
  errors - opt-in, disabled by default, and never fires for routine
  connectivity flakiness. See "Automatic GitHub issue reporting" below.

## Installation

### HACS (recommended)

[Open Jackery in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=bouldinnathan&repository=home-assistant-jackery&category=integration)

1. Open the link above and choose **Download** (or add this repo manually
   in HACS -> Integrations -> ⋮ -> Custom repositories, category
   "Integration", then install "Jackery" from the list).
2. Restart Home Assistant.

### Manual

Copy `custom_components/jackery` into your Home Assistant `config/custom_components/`
directory and restart.

## Setup

Settings -> Devices & Services -> Add Integration -> "Jackery". If your unit
was already seen advertising over Bluetooth, it's offered directly;
otherwise enter its MAC address manually (find it via a BLE scanner app, or
your OS's Bluetooth settings while the unit is in pairing/advertising mode).

Options (Configure on the integration entry):

| Option | Default | Notes |
| --- | --- | --- |
| Poll interval | 30s | How often Home Assistant connects and polls the device |
| BLE connect timeout | 15s | |
| BLE command response timeout | 10s | |
| GitHub error reporting | off | See below |

## Entities

Exact entities depend entirely on what your unit reports (see "Why entities
are dynamically discovered" in [docs/PROTOCOL.md](docs/PROTOCOL.md)).
Typically you'll see something like:

- `sensor.<device>_soc` - battery percentage
- `sensor.<device>_output_watts` / `input_watts` - power flow
- `sensor.<device>_cell_temp` - temperature, if reported
- `binary_sensor.<device>_*` - fault flags, charging state, etc.
- `switch.<device>_ac_output` / `dc_output` / `usb_output` - controllable
  outputs, if the field name matches a known output pattern

## Services

- `jackery.refresh` - poll immediately instead of waiting for the next
  scheduled interval. Optional `device_id` if you have more than one unit.
- `jackery.send_raw_command` - send an arbitrary JSON command, e.g.
  `{"cmd": "data_get", "type": "full"}`, and get the raw response back.

## Debug logging

Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.jackery: debug
```

This logs every command sent and every notify chunk received, which is the
fastest way to figure out what your specific unit actually expects - see
[docs/PROTOCOL.md](docs/PROTOCOL.md) for how to compare it against a real
Bluetooth capture from the official app.

## Automatic GitHub issue reporting

Disabled by default. When enabled (Configure -> GitHub error reporting) with
a repository (`owner/name`) and a token, **unexpected** errors (bugs - not
routine Bluetooth connection failures or timeouts) are automatically filed
as GitHub issues: deduplicated by a fingerprint of the exception type and
origin, capped at 5 reports/24h, with secrets/addresses/tokens redacted from
the traceback before it's sent.

Use a **fine-grained personal access token** scoped to only `Issues: write`
on the single repository you point it at - never a classic token, and never
one with broader `repo` scope. Worst case if it leaks: someone can file spam
issues on that one repo, not access your account or other repos.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Disclaimer

This is an unofficial, community-built integration. It is not affiliated
with, endorsed by, or supported by Jackery. Controlling a power station's
outputs via a reverse-engineered protocol carries inherent risk - test
thoroughly before relying on write entities (especially switches) in
unattended automations.

## License

MIT - see [LICENSE](LICENSE).
