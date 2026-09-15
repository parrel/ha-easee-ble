<p align="center">
  <img src="https://raw.githubusercontent.com/parrel/ha-easee-ble/main/custom_components/easee_ble/brand/icon.png" alt="" width="96">
</p>

<h1 align="center">Easee EV Charger (Bluetooth)</h1>

<p align="center">
  Control your Easee EV charger from Home Assistant - <b>locally, over Bluetooth</b>.<br>
  No Easee account, no internet. Just the PIN on the charger.
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS: custom"></a>
  <a href="https://github.com/parrel/ha-easee-ble/releases"><img src="https://img.shields.io/github/v/release/parrel/ha-easee-ble" alt="Latest release"></a>
  <a href="https://github.com/parrel/ha-easee-ble/actions/workflows/validate.yml"><img src="https://github.com/parrel/ha-easee-ble/actions/workflows/validate.yml/badge.svg" alt="Validate"></a>
  <a href="https://github.com/parrel/ha-easee-ble/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/sponsors/parrel"><img src="https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2.svg" alt="Sponsor"></a>
</p>

> [!WARNING]
> **Unofficial.** Reverse-engineered, and not affiliated with or endorsed by
> Easee. No warranty - changing charger settings is at your own risk.

## Features

- **Fully local** - Home Assistant talks straight to the charger. Keeps working when the internet or Easee's cloud doesn't.
- **Charging control** - start and stop, set current limits, switch between 1 and 3 phases.
- **Energy dashboard ready** - power, per-phase current and lifetime energy, booked in the right hour.
- **Offline RFID keys** - enrol and remove tags on the charger itself.
- **Found automatically** - the charger shows up under *Discovered*; enter the PIN and you're done.
- **Plays nicely with others** - settings sync with the Easee app, and an external OCPP operator can stay connected.

## Contents

