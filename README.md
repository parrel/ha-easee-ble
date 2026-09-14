# Easee EV Charger (Bluetooth)

Control an Easee EV charger from Home Assistant over **Bluetooth**. All you need is the PIN printed on the charger or shown in the app.

[![HACS: custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Validate](https://github.com/parrel/ha-easee-ble/actions/workflows/validate.yml/badge.svg)](https://github.com/parrel/ha-easee-ble/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2.svg)](https://github.com/sponsors/parrel)

**Unofficial.** Reverse-engineered. Not affiliated with or endorsed by Easee. No warranty, changing charger settings is at your own risk.

## Contents

- [Supported devices](#supported-devices)
- [Compared to the alternatives](#compared-to-the-alternatives)
- [Before you start](#before-you-start)
- [Installation](#installation)
- [Setup](#setup)
- [Entities](#entities)
- [Actions](#actions)
- [Options](#options)
- [Examples](#examples)
  - [evcc configuration](#evcc-configuration)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Licence](#licence)

## Supported devices

Easee wall chargers: developed against an Easee Charge Max, others speak the same protocol and are expected to work.

## Compared to the alternatives
| | This integration | [Easee](https://github.com/nordicopen/easee_hass) (pyeasee) | [OCPP](https://github.com/lbbrhzn/ocpp)¹ |
|---|:-:|:-:|:-:|
| Local control | ✅ | ❌ | ✅ |
| Start and stop charging | ✅ | ✅ | ✅ |
| Current limits | ✅ | ✅ | ✅ |
| Phase switching | ✅ | ✅ | ❌ |
| Power and energy | ✅ | ⚠️² | ✅ |
| Update rate | >5s | Live push | >30 s |
| RFID key enrollment | ✅ | ❌ | ❌ |
| Charge schedules | ❌ | ✅ | ❌ |

¹ Easee's native OCPP, firmware 344 and later. It is switched on through
Easee's cloud API.

² The cloud updates lifetime energy at irregular times, not on the hour, so
the Energy dashboard books part of it in the wrong hour.

## Before you start

You need a **Bluetooth proxy** in range of the charger - an
ESPHome Bluetooth proxy is the
usual choice.

Two things are worth checking now, because they are the cause of nearly every
failed setup:

- **A Bluetooth adapter plugged into the Home Assistant machine will most likely not work.**
  The charger doesn't expose the descriptors Linux's Bluetooth stack needs to
  subscribe to notifications, so replies never arrive. Use a proxy.
- **The proxy must not be scanning 100% of the time.** ESPHome's defaults
  (`interval: 320ms`, `window: 30ms`) are fine. The ready-made
  `bluetooth-proxy` config scans continuously and never leaves the charger the
  airtime it needs to answer.

## Installation

### HACS

[![Open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=parrel&repository=ha-easee-ble&category=integration)

The button opens this repository in your own HACS - click **Download**, then
restart Home Assistant. By hand instead:

1. In HACS, open the ⋮ menu → **Custom repositories**.
2. Add `https://github.com/parrel/ha-easee-ble` with category **Integration**.
3. Search for **Easee EV Charger (Bluetooth)** and install it.
4. Restart Home Assistant.

### Manually

Copy `custom_components/easee_ble/` into your `config/custom_components/` and
restart Home Assistant. The `easee-ble` library is installed for you.

## Setup

First, get the charger advertising. Chargers only advertise over Bluetooth
intermittently unless told otherwise, so do one of:

- In the Easee app, set Bluetooth to **always on** (recommended), or
- **long-press the charger's touch button** for 5 seconds, which opens a window
  of a few minutes.

Then go to **Settings → Devices & services**. The charger is usually already
waiting under **Discovered**; if not, click **Add integration** and search for
**Easee EV Charger (Bluetooth)**, or use the button:

[![Add the Easee EV Charger (Bluetooth) integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=easee_ble)

Enter the **PIN printed on the label or shown in the app** - not
your Easee app password. Home Assistant connects once to verify it, and you're
done.

## Entities

### Controls

| Entity | |
|---|---|
| **Charger enabled** | Switch the charger on and off |
| **Max charger current** | The charger's own current limit, in amps |
| **Dynamic charger current** | A temporary limit on top of it - the one to automate |
| **Phase mode** | 1-phase, automatic, or 3-phase - see below |
| **Dynamic circuit current** | The same, one level up: the circuit shared by several chargers |
| **Cable locked** | Lock the cable permanently into the socket |
| **Idle current** | Keep a trickle flowing to a parked car |
| **Require authorisation** | No charging until a key is presented - the app's private access |
| **LED** | The status LED strip, dimmable; 0% is off |
| **Bluetooth mode** | Button press only, or always on |
| **Reboot**, **Identify** | Restart the charger; play the LED animation to find it |

A new **Phase mode** only takes effect once the charger has been turned off and on again, which can be accomplished with the **Charger enabled** switch or by limiting one of the limits below the minimum required limits (usually <6A). The charger does not do this by itself.

### Sensors

| Entity | |
|---|---|
| **Status** | What the car and cable are doing: charging, awaiting start, disconnected... |
| **Charging blocked by** | *Why* no current is flowing |
| **Power** | kW flowing right now |
| **Lifetime energy**, **Session energy** | kWh; lifetime energy feeds the Energy dashboard |
| **Current L1/L2/L3** | Per-phase current |
| **Circuit max current**, **Cable rating** | The installer's limit and the cable's rating |

Also created but **disabled by default**: line-to-line and line-to-neutral
voltages, current N, equalizer limits, energy last hour, lifetime hours, LED
mode, OCPP, fallback circuit current, Bluetooth signal, firmware, WiFi network,
IP and MAC address. Enable any of them from the device page.

### Reading Status and "Charging blocked by" together

**Status** describes the **car and cable**, not your settings. Switch the charger
off and it still reads *Awaiting start* - that is not a bug, and it is what
Easee's own app reports too. What changes is **Charging blocked by**, which goes
to *Charger disabled*.

Together they tell apart the situations that all look like "awaiting start":
switched off, waiting for authorisation, queued behind load balancing, or capped
by the circuit.

## Actions

The charger keeps its own list of RFID keys, the ones that work with no network
at all. Nothing reports that list as a state, so it is reached through actions:
`easee_ble.list_rfid_keys`, `easee_ble.add_rfid_key` and
`easee_ble.remove_rfid_key`. Each takes the charger as its target.

```yaml
action: easee_ble.list_rfid_keys
data:
  device_id: "{{ device_id('sensor.eh123456_status') }}"
response_variable: enrolled       # {"keys": ["Alice", "Bob"]}
```

Adding takes a name and the tag's UID in hex; removing takes the UID alone.
A tag paired through the Easee app is enrolled against your **account in the
cloud**, not against the charger, and will not appear here.

Turn **Require authorisation** on to make the charger actually ask for a key.

## Options

**Settings → Devices & services → Easee EV Charger (Bluetooth) → Configure**
sets the poll interval, 30 seconds by default. Home Assistant keeps the
Bluetooth connection open, so a poll costs about 0.4 seconds - short intervals
are cheap here.

## Examples

### evcc configuration

An example of how this integration can be used with evcc can be found in [examples/evcc.md](examples/evcc.md).

## Known limitations

- **The charger accepts one Bluetooth connection at a time.** While Home
  Assistant holds it, the Easee app cannot connect. To use the app, disable the
  config entry for as long as you need it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Could not reach the charger" during setup | The charger isn't advertising, or is out of range of a proxy |
| "The charger rejected that PIN" | Wrong PIN - it's on the label, or in the app, not your app password |
| Entities go unavailable in bursts | Weak signal; move a proxy closer and check the **Bluetooth signal** sensor |
| Nothing ever connects | A local Bluetooth adapter instead of a proxy, or a proxy scanning 100% of the time |

For a closer look, turn on debug logging:

```yaml
logger:
  logs:
    custom_components.easee_ble: debug
    easee_ble: debug
```

**Settings → Devices & services → the charger → ⋮ → Download diagnostics** dumps
everything the last poll saw, with identifying fields redacted. It's the most
useful thing to attach to an issue.


## Contributing

Issues and pull requests are welcome at
[github.com/parrel/ha-easee-ble](https://github.com/parrel/ha-easee-ble/issues).
The protocol work lives in [easee-ble](https://github.com/parrel/easee-ble).

Some frame fields are still unnamed. The library logs a line whenever an
unidentified field changes:

```
charger <serial>: unidentified field(s) moved: CONFIG#14 (absent) -> 1
```

Change one setting, read the line, and you've found the field that carries it -
a very welcome issue report.

### Development

```bash
scripts/setup      # provision the devcontainer
scripts/develop    # run Home Assistant against ./config with this linked in
pytest             # run the test suite
```

`easee-ble` comes from PyPI at the pin in `manifest.json`, so the devcontainer
runs what Home Assistant installs. To work on the library at the same time,
`pip install -e /workspaces/easee-ble[dev]` over it - `scripts/develop` tells
Home Assistant to leave that package alone, so the checkout survives a restart
whatever version it calls itself.

## Licence

MIT - see [LICENSE](LICENSE).
