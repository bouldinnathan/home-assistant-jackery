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
  or the known GATT service UUID are offered automatically. The manual-entry
  step also lists *every* nearby Bluetooth device Home Assistant currently
  sees (not just Jackery-looking ones, clearly marked "not confirmed
  Jackery"), so a unit advertising under an unexpected name still shows up -
  and manual MAC-address entry always works too.
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
- `jackery.scan_bluetooth_devices` - list every Bluetooth device Home
  Assistant currently sees nearby (name, address, signal strength,
  advertised service UUIDs), not just ones already recognized as Jackery.
  Requires at least one Jackery unit already configured (to register the
  service), but isn't tied to that unit - it's a general discovery/debug
  tool. Call it from Developer Tools -> Actions with "Response data" checked
  to see the list.

### WiFi-connected units

Some Jackery models also support WiFi via the Jackery app. That path talks
to **Jackery's cloud service**, not anything discoverable on your local
network - there's no local HTTP/mDNS/UPnP API to connect to directly (this
was confirmed by checking how existing third-party integrations for these
same portable power-station models work: they authenticate against
Jackery's cloud with your account credentials, and require internet
connectivity). Supporting that would mean depending on Jackery's cloud
staying online and your account credentials living in Home Assistant -
exactly what this integration was built to avoid (see "Why there's no
cloud/MQTT fallback here" in [docs/PROTOCOL.md](docs/PROTOCOL.md)). BLE
remains the only local path for these models.

If you believe your specific unit exposes something on the local network
that isn't cloud traffic, a Wireshark capture is the way to check:

1. On the phone/tablet running the Jackery app, connect to the same WiFi
   network as the unit.
2. Capture with Wireshark on a machine that can see that traffic - either
   run Wireshark on a Wi-Fi adapter in monitor mode, or (easier) set up the
   phone to route through a machine running Wireshark (a shared "hotspot"
   from a laptop, or a mitmproxy/Wireshark-capable VPN profile on the
   phone).
3. Filter to the power station's IP (find it via your router's client list,
   matched by MAC address on the unit's label) with `ip.addr == <that IP>`.
4. Open the app, let it talk to the unit, and watch what shows up. Plain
   HTTP or an unencrypted local protocol on that IP would be genuinely new
   information; TLS/HTTPS traffic to an external IP confirms it's cloud-only.

Open an issue with what you find (redact anything sensitive) and this can
be revisited.

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
