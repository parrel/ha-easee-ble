"""Tests for the Easee BLE config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from easee_ble import EaseeConnectionError, JPakeError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_PIN, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.easee_ble.const import (
    CONF_SERIAL,
    DOMAIN,
    MANUFACTURER_ID,
    SERVICE_UUID,
)

from .conftest import ADDRESS, PIN, SERIAL


def _info(
    name: str,
    address: str = ADDRESS,
    *,
    manufacturer_data: dict[int, bytes] | None = None,
    service_uuids: list[str] | None = None,
) -> BluetoothServiceInfoBleak:
    """One advertisement, with only the fields the config flow reads."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-70,
        manufacturer_data={} if manufacturer_data is None else manufacturer_data,
        service_data={},
        service_uuids=[] if service_uuids is None else service_uuids,
        source="local",
        device=MagicMock(),
        advertisement=MagicMock(),
        connectable=True,
        time=0,
        tx_power=-127,
    )


VENDOR = {MANUFACTURER_ID: b"\x00"}

DISCOVERY = _info(SERIAL, manufacturer_data=VENDOR)

# No serial format is assumed: only the vendor signature identifies a charger.
ODD_SERIAL = _info("QP7X99", address="11:22:33:44:55:01", service_uuids=[SERVICE_UUID])

# An advertisement without a local name reports the address as its name.
UNNAMED = _info(
    "11:22:33:44:55:02", address="11:22:33:44:55:02", manufacturer_data=VENDOR
)

NOT_A_CHARGER = _info("SomeOtherThing", address="11:22:33:44:55:66")


def _discovered(*infos: BluetoothServiceInfoBleak):
    """Patch what Home Assistant's Bluetooth discovery is holding."""
    return patch(
        "custom_components.easee_ble.config_flow.async_discovered_service_info",
        return_value=list(infos),
    )


async def test_bluetooth_discovery(
    hass: HomeAssistant, mock_ble_device: MagicMock, mock_charger: MagicMock
) -> None:
    """A discovered charger asks for its PIN and is set up."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pin"
    assert result["description_placeholders"] == {"serial": SERIAL}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: PIN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == SERIAL
    assert result["data"] == {
        CONF_ADDRESS: ADDRESS,
        CONF_SERIAL: SERIAL,
        CONF_PIN: PIN,
    }
    # The PIN was checked against the charger and the slot handed back.
    assert mock_charger.connect.await_count >= 1
    assert mock_charger.disconnect.await_count >= 1


async def test_bluetooth_discovery_not_a_charger(hass: HomeAssistant) -> None:
    """A device without the vendor signature is not offered."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=NOT_A_CHARGER
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_unfamiliar_serial(
    hass: HomeAssistant, mock_ble_device: MagicMock, mock_charger: MagicMock
) -> None:
    """A charger is taken at its word about its serial, whatever the format."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=ODD_SERIAL
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {"serial": "QP7X99"}


async def test_bluetooth_discovery_without_name(hass: HomeAssistant) -> None:
    """An advertisement carrying no name has no serial to set up with."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=UNNAMED
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_serial"


async def test_bluetooth_discovery_already_configured(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """A charger that is already set up is not offered again."""
    mock_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=DISCOVERY
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow(
    hass: HomeAssistant, mock_ble_device: MagicMock, mock_charger: MagicMock
) -> None:
    """The user picks a charger from the advertising ones."""
    with _discovered(DISCOVERY, ODD_SERIAL, UNNAMED, NOT_A_CHARGER):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        # Both chargers are offered; the nameless and non-Easee adverts are not.
        assert set(result["data_schema"].schema[CONF_ADDRESS].container) == {
            ADDRESS,
            ODD_SERIAL.address,
        }

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
    assert result["step_id"] == "pin"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: PIN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADDRESS] == ADDRESS


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    """Nothing advertising means nothing to set up."""
    with _discovered():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_skips_configured(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """A charger that is already set up is not in the picker."""
    mock_entry.add_to_hass(hass)
    with _discovered(DISCOVERY):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (JPakeError("verification failed"), "invalid_auth"),
        (EaseeConnectionError("no link"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_pin_errors_recover(
    hass: HomeAssistant,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
    error: Exception,
    expected: str,
) -> None:
    """A bad PIN or an unreachable charger is reported on the form, and retried."""
    mock_charger.connect.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=DISCOVERY
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: "0000"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    mock_charger.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: PIN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_pin_charger_out_of_range(
    hass: HomeAssistant, mock_charger: MagicMock
) -> None:
    """A charger that stopped advertising between steps cannot be validated."""
    with patch(
        "custom_components.easee_ble.config_flow.bluetooth"
        ".async_ble_device_from_address",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=DISCOVERY
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: PIN}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """A rejected PIN can be replaced without removing the entry."""
    mock_entry.add_to_hass(hass)
    result = await mock_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    mock_charger.connect.side_effect = JPakeError("verification failed")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: "0000"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_charger.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PIN: "4321"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_entry.data[CONF_PIN] == "4321"

    # The reauth success reloads the entry in the background; let that finish,
    # then unload so the coordinator's refresh timer doesn't linger past the test.
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    mock_ble_device: MagicMock,
    mock_charger: MagicMock,
) -> None:
    """The poll interval can be changed without a reload."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 90}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_entry.options == {CONF_SCAN_INTERVAL: 90}
    assert mock_entry.runtime_data.update_interval.total_seconds() == 90
