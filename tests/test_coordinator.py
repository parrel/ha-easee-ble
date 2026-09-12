"""Tests for the polling coordinator and the entities that read it."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from easee_ble import EaseeCommandRefused, EaseeConnectionError, IncompleteFrame
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.easee_ble.coordinator as coordinator_module

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


async def test_a_working_link_is_never_given_up(
    hass: HomeAssistant, loaded: MockConfigEntry, mock_charger: MagicMock
) -> None:
    """Age alone is no reason to drop a link: the charger has one slot to lose."""
    coordinator = loaded.runtime_data

    for _ in range(3):
        await coordinator.async_refresh()

    assert mock_charger.connect.await_count == 1
    mock_charger.disconnect.assert_not_awaited()


async def test_reconnect_waits_for_the_teardown_to_settle(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    mock_charger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reconnect does not race the teardown of the link it just dropped."""
    coordinator = loaded.runtime_data
    monkeypatch.setattr(coordinator_module, "RECONNECT_SETTLE", 0.2)

    await coordinator._drop()
    started = hass.loop.time()
    await coordinator._ready()

    assert hass.loop.time() - started >= 0.2
    assert mock_charger.connect.await_count == 2


async def test_a_link_lost_while_connecting_still_settles(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    mock_charger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The library tears that link down itself, so only the callback records it."""
    coordinator = loaded.runtime_data
    monkeypatch.setattr(coordinator_module, "RECONNECT_SETTLE", 0.2)

    # As the library does: report the drop, then fail the connect it happened during.
    coordinator._charger = None
    coordinator._on_link_lost(mock_charger)
    started = hass.loop.time()
    await coordinator._ready()

    assert hass.loop.time() - started >= 0.2


async def test_the_settle_survives_a_reload(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    mock_charger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed setup is reloaded on the next advertisement, coordinator and all."""
    monkeypatch.setattr(coordinator_module, "RECONNECT_SETTLE", 0.2)
    await loaded.runtime_data._drop()

    # As a reload does: a new coordinator, remembering nothing of its own.
    reloaded = coordinator_module.EaseeBleCoordinator(hass, loaded)
    started = hass.loop.time()
    await reloaded._ready()

    assert hass.loop.time() - started >= 0.2


async def test_a_first_connect_does_not_settle(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing was torn down, so there is nothing to wait for."""
    monkeypatch.setattr(coordinator_module, "RECONNECT_SETTLE", 5.0)
    mock_entry.add_to_hass(hass)

    started = hass.loop.time()
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.loop.time() - started < 5.0


async def test_a_wedged_poll_is_cut_short(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    mock_charger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A link that stops answering is rebuilt, not waited on for minutes."""
    monkeypatch.setattr(coordinator_module, "POLL_TIMEOUT", 0.05)

    async def _never_answers(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(60)

    mock_charger.poll.side_effect = _never_answers
    await loaded.runtime_data.async_refresh()

    assert not loaded.runtime_data.last_update_success
    assert "unanswered" in str(loaded.runtime_data.last_exception)
    mock_charger.disconnect.assert_awaited()

    mock_charger.poll.side_effect = None
    await loaded.runtime_data.async_refresh()
    assert loaded.runtime_data.last_update_success
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
