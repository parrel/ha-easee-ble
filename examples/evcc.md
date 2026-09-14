# evcc configuration

[evcc](https://evcc.io) drives any charger Home Assistant exposes, through its
[Home Assistant charger](https://docs.evcc.io/en/chargers/home-assistant-charger/)
template. It needs a status sensor, a switch and a number - this integration has
all three.

## The charger

In evcc: **Configuration → Add charger → Home Assistant**. Pick your instance,
authorise in the tab that opens, assign the entities. evcc stores and renews the
token itself.

The same thing in `evcc.yaml`, with `EH123456` for your charger's serial:

```yaml
chargers:
  - name: easee
    type: template
    template: homeassistant
    uri: http://homeassistant.local:8123
    status: sensor.eh123456_status
    enabled: switch.eh123456_charger_enabled
    enable: switch.eh123456_charger_enabled
    setMaxCurrent: number.eh123456_dynamic_charger_current
    power: sensor.eh123456_power
    energy: sensor.eh123456_lifetime_energy
    currentL1: sensor.eh123456_current_l1
    currentL2: sensor.eh123456_current_l2
    currentL3: sensor.eh123456_current_l3
    statusB: awaiting_start, ready_to_charge, awaiting_authorization, de_authorizing, completed
    statusA: disconnected, offline, error
    phaseswitch: select.easee_phases # see below
```

## Phase switching

`phaseswitch` wants a select with the options `1` and `3`. **Phase mode** has
`1_phase`, `auto` and `3_phase`. evcc switches by writing that select and
nothing else, and the phase switch only takes effect once the charger has been turned off and on again. So the bridge in `configuration.yaml` writes the mode, then switches
the charger off:

```yaml
template:
  - select:
      - name: Easee phases
        unique_id: easee_evcc_phases
        state: >
          {% set mode = states('select.eh123456_phase_mode') %}
          {{ '1' if mode == '1_phase' else '3' if mode in ['3_phase', 'auto'] else none }}
        options: "{{ ['1', '3'] }}"
        select_option:
          - action: select.select_option
            target:
              entity_id: select.eh123456_phase_mode
            data:
              option: "{{ '3_phase' if option == '3' else '1_phase' }}"
          # evcc switches it back on, and the mode applies on the way up.
          - action: switch.turn_off
            target:
              entity_id: switch.eh123456_charger_enabled
```

Leave evcc's `interval` at its default 30 seconds. The re-enable has to land
inside that 60-second window, and it only happens on a loadpoint cycle. The pause therefore lasts until evcc's next
cycle, up to the `interval` in `evcc.yaml`.
