"""Shared base entities: device info, and the two availability policies."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EaseeBleCoordinator


class EaseeBleEntity(CoordinatorEntity[EaseeBleCoordinator]):
    """Base entity tying Home Assistant entities to one charger."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Attach the entity to the charger's device entry."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Easee",
            name=coordinator.serial,
            serial_number=coordinator.serial,
        )


class EaseeBleReadingEntity(EaseeBleEntity):
    """Base for entities that only report. Unavailable as soon as the link is."""

    @property
    def available(self) -> bool:
        """Whether the cached reading is still backed by a live link."""
        return super().available and not self.coordinator.link_lost
