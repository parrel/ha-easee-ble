"""Tests for the diagnostics download."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.easee_ble.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SERIAL


async def test_diagnostics_redacts_identifying_fields(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """The download carries the readings, with the identifying ones redacted."""
    mock_charger.poll.return_value = {
        "totalPower": 7.4,
        "wifiSSID": "my-network",
        "ipAddress": "192.168.1.20",
        "macAddress": "aa:bb:cc:dd:ee:ff",
    }
    mock_charger.unknown = {"CONFIG#14": 1}
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_entry)
    assert diag["serial"] == SERIAL
    assert diag["connected"] is True
    assert diag["named"]["totalPower"] == 7.4
    assert diag["named"]["wifiSSID"] == "**REDACTED**"
    assert diag["named"]["ipAddress"] == "**REDACTED**"
    assert diag["named"]["macAddress"] == "**REDACTED**"
    assert diag["unnamed"] == {"CONFIG#14": 1}
