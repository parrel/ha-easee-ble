"""Config flow: discover a charger over Bluetooth and take its PIN."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from easee_ble import EaseeCharger, EaseeError, JPakeError
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS, CONF_PIN, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER_ID,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)

_PIN_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})


def _is_charger(info: BluetoothServiceInfoBleak) -> bool:
    """The vendor signature the manifest matches on, re-checked per advertisement."""
    return (
        MANUFACTURER_ID in info.manufacturer_data or SERVICE_UUID in info.service_uuids
    )


def _serial_from(info: BluetoothServiceInfoBleak) -> str | None:
    """The charger advertises its bare serial as its name.

    A nameless advertisement reports the address instead, which is not alphanumeric.
    """
    name = (info.name or "").strip()
    return name if name.isalnum() else None


async def _validate(hass: HomeAssistant, address: str, serial: str, pin: str) -> None:
    """Connect once with the given PIN, then let the charger go."""
    device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        raise CannotConnect(f"charger {serial} ({address}) is not in range")
    charger = EaseeCharger(device, pin, serial)
    try:
        await charger.connect()
    except JPakeError as exc:
        raise InvalidAuth(str(exc)) from exc
    except (EaseeError, BleakError) as exc:
        raise CannotConnect(str(exc)) from exc
    finally:
        await charger.disconnect()


class CannotConnect(Exception):
    """The charger could not be reached."""


class InvalidAuth(Exception):
    """The charger rejected the PIN."""


class EaseeBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Easee BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with no charger picked yet."""
        self._address: str = ""
        self._serial: str = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EaseeBleOptionsFlow:
        """Return the options flow for this entry."""
        return EaseeBleOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a charger found by Home Assistant's Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_charger(discovery_info):
            return self.async_abort(reason="not_supported")
        serial = _serial_from(discovery_info)
        if serial is None:
            # A later advertisement carrying the name re-triggers discovery.
            return self.async_abort(reason="no_serial")
        self._address, self._serial = discovery_info.address, serial
        self.context["title_placeholders"] = {"name": serial}
        return await self.async_step_pin()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a discovered charger."""
        candidates = self._candidates()
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if (serial := candidates.get(address)) is None:
                return self.async_abort(reason="no_devices_found")
            self._address, self._serial = address, serial
            return await self.async_step_pin()

        if not candidates:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {a: f"{s} ({a})" for a, s in candidates.items()}
                    )
                }
            ),
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take the PIN printed on the charger, and check it works."""
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN]
            errors = await self._check(pin)
            if not errors:
                return self.async_create_entry(
                    title=self._serial,
                    data={
                        CONF_ADDRESS: self._address,
                        CONF_SERIAL: self._serial,
                        CONF_PIN: pin,
                    },
                )
        return self.async_show_form(
            step_id="pin",
            data_schema=_PIN_SCHEMA,
            description_placeholders={"serial": self._serial},
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a PIN that has stopped working."""
        self._address = entry_data[CONF_ADDRESS]
        self._serial = entry_data[CONF_SERIAL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take a new PIN for an existing entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN]
            errors = await self._check(pin)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_PIN: pin}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_PIN_SCHEMA,
            description_placeholders={"serial": self._serial},
            errors=errors,
        )

    async def _check(self, pin: str) -> dict[str, str]:
        """Try the PIN against the charger, mapping failures to form errors."""
        try:
            await _validate(self.hass, self._address, self._serial, pin)
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except CannotConnect:
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception(
                "charger %s: unexpected error validating the PIN", self._serial
            )
            return {"base": "unknown"}
        return {}

    def _candidates(self) -> dict[str, str]:
        """Advertising chargers that are not configured yet, by address."""
        configured = self._async_current_ids()
        found: dict[str, str] = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in configured or not _is_charger(info):
                continue
            if (serial := _serial_from(info)) is not None:
                found[info.address] = serial
        return found


class EaseeBleOptionsFlow(OptionsFlow):
    """Let the user tune the poll interval from Configure."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the poll interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds()
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=interval): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
