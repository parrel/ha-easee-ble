"""Switches: the charger's on/off setting, and the permanent cable lock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    async_add_entities([EaseeChargerEnabled(coordinator), EaseeCableLock(coordinator)])


class EaseeChargerEnabled(EaseeBleEntity, SwitchEntity):
    """Switch the charger on or off - Easee's ``isEnabled``."""

    _attr_translation_key = "charger_enabled"

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_charger_enabled"

    @property
    def is_on(self) -> bool | None:
        """Whether the charger is enabled."""
        value = (self.coordinator.data or {}).get("isEnabled")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the charger."""
        await self.coordinator.async_set_charger_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the charger."""
        await self.coordinator.async_set_charger_enabled(False)


class EaseeCableLock(EaseeBleEntity, SwitchEntity):
    """Lock the charging cable permanently into the socket."""

    _attr_translation_key = "cable_locked"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_cable_locked"

    @property
    def is_on(self) -> bool | None:
        """Whether the cable is set to stay locked."""
        value = (self.coordinator.data or {}).get("cableLocked")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the cable permanently."""
        await self.coordinator.async_set_cable_locked(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Release the permanent cable lock."""
        await self.coordinator.async_set_cable_locked(False)
