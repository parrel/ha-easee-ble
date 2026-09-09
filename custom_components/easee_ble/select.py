"""Selects: phase mode, and how the charger's Bluetooth radio behaves."""

from __future__ import annotations

from easee_ble import BtEnableMode, PhaseMode
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleEntity

PARALLEL_UPDATES = 0

# Option strings are translation keys (see strings.json), so keep them stable.
_OPTION_TO_MODE = {
    "1_phase": PhaseMode.LOCKED_1_PHASE,
    "auto": PhaseMode.AUTO,
    "3_phase": PhaseMode.LOCKED_3_PHASE,
}
_MODE_TO_OPTION = {mode.value: option for option, mode in _OPTION_TO_MODE.items()}

_OPTION_TO_BT_MODE = {
    "button_press": BtEnableMode.BUTTON_PRESS,
    "always_on": BtEnableMode.ALWAYS_ON,
}
_BT_MODE_TO_OPTION = {mode.value: option for option, mode in _OPTION_TO_BT_MODE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    coordinator = entry.runtime_data
    async_add_entities([EaseePhaseMode(coordinator), EaseeBtEnableMode(coordinator)])


class EaseePhaseMode(EaseeBleEntity, SelectEntity):
    """How many phases the charger is allowed to use."""

    _attr_translation_key = "phase_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(_OPTION_TO_MODE)

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_phase_mode"

    @property
    def current_option(self) -> str | None:
        """The phase mode as last read from the charger."""
        value = (self.coordinator.data or {}).get("phaseMode")
        return None if value is None else _MODE_TO_OPTION.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Write a new phase mode to the charger."""
        await self.coordinator.async_set_phase_mode(_OPTION_TO_MODE[option])


class EaseeBtEnableMode(EaseeBleEntity, SelectEntity):
    """How the charger's Bluetooth radio behaves."""

    _attr_translation_key = "bt_enable_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(_OPTION_TO_BT_MODE)

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_bt_enable_mode"

    @property
    def current_option(self) -> str | None:
        """The Bluetooth mode as last read from the charger."""
        value = (self.coordinator.data or {}).get("btEnableMode")
        return None if value is None else _BT_MODE_TO_OPTION.get(int(value))

    async def async_select_option(self, option: str) -> None:
        """Write a new Bluetooth mode to the charger."""
        await self.coordinator.async_set_bt_enable_mode(_OPTION_TO_BT_MODE[option])
