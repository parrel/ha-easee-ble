"""Tests for the entity behaviour that is not just a field read."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.icon import async_get_icons
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
