"""Actions for the RFID keys enrolled on the charger itself.

Keys are a list, not a state: there is no field that reports them, so they are
actions rather than entities. Note these are the charger's *local* keys, the
ones that work with no network. A tag paired through the Easee app belongs to
the account in the cloud and never appears here.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import EaseeBleCoordinator

SERVICE_LIST_RFID_KEYS = "list_rfid_keys"
SERVICE_ADD_RFID_KEY = "add_rfid_key"
SERVICE_REMOVE_RFID_KEY = "remove_rfid_key"

ATTR_NAME = "name"
ATTR_TOKEN = "token"
ATTR_KEYS = "keys"

_DEVICE_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})

_ADD_SCHEMA = _DEVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(ATTR_TOKEN): cv.string,
    }
)

_REMOVE_SCHEMA = _DEVICE_SCHEMA.extend({vol.Required(ATTR_TOKEN): cv.string})


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> EaseeBleCoordinator:
    """The coordinator for the charger a call targets."""
    device_id: str = call.data[ATTR_DEVICE_ID]
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain == DOMAIN:
                if entry.state is not ConfigEntryState.LOADED:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN,
                        translation_key="charger_not_loaded",
                    )
                return entry.runtime_data
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="not_an_easee_charger",
        translation_placeholders={"device_id": device_id},
    )


async def _list_rfid_keys(call: ServiceCall) -> ServiceResponse:
    """List the keys enrolled on the charger."""
    keys = await _coordinator(call.hass, call).async_list_rfid_keys()
    return {ATTR_KEYS: keys}


async def _add_rfid_key(call: ServiceCall) -> None:
    """Enrol a key on the charger."""
    await _coordinator(call.hass, call).async_add_rfid_key(
        call.data[ATTR_NAME], call.data[ATTR_TOKEN]
    )


async def _remove_rfid_key(call: ServiceCall) -> None:
    """Remove an enrolled key from the charger."""
    await _coordinator(call.hass, call).async_remove_rfid_key(call.data[ATTR_TOKEN])


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions. Once, not once per charger."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_RFID_KEYS,
        _list_rfid_keys,
        schema=_DEVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_RFID_KEY, _add_rfid_key, schema=_ADD_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_RFID_KEY, _remove_rfid_key, schema=_REMOVE_SCHEMA
    )
