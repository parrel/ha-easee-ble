"""Switches: the charger's on/off setting and the settings that behave like one."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EaseeSwitchEntityDescription(SwitchEntityDescription):
    """Describes an Easee switch entity."""

    field: str
    setter: Callable[[EaseeBleCoordinator, bool], Awaitable[None]]


SWITCHES: tuple[EaseeSwitchEntityDescription, ...] = (
    EaseeSwitchEntityDescription(
        key="charger_enabled",
        field="isEnabled",
        translation_key="charger_enabled",
        setter=lambda c, v: c.async_set_charger_enabled(v),
    ),
    EaseeSwitchEntityDescription(
        key="cable_locked",
        field="cableLocked",
        translation_key="cable_locked",
        entity_category=EntityCategory.CONFIG,
        setter=lambda c, v: c.async_set_cable_locked(v),
    ),
    # Trickle current to a parked car, so it can keep its own systems alive.
    EaseeSwitchEntityDescription(
        key="idle_current",
        field="enableIdleCurrent",
        translation_key="idle_current",
        entity_category=EntityCategory.CONFIG,
        setter=lambda c, v: c.async_set_idle_current(v),
    ),
    # The app calls this private access: no charging until a key is presented.
    EaseeSwitchEntityDescription(
        key="authorization_required",
        field="authorizationRequired",
        translation_key="authorization_required",
        entity_category=EntityCategory.CONFIG,
        setter=lambda c, v: c.async_set_local_authorization(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    async_add_entities(EaseeSwitch(coordinator, desc) for desc in SWITCHES)


class EaseeSwitch(EaseeBleEntity, SwitchEntity):
    """A setting on the charger that is on or off."""

    entity_description: EaseeSwitchEntityDescription

    def __init__(
        self,
        coordinator: EaseeBleCoordinator,
        description: EaseeSwitchEntityDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """The setting as last read from the charger."""
        value = (self.coordinator.data or {}).get(self.entity_description.field)
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the setting on."""
        await self.entity_description.setter(self.coordinator, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the setting off."""
        await self.entity_description.setter(self.coordinator, False)
