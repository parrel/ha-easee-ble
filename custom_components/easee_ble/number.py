"""Writable numeric settings: the charger and circuit current limits."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EaseeNumberEntityDescription(NumberEntityDescription):
    """Describes an Easee number entity."""

    field: str
    setter: Callable[[EaseeBleCoordinator, int], Awaitable[None]]


NUMBERS: tuple[EaseeNumberEntityDescription, ...] = (
    EaseeNumberEntityDescription(
        key="max_charger_current",
        field="maxChargerCurrent",
        translation_key="max_charger_current",
        device_class=NumberDeviceClass.CURRENT,
        native_min_value=0,
        native_max_value=40,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        setter=lambda c, v: c.async_set_max_charger_current(v),
    ),
    EaseeNumberEntityDescription(
        key="dynamic_charger_current",
        field="dynamicChargerCurrent",
        translation_key="dynamic_charger_current",
        device_class=NumberDeviceClass.CURRENT,
        native_min_value=0,
        native_max_value=40,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        setter=lambda c, v: c.async_set_dynamic_charger_current(v),
    ),
    EaseeNumberEntityDescription(
        key="dynamic_circuit_current",
        field="dynamicCircuitCurrentP1",
        translation_key="dynamic_circuit_current",
        device_class=NumberDeviceClass.CURRENT,
        native_min_value=0,
        native_max_value=40,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        setter=lambda c, v: c.async_set_dynamic_circuit_current(v),
    ),
    EaseeNumberEntityDescription(
        key="fallback_circuit_current",
        field="fallbackCircuitCurrentP1",
        translation_key="fallback_circuit_current",
        device_class=NumberDeviceClass.CURRENT,
        native_min_value=0,
        native_max_value=40,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        setter=lambda c, v: c.async_set_fallback_circuit_current(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(EaseeNumber(coordinator, desc) for desc in NUMBERS)


class EaseeNumber(EaseeBleEntity, NumberEntity):
    """A writable current limit on the charger."""

    entity_description: EaseeNumberEntityDescription

    def __init__(
        self,
        coordinator: EaseeBleCoordinator,
        description: EaseeNumberEntityDescription,
    ) -> None:
        """Initialise the number."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """The limit as last read from the charger."""
        value = (self.coordinator.data or {}).get(self.entity_description.field)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new limit to the charger."""
        await self.entity_description.setter(self.coordinator, int(value))
