"""Tests for the entity behaviour that is not just a field read."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import easee_ble
from custom_components.easee_ble.const import DOMAIN

from .conftest import POLL_DATA


@pytest.fixture
async def loaded(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> MockConfigEntry:
    """A set-up config entry."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    return mock_entry


async def _set_reading(
    hass: HomeAssistant, entry: MockConfigEntry, charger: MagicMock, **fields
) -> None:
    """Make the next poll report these fields, and run it."""
    charger.poll.return_value = {**POLL_DATA, **fields}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_led_maps_percent_to_brightness(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """60% shows as 153 of 255, and 0% reads as off."""
    state = hass.states.get("light.eh123456_led")
    assert state.state == "on"
    assert state.attributes[ATTR_BRIGHTNESS] == 153

    await _set_reading(hass, loaded, mock_charger, ledStripBrightness=0)
    assert hass.states.get("light.eh123456_led").state == "off"


async def test_led_restores_the_last_brightness(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """Switching back on returns to the last non-zero level, not to full."""
    await _set_reading(hass, loaded, mock_charger, ledStripBrightness=0)

    await hass.services.async_call(
        "light", "turn_on", {ATTR_ENTITY_ID: "light.eh123456_led"}, blocking=True
    )
    await hass.async_block_till_done()
    # 60 was the last level seen before it went to 0.
    assert mock_charger.perform.await_count == 1
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.set_led_brightness.assert_called_once_with(60)


async def test_led_explicit_brightness_never_rounds_to_off(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A brightness of 1/255 is 0% when rounded, which would mean 'off'."""
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: "light.eh123456_led", ATTR_BRIGHTNESS: 1},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.set_led_brightness.assert_called_once_with(1)


async def test_cable_lock_writes_both_ways(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """The cable lock is a setting, read back from the charger."""
    assert hass.states.get("switch.eh123456_cable_locked").state == "off"

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: "switch.eh123456_cable_locked"},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.set_cable_locked.assert_called_once_with(True)

    await _set_reading(hass, loaded, mock_charger, cableLocked=1)
    assert hass.states.get("switch.eh123456_cable_locked").state == "on"


async def test_reason_for_no_current_reports_slug_and_code(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """The state is the stable slug; the raw code rides along as an attribute."""
    await _set_reading(hass, loaded, mock_charger, reasonForNoCurrent=53)
    state = hass.states.get("sensor.eh123456_charging_blocked_by")
    assert state.state == "charger_disabled"
    assert state.attributes["code"] == 53
    assert state.attributes["known"] is True


async def test_unmapped_reason_code_has_no_state(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """An enum sensor may not invent a state outside its options list."""
    await _set_reading(hass, loaded, mock_charger, reasonForNoCurrent=222)
    state = hass.states.get("sensor.eh123456_charging_blocked_by")
    assert state.state == "unknown"
    assert state.attributes["code"] == 222
    assert state.attributes["known"] is False


async def test_absent_field_reads_as_unknown(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A field the charger did not send is not an error."""
    mock_charger.poll.return_value = {
        k: v for k, v in POLL_DATA.items() if k != "totalPower"
    }
    await loaded.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.eh123456_power").state == "unknown"


async def test_names_come_from_translations(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """Entity names are translated, not hard-coded on the descriptions."""
    assert (
        hass.states.get("sensor.eh123456_status").attributes["friendly_name"]
        == "EH123456 Status"
    )
    assert (
        hass.states.get("switch.eh123456_cable_locked").attributes["friendly_name"]
        == "EH123456 Cable locked"
    )
    assert (
        hass.states.get("sensor.eh123456_charging_blocked_by").attributes[
            "friendly_name"
        ]
        == "EH123456 Charging blocked by"
    )


async def test_icons_are_registered(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """icons.json is loaded and keyed to entities that exist."""
    icons = await async_get_icons(hass, "entity", [DOMAIN])
    entity_icons = icons[DOMAIN]
    assert entity_icons["sensor"]["charger_op_mode"]["default"] == "mdi:ev-station"
    assert (
        entity_icons["switch"]["cable_locked"]["state"]["off"]
        == "mdi:lock-open-variant"
    )


async def test_new_settings_write_and_read_back(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """The switches added in 0.2.0 send their own command and follow the poll."""
    assert hass.states.get("switch.eh123456_idle_current").state == "off"

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: "switch.eh123456_idle_current"},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.set_idle_current.assert_called_once_with(True)

    await _set_reading(hass, loaded, mock_charger, enableIdleCurrent=1)
    assert hass.states.get("switch.eh123456_idle_current").state == "on"


async def test_authorization_required_uses_local_authorization(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """Private access is written with set_local_authorization, not set_enabled."""
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: "switch.eh123456_require_authorisation"},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.set_local_authorization.assert_called_once_with(True)


async def test_dynamic_circuit_current_writes_all_phases(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """Every phase is named: one argument would set phase 1 and leave L2/L3 open."""
    assert hass.states.get("number.eh123456_dynamic_circuit_current").state == "20.0"

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: "number.eh123456_dynamic_circuit_current", "value": 12},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.set_dynamic_circuit_current.assert_called_once_with(12, 12, 12)


async def test_led_mode_reports_the_app_s_own_enum(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """LED mode is a disabled diagnostic, so it has to be enabled to be read."""
    registry = er.async_get(hass)
    entry = registry.async_get("sensor.eh123456_led_mode")
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    registry.async_update_entity(entry.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.eh123456_led_mode").state == "idle_master"


async def test_identify_plays_the_lights(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """The identify button runs the animation the app plays on connecting."""
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.eh123456_identify"}, blocking=True
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.play_lights.assert_called_once_with()


async def test_reboot_releases_the_connection_slot(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A rebooting charger is on its way down: hold nothing, and do not poll it."""
    mock_charger.poll.reset_mock()

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.eh123456_reboot"}, blocking=True
    )
    await hass.async_block_till_done()

    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.reboot.assert_called_once_with()
    mock_charger.disconnect.assert_awaited()
    assert not mock_charger.poll.await_count


async def test_every_entity_has_a_translated_name(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    """Each entity's translation key resolves, and strings.json has no orphans."""
    strings = json.loads(
        (Path(easee_ble.__file__).parent / "strings.json").read_text()
    )["entity"]

    used: dict[str, set[str]] = {}
    for entry in er.async_get(hass).entities.values():
        platform = entry.entity_id.split(".")[0]
        assert entry.translation_key, f"{entry.entity_id} has no translation key"
        assert entry.translation_key in strings.get(platform, {}), (
            f"{entry.entity_id}: no strings.json entry for "
            f"entity.{platform}.{entry.translation_key}"
        )
        used.setdefault(platform, set()).add(entry.translation_key)

    orphans = {
        f"{platform}.{key}"
        for platform, keys in strings.items()
        for key in keys
        if key not in used.get(platform, set())
    }
    assert not orphans, f"strings.json describes entities that do not exist: {orphans}"
