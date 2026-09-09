"""Tests for the polling coordinator and the entities that read it."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from easee_ble import EaseeCommandRefused, EaseeConnectionError, IncompleteFrame
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.easee_ble.const import MAX_LINK_AGE

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


async def test_link_is_held_across_polls(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A second poll reuses the connection rather than rebuilding it."""
    await loaded.runtime_data.async_refresh()
    assert mock_charger.connect.await_count == 1
    assert mock_charger.poll.await_count == 2


async def test_broken_link_is_dropped(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A malformed reply is a link problem: drop it and reconnect next cycle."""
    mock_charger.poll.side_effect = IncompleteFrame("short frame")
    await loaded.runtime_data.async_refresh()
    assert not loaded.runtime_data.last_update_success
    mock_charger.disconnect.assert_awaited()

    mock_charger.poll.side_effect = None
    await loaded.runtime_data.async_refresh()
    assert loaded.runtime_data.last_update_success
    assert mock_charger.connect.await_count == 2


async def test_readings_go_unavailable_when_the_link_drops(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """Readings stop claiming to be live the moment the backend says so."""
    power = hass.states.get("sensor.eh123456_power")
    assert power.state == str(POLL_DATA["totalPower"])

    mock_charger.connected = False
    loaded.runtime_data.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.eh123456_power").state == "unavailable"
    # Controls stay usable: the coordinator reconnects on demand.
    assert hass.states.get("switch.eh123456_charger_enabled").state == "on"


async def test_command_writes_and_refreshes(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """Turning a switch off writes to the charger and reads the result back."""
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: "switch.eh123456_charger_enabled"},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_charger.perform.assert_awaited()
    assert mock_charger.poll.await_count > 1


async def test_refused_command_keeps_the_link(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """The charger saying no is an answer, not a broken link."""
    mock_charger.perform.side_effect = EaseeCommandRefused("out of range")
    with pytest.raises(HomeAssistantError, match="refused"):
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: "number.eh123456_max_charger_current", "value": 6},
            blocking=True,
        )
    mock_charger.disconnect.assert_not_awaited()


async def test_failed_command_drops_the_link(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A command that could not be delivered starts the recovery."""
    mock_charger.perform.side_effect = EaseeConnectionError("write failed")
    with pytest.raises(HomeAssistantError, match="could not be delivered"):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: "select.eh123456_phase_mode", "option": "auto"},
            blocking=True,
        )
    mock_charger.disconnect.assert_awaited()


async def test_out_of_range_command_is_reported(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A charger that is not advertising gives the user a reason, not a traceback."""
    mock_charger.connected = False
    import custom_components.easee_ble.coordinator as coordinator_module

    original = coordinator_module.bluetooth.async_ble_device_from_address
    coordinator_module.bluetooth.async_ble_device_from_address = (
        lambda *args, **kwargs: None
    )
    try:
        with pytest.raises(HomeAssistantError, match="not in range"):
            await hass.services.async_call(
                "light",
                "turn_off",
                {ATTR_ENTITY_ID: "light.eh123456_led"},
                blocking=True,
            )
    finally:
        coordinator_module.bluetooth.async_ble_device_from_address = original


async def test_link_lost_schedules_a_reconnect(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A drop reported between polls starts recovering immediately."""
    coordinator = loaded.runtime_data
    mock_charger.connected = False
    coordinator._on_link_lost(mock_charger)
    await hass.async_block_till_done()

    mock_charger.connected = True
    await hass.async_block_till_done()
    assert mock_charger.connect.await_count == 2


async def test_link_lost_ignores_a_charger_we_let_go_of(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A deliberate disconnect must not trigger a reconnect of its own."""
    coordinator = loaded.runtime_data
    coordinator._on_link_lost(MagicMock())
    await hass.async_block_till_done()
    assert mock_charger.connect.await_count == 1


async def test_stale_link_is_retired(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """A link older than MAX_LINK_AGE is replaced by the poll, not by a command."""
    coordinator = loaded.runtime_data
    coordinator._connected_at -= MAX_LINK_AGE + 1

    # The command path takes the old link as it is, rather than waiting on a reconnect.
    await coordinator._ready()
    assert mock_charger.connect.await_count == 1

    # The poll path retires it.
    await coordinator._ready(retire_stale=True)
    assert mock_charger.connect.await_count == 2


async def test_connect_reporting_a_lost_link_is_not_adopted(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """A connection that arrives already dead is discarded, not held."""
    mock_entry.add_to_hass(hass)

    def _connect() -> None:
        mock_charger.connected = False

    mock_charger.connect.side_effect = _connect
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.runtime_data.charger is None
