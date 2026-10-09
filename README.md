# Orange Livebox for Home Assistant

Custom integration that connects Home Assistant to an Orange Livebox router
through its local API (the same one the web UI at http://192.168.1.1 uses).
No cloud, polling every 30 seconds.

## Features

| Platform | Entities |
| --- | --- |
| Sensor | Last boot, external IPv4/IPv6, link type, connected devices, data received/sent, missed calls, firewall level |
| Sensor (xDSL) | Download/upload rate and max rate, noise margins, attenuation |
| Sensor (fiber) | Optical received/transmitted power, ONU state, module temperature |
| Binary sensor | Internet connection, TV service, one per phone line |
| Switch | Wi-Fi, guest Wi-Fi |
| Button | Restart, ring phone |
| Device tracker | Every device known by the Livebox (disabled by default, enable those you want) |

Entities are only created when your model answers the corresponding call, so
the list varies between Livebox models (tested on a Livebox Nautilus on fiber)
and DSL/fiber lines. Diagnostics (with personal data redacted) can be
downloaded from the device page.

## Installation

### HACS

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jeremv42&repository=ha-orange-livebox&category=integration)

Click the button above, or add `https://github.com/jeremv42/ha-orange-livebox`
as a custom repository (type *Integration*) in HACS. Then install
*Orange Livebox* and restart Home Assistant.

### Manual

Copy `custom_components/orange_livebox` into your Home Assistant
`config/custom_components/` folder and restart.

## Configuration

Once the integration is installed **and Home Assistant restarted**:

[![Open your Home Assistant instance and start setting up Orange Livebox.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=orange_livebox)

Or *Settings → Devices & services → Add integration → Orange Livebox*.

- **Host**: `192.168.1.1` by default
- **Username**: `admin`
- **Password**: the admin password (by default the first 8 characters of the
  Wi-Fi key printed under the box)

## Development

```bash
scripts/setup          # create .venv with Home Assistant + test tooling
.venv/bin/pytest       # run the tests
scripts/lint           # ruff format + lint
scripts/develop        # run a local Home Assistant on http://localhost:8123
```

To see what your own box returns (and find new data worth exposing):

```bash
.venv/bin/python scripts/probe.py > probe-full.json   # asks for the password
.venv/bin/python scripts/probe.py --call NeMo.Intf.data getMIBs '{"mibs":"dsl"}'
```

Probe dumps contain MAC/IP addresses and the serial number; `probe-*.json`
is git-ignored.