- [Supported devices](#supported-devices)
- [Compared to the alternatives](#compared-to-the-alternatives)
- [Getting started](#getting-started)
  - [1. Set up a Bluetooth proxy](#1-set-up-a-bluetooth-proxy)
  - [2. Install the integration](#2-install-the-integration)
  - [3. Add your charger](#3-add-your-charger)
- [Entities](#entities)
- [Actions](#actions)
- [Options](#options)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Licence](#licence)

## Supported devices

| Charger | Status |
|---|---|
| Easee Charge Max | ✅ Tested - developed against this one |
| Other Easee wall chargers | 🟡 Expected to work - they speak the same protocol |

> [!TIP]
> Got it running on a model not listed here?
> [Open an issue](https://github.com/parrel/ha-easee-ble/issues) so it can be added.

## Compared to the alternatives

| | This integration | [Easee](https://github.com/nordicopen/easee_hass) (pyeasee) | [OCPP](https://github.com/lbbrhzn/ocpp)¹ |
|---|:-:|:-:|:-:|
| Local control | ✅ | ❌ | ✅ |
| Start and stop charging | ✅ | ✅ | ✅ |
| Current limits | ✅ | ✅ | ✅ |
| Phase switching | ✅ | ✅ | ❌ |
| Power and energy | ✅ | ⚠️² | ✅ |
| Update rate | 5 s and up | Live push | 30 s and up |
| RFID key enrollment | ✅ | ❌ | ❌ |
| Charge schedules | ❌ | ✅ | ❌ |
| Works alongside an external operator | ✅ | ✅ | ⚠️³ |

¹ Easee's native OCPP, firmware 344 and later. It is switched on through
Easee's cloud API.

² The cloud updates lifetime energy at irregular times, not on the hour, so
the Energy dashboard books part of it in the wrong hour.

³ The charger accepts only one OCPP connection. Bluetooth and the cloud don't
use it, so an external operator (a company-car or employer backend) can stay
connected. Pointing OCPP at Home Assistant takes that single slot, so you'd
need something like [evcc](https://evcc.io) in between to proxy the operator's
connection.

## Getting started

Three steps:

1. **[Set up a Bluetooth proxy](#1-set-up-a-bluetooth-proxy)** within range of the charger.
2. **[Install the integration](#2-install-the-integration)** through HACS.
3. **[Add your charger](#3-add-your-charger)** and enter its PIN.

### 1. Set up a Bluetooth proxy

You need a **Bluetooth proxy** in range of the charger - an
[ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
is the usual choice. Two things cause nearly every failed setup, so check them
now:

> [!IMPORTANT]
> - **A Bluetooth adapter plugged into the Home Assistant machine will most likely not work.**
>   The charger doesn't expose the descriptors Linux's Bluetooth stack needs to
>   subscribe to notifications, so replies never arrive. Use a proxy.
> - **The proxy must not scan 100% of the time.** ESPHome's defaults
>   (`interval: 320ms`, `window: 30ms`) are fine. The ready-made
>   `bluetooth-proxy` firmware scans continuously and never leaves the charger
>   the airtime it needs to answer.

Add or adjust these blocks in your proxy's YAML. If you started from the
ready-made firmware, the `scan_parameters` here override its continuous
scanning:

```yaml
esp32_ble_tracker:
  scan_parameters:
    interval: 320ms
    window: 30ms
    active: true

bluetooth_proxy:
  active: true   # lets Home Assistant connect through the proxy
```

### 2. Install the integration

#### Using HACS (recommended)

[![Open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=parrel&repository=ha-easee-ble&category=integration)

The button opens this repository in your own HACS - click **Download**, then
restart Home Assistant. Or add the repository by hand:

1. In HACS, open the ⋮ menu → **Custom repositories**.
2. Add `https://github.com/parrel/ha-easee-ble` with category **Integration**.
3. Search for **Easee EV Charger (Bluetooth)** and install it.
4. Restart Home Assistant.

#### Manually

Copy `custom_components/easee_ble/` into your `config/custom_components/` and
restart Home Assistant. The `easee-ble` library is installed for you.

### 3. Add your charger

First, get the charger advertising. Chargers only advertise over Bluetooth
now and then, so do one of:

- In the Easee app, set Bluetooth to **always on**, or
- **long-press the charger's touch button** for 5 seconds, which opens a window
  of a few minutes.

> [!TIP]
> Go for **always on**. Home Assistant can then reconnect by itself after a
> dropped link, without anyone walking to the charger. You can also change it
> later with the **Bluetooth mode** entity.

Then go to **Settings → Devices & services**. The charger is usually already
waiting under **Discovered**. If not, click **Add integration** and search for
**Easee EV Charger (Bluetooth)**, or use the button:

[![Add the Easee EV Charger (Bluetooth) integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=easee_ble)

Enter the charger's PIN. Home Assistant connects once to check it, and you're
done.

> [!NOTE]
> The PIN is the one **printed on the label or shown in the app** - not your
> Easee app password.

## Entities

The charger shows up as a device named after its serial number, e.g.
`EH123456`, so its entities are called `sensor.eh123456_status`,
`number.eh123456_dynamic_charger_current` and so on.

### Controls

| Entity | What it does |
|---|---|
| **Charger enabled** | Switch the charger on and off |
| **Max charger current** | The charger's own current limit, in amps |
| **Dynamic charger current** | A temporary limit on top of it - the one to automate |
| **Phase mode** | 1-phase, automatic, or 3-phase - see the note below |
| **Dynamic circuit current** | The same, one level up: the circuit shared by several chargers |
| **Cable locked** | Lock the cable permanently into the socket |
| **Idle current** | Keep a trickle flowing to a parked car |
| **Require authorisation** | No charging until a key is presented - the app's private access |
| **LED** | The status LED strip, dimmable; 0% is off |
| **Bluetooth mode** | Button press only, or always on |
| **Reboot**, **Identify** | Restart the charger; play the LED animation to find it |

> [!NOTE]
> A new **Phase mode** only takes effect once the charger has been switched off
> and on again, and it won't do that by itself. Toggle **Charger enabled**, or
> briefly set one of the current limits below the charging minimum (usually 6 A).

> [!TIP]
> Settings sync with Easee's cloud both ways. A change made here shows up in
> the Easee app, and a change made in the app shows up here on the next poll.

### Sensors

| Entity | What it shows |
|---|---|
| **Status** | What the car and cable are doing: charging, awaiting start, disconnected... |
| **Charging blocked by** | *Why* no current is flowing |
| **Power** | kW flowing right now |
| **Lifetime energy**, **Session energy** | kWh; lifetime energy feeds the Energy dashboard |
| **Current L1/L2/L3** | Per-phase current |
| **Circuit max current**, **Cable rating** | The installer's limit and the cable's rating |

Also created but **disabled by default** - enable any of them from the device
page:

- Voltages, line-to-line and line-to-neutral
- Current N
- Equalizer limits L1/L2/L3
- Fallback circuit current
- Energy last hour, lifetime hours
- LED mode, OCPP
- Bluetooth signal, firmware
- WiFi network, IP address, MAC address

### Reading Status and "Charging blocked by" together

**Status** describes the **car and cable**, not your settings. Switch the
charger off and it still reads *Awaiting start* - that's not a bug, it's what
Easee's own app reports too. What changes is **Charging blocked by**.

So when Status says *Awaiting start*, look at **Charging blocked by**:

| Charging blocked by | What's going on |
|---|---|
| *Charger disabled* | The charger is switched off |
| *Pending authorisation*, *Waiting for schedule or authorisation* | Waiting for an RFID key or approval in the app |
| *Waiting in queue*, *Limited by load balancing* | Queued behind other chargers by load balancing |
| *Max circuit limit too low*, *Limited by circuit max limit* | Capped by the circuit |

## Actions

The charger keeps its own list of RFID keys - the ones that work with no
network at all. It isn't exposed as an entity, so you manage it with three
actions. Each needs the charger's `device_id`.

**List the enrolled keys**

```yaml
action: easee_ble.list_rfid_keys
data:
  device_id: "{{ device_id('sensor.eh123456_status') }}"
response_variable: enrolled       # {"keys": ["Alice", "Bob"]}
```

**Add a key** - takes a name and the tag's UID in hex:

```yaml
action: easee_ble.add_rfid_key
data:
  device_id: "{{ device_id('sensor.eh123456_status') }}"
  name: Alice
  token: 04a1b2c3d4e5f6
```

**Remove a key** - takes the UID alone:

```yaml
action: easee_ble.remove_rfid_key
data:
  device_id: "{{ device_id('sensor.eh123456_status') }}"
  token: 04a1b2c3d4e5f6
```

> [!NOTE]
> This only shows/modifies local keys, not account keys. And turn
> **Require authorisation** on, or the charger never asks for a key at all.

## Options

**Settings → Devices & services → Easee EV Charger (Bluetooth) → Configure**
sets the poll interval, 30 seconds by default. Home Assistant keeps the
Bluetooth connection open, so a poll costs about 0.4 seconds - short intervals
are cheap here.

## Known limitations

> [!WARNING]
> **The charger accepts one Bluetooth connection at a time.** While Home
> Assistant holds it, the Easee app cannot connect to the charger over
> Bluetooth. To use the app that way, disable the integration entry for as
> long as you need it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "Could not reach the charger" during setup | The charger isn't advertising, or is out of range of a proxy |
| "The charger rejected that PIN" | Wrong PIN - it's on the label, or in the app, not your app password |
| Entities go unavailable in bursts | Weak signal; move a proxy closer and check the **Bluetooth signal** sensor |
| Nothing ever connects | A local Bluetooth adapter instead of a proxy, or a proxy scanning 100% of the time |

Still stuck? [Open an issue](https://github.com/parrel/ha-easee-ble/issues)
and attach these two:

1. **Diagnostics** - **Settings → Devices & services → the charger → ⋮ →
   Download diagnostics** dumps everything the last poll saw, with identifying
   fields redacted. It's the most useful thing you can attach.
2. **Debug logs** - add this to `configuration.yaml`, restart, and reproduce
   the problem:

   ```yaml
   logger:
     logs:
       custom_components.easee_ble: debug
       easee_ble: debug
   ```

## Contributing

Issues and pull requests are welcome at
[github.com/parrel/ha-easee-ble](https://github.com/parrel/ha-easee-ble/issues).
The protocol work lives in [easee-ble](https://github.com/parrel/easee-ble).

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

MIT - see [LICENSE](https://github.com/parrel/ha-easee-ble/blob/main/LICENSE).

If this integration saves you a walk to the garage, consider
[sponsoring its development](https://github.com/sponsors/parrel).
