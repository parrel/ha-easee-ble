"""Diagnostics: everything the last poll saw, named fields and unnamed alike."""

from __future__ import annotations

from typing import Any

from easee_ble import reason_for_no_current, reason_for_no_current_slug
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import EaseeBleConfigEntry

# Identify the charger's owner or its place on a network, and help with nothing.
TO_REDACT = {"wifiSSID", "ipAddress", "macAddress"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EaseeBleConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = dict(coordinator.data or {})
    charger = coordinator.charger
    reason = data.get("reasonForNoCurrent")
    return {
        "serial": coordinator.serial,
        "connected": bool(charger and charger.connected),
        "radio": charger.radio if charger else None,
        "update_ok": coordinator.last_update_success,
        # Distinct from "connected": this is what the sensors read for availability.
        "link_lost": coordinator.link_lost,
        "named": async_redact_data(data, TO_REDACT),
        # The slug is what the sensor is keyed on; the text is for a person.
        "reason_for_no_current": reason_for_no_current_slug(reason),
        "reason_for_no_current_text": reason_for_no_current(reason),
        # Keyed "<CHANNEL>#<field number>", for identifying unnamed fields.
        "unnamed": dict(charger.unknown) if charger else {},
    }
