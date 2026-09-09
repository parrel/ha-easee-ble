"""The Easee EV Charger (Bluetooth) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EaseeBleCoordinator

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type EaseeBleConfigEntry = ConfigEntry[EaseeBleCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EaseeBleConfigEntry) -> bool:
    """Set up Easee BLE from a config entry."""
    coordinator = EaseeBleCoordinator(hass, entry)
    entry.runtime_data = coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        # Give the charger's only connection slot back, or the retry finds nothing.
        await coordinator.async_shutdown()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: EaseeBleConfigEntry
) -> None:
    """Apply an options change without the reconnect a reload would cost."""
    await entry.runtime_data.async_apply_options()


async def async_unload_entry(hass: HomeAssistant, entry: EaseeBleConfigEntry) -> bool:
    """Unload a config entry, releasing the connection so a reload can reconnect."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
