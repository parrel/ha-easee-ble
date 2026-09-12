"""Tests for the RFID key actions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.easee_ble.const import DOMAIN

from .conftest import ADDRESS


@pytest.fixture
async def charger_device(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> str:
    """The device id of a set-up charger."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, ADDRESS)})
    return device.id


async def test_list_rfid_keys_unwraps_the_reply(
    hass: HomeAssistant, charger_device: str, mock_charger: MagicMock
) -> None:
    """The names hide in the acknowledgement's Comment, as nested JSON."""
    mock_charger.perform.return_value = {
        "id": 102,
        "code": 1,
        "Comment": '{"utns":["Alice","Bob"]}',
    }

    response = await hass.services.async_call(
        DOMAIN,
        "list_rfid_keys",
        {ATTR_DEVICE_ID: charger_device},
        blocking=True,
        return_response=True,
    )

    assert response == {"keys": ["Alice", "Bob"]}
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.list_local_rfids.assert_called_once_with()


async def test_list_rfid_keys_survives_a_reply_without_names(
    hass: HomeAssistant, charger_device: str, mock_charger: MagicMock
) -> None:
    """A charger with no keys enrolled answers without the list at all."""
    mock_charger.perform.return_value = {"id": 102, "code": 1, "res": {"nws": 3}}

    response = await hass.services.async_call(
        DOMAIN,
        "list_rfid_keys",
        {ATTR_DEVICE_ID: charger_device},
        blocking=True,
        return_response=True,
    )

    assert response == {"keys": []}


async def test_add_and_remove_rfid_key(
    hass: HomeAssistant, charger_device: str, mock_charger: MagicMock
) -> None:
    """Adding takes a name and a token; removing takes the token alone."""
    await hass.services.async_call(
        DOMAIN,
        "add_rfid_key",
        {ATTR_DEVICE_ID: charger_device, "name": "Alice", "token": "04a1b2c3"},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.add_local_rfid.assert_called_once_with("Alice", "04a1b2c3")

    await hass.services.async_call(
        DOMAIN,
        "remove_rfid_key",
        {ATTR_DEVICE_ID: charger_device, "token": "04a1b2c3"},
        blocking=True,
    )
    session = MagicMock()
    mock_charger.perform.await_args.args[0](session)
    session.remove_local_rfid.assert_called_once_with("04a1b2c3")


async def test_keys_are_not_polled_back(
    hass: HomeAssistant, charger_device: str, mock_charger: MagicMock
) -> None:
    """No field reports the keys, so a read-back would cost a poll for nothing."""
    mock_charger.poll.reset_mock()

    await hass.services.async_call(
        DOMAIN,
        "add_rfid_key",
        {ATTR_DEVICE_ID: charger_device, "name": "Alice", "token": "04a1b2c3"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert not mock_charger.poll.await_count


async def test_a_device_from_another_integration_is_refused(
    hass: HomeAssistant, charger_device: str
) -> None:
    """Targeting something that is not one of our chargers is a user error."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "list_rfid_keys",
            {ATTR_DEVICE_ID: "does-not-exist"},
            blocking=True,
            return_response=True,
        )
