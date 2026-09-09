"""Fixtures shared by the Easee BLE tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_PIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.easee_ble.const import CONF_SERIAL, DOMAIN

ADDRESS = "AA:BB:CC:DD:EE:FF"
SERIAL = "EH123456"
PIN = "1234"

POLL_DATA = {
    "isEnabled": 1,
    "cableLocked": 0,
    "phaseMode": 2,
    "btEnableMode": 1,
    "ledStripBrightness": 60,
    "maxChargerCurrent": 32,
    "dynamicChargerCurrent": 16,
    "chargerOpMode": 3,
    "reasonForNoCurrent": 0,
    "lifetimeEnergy": 1234.5,
    "totalPower": 7.4,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom_components in every test."""


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """A configured charger."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        title=SERIAL,
        data={CONF_ADDRESS: ADDRESS, CONF_SERIAL: SERIAL, CONF_PIN: PIN},
    )


@pytest.fixture
def mock_ble_device() -> Generator[MagicMock]:
    """Pretend the charger is in range wherever the integration looks."""
    device = MagicMock()
    with (
        patch(
            "custom_components.easee_ble.coordinator.bluetooth"
            ".async_ble_device_from_address",
            return_value=device,
        ),
        patch(
            "custom_components.easee_ble.config_flow.bluetooth"
            ".async_ble_device_from_address",
            return_value=device,
        ),
    ):
        yield device


@pytest.fixture
def mock_charger() -> Generator[MagicMock]:
    """A charger that connects and polls successfully."""
    charger = MagicMock()
    charger.connected = True
    charger.radio = "proxy"
    charger.unknown = {}
    charger.connect = AsyncMock()
    charger.disconnect = AsyncMock()
    charger.perform = AsyncMock()
    charger.poll = AsyncMock(return_value=dict(POLL_DATA))
    with (
        patch(
            "custom_components.easee_ble.coordinator.EaseeCharger",
            return_value=charger,
        ),
        patch(
            "custom_components.easee_ble.config_flow.EaseeCharger",
            return_value=charger,
        ),
    ):
        yield charger
