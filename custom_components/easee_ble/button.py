"""Buttons: the charger actions that take no argument and read nothing back."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EaseeButtonEntityDescription(ButtonEntityDescription):
    """Describes an Easee button entity."""

    press: Callable[[EaseeBleCoordinator], Awaitable[None]]


BUTTONS: tuple[EaseeButtonEntityDescription, ...] = (
    EaseeButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press=lambda c: c.async_reboot(),
    ),
    EaseeButtonEntityDescription(
        key="identify",
        translation_key="identify",
        device_class=ButtonDeviceClass.IDENTIFY,
        entity_category=EntityCategory.CONFIG,
        press=lambda c: c.async_play_lights(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(EaseeButton(coordinator, desc) for desc in BUTTONS)


class EaseeButton(EaseeBleEntity, ButtonEntity):
    """One action the charger performs on request."""

    entity_description: EaseeButtonEntityDescription

    def __init__(
        self,
        coordinator: EaseeBleCoordinator,
        description: EaseeButtonEntityDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    async def async_press(self) -> None:
        """Send the action to the charger."""
        await self.entity_description.press(self.coordinator)
