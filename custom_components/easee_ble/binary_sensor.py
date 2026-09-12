"""Binary sensors: the read-only flags the charger reports."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleReadingEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EaseeBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an Easee binary sensor entity."""

    field: str


BINARY_SENSORS: tuple[EaseeBinarySensorEntityDescription, ...] = (
    # Only the cloud or the app can turn OCPP on, so this reports and no more.
    EaseeBinarySensorEntityDescription(
        key="ocpp_enabled",
        field="ocppEnabled",
        translation_key="ocpp_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(EaseeBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class EaseeBinarySensor(EaseeBleReadingEntity, BinarySensorEntity):
    """One flag from the charger's last poll."""

    entity_description: EaseeBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EaseeBleCoordinator,
        description: EaseeBinarySensorEntityDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """The flag's value, or None if the charger did not send it."""
        value = (self.coordinator.data or {}).get(self.entity_description.field)
        return None if value is None else bool(value)
