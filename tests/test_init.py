"""Tests for setting up, reloading and unloading a config entry."""

from __future__ import annotations

from unittest.mock import MagicMock

from easee_ble import EaseeConnectionError, JPakeError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.easee_ble.const import DOMAIN


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """A charger in range sets up, creates entities, and releases the slot."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.eh123456_status") is not None
    assert hass.states.get("switch.eh123456_charger_enabled").state == "on"

    device_registry = dr.async_get(hass)
    (device,) = dr.async_entries_for_config_entry(device_registry, mock_entry.entry_id)
    assert device.manufacturer == "Easee"

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
    mock_charger.disconnect.assert_awaited()


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """A charger that cannot be reached leaves the entry retrying, not failed."""
    mock_charger.connect.side_effect = EaseeConnectionError("no link")
    mock_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.SETUP_RETRY
    # The half-finished setup retained no connection, so the retry starts clean.
    assert mock_entry.runtime_data.charger is None


async def test_setup_starts_reauth_on_bad_pin(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """A rejected PIN asks the user for a new one instead of retrying forever."""
    mock_charger.connect.side_effect = JPakeError("verification failed")
    mock_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]
