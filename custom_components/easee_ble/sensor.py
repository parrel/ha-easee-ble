"""Read-only State/Config readings exposed as sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from easee_ble import (
    CONFIRMED_REASON_CODES,
    REASON_FOR_NO_CURRENT,
    REASON_FOR_NO_CURRENT_SLUGS,
    ChargerOpMode,
    reason_for_no_current,
    reason_for_no_current_slug,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleReadingEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EaseeSensorEntityDescription(SensorEntityDescription):
    """Describes an Easee sensor entity."""

    field: str


def _current(
    field: str, key: str, *, enabled_default: bool = True
) -> EaseeSensorEntityDescription:
    """A per-phase current reading."""
    return EaseeSensorEntityDescription(
        key=key,
        field=field,
        translation_key=key,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled_default,
    )


def _voltage(field: str, key: str) -> EaseeSensorEntityDescription:
    """A per-phase voltage reading."""
    return EaseeSensorEntityDescription(
        key=key,
        field=field,
        translation_key=key,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    )


def _equalizer_limit(field: str, key: str) -> EaseeSensorEntityDescription:
    """A limit an Easee Equalizer pushes down to this charger, one per phase."""
    return EaseeSensorEntityDescription(
        key=key,
        field=field,
        translation_key=key,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


SENSORS: tuple[EaseeSensorEntityDescription, ...] = (
    # The charger's own lifetime meter, so it feeds the Energy dashboard.
    EaseeSensorEntityDescription(
        key="lifetime_energy",
        field="lifetimeEnergy",
        translation_key="lifetime_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Resets to (near) zero when a new session starts.
    EaseeSensorEntityDescription(
        key="session_energy",
        field="sessionEnergy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    EaseeSensorEntityDescription(
        key="total_power",
        field="totalPower",
        translation_key="total_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # The charger's view of the BLE link - the first thing to check when polling fails.
    EaseeSensorEntityDescription(
        key="local_rssi",
        field="localRSSI",
        translation_key="local_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    EaseeSensorEntityDescription(
        key="charger_firmware",
        field="chargerFirmware",
        translation_key="charger_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # The installer's circuit rating - read-only here, and P1 stands for all phases.
    EaseeSensorEntityDescription(
        key="circuit_max_current",
        field="circuitMaxCurrentP1",
        translation_key="circuit_max_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # The attached cable's rating, which reasonForNoCurrent 75 refers to.
    EaseeSensorEntityDescription(
        key="cable_rating",
        field="cableRating",
        translation_key="cable_rating",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    _equalizer_limit("equalizerLimitL1", "equalizer_limit_l1"),
    _equalizer_limit("equalizerLimitL2", "equalizer_limit_l2"),
    _equalizer_limit("equalizerLimitL3", "equalizer_limit_l3"),
    # The network the charger is configured to join, not necessarily the one it joined.
    EaseeSensorEntityDescription(
        key="wifi_ssid",
        field="wifiSSID",
        translation_key="wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    EaseeSensorEntityDescription(
        key="ip_address",
        field="ipAddress",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    EaseeSensorEntityDescription(
        key="mac_address",
        field="macAddress",
        translation_key="mac_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    _current("currentN", "current_n", enabled_default=False),
    _current("currentL1", "current_l1"),
    _current("currentL2", "current_l2"),
    _current("currentL3", "current_l3"),
    _voltage("voltageL1N", "voltage_l1n"),
    _voltage("voltageL2N", "voltage_l2n"),
    _voltage("voltageL3N", "voltage_l3n"),
)

_OP_MODE_OPTIONS = [mode.name.lower() for mode in ChargerOpMode]
_OP_MODE_BY_VALUE = {mode.value: mode.name.lower() for mode in ChargerOpMode}

# Ordered by code rather than alphabetically, the way Easee grouped them.
_REASON_OPTIONS = [
    REASON_FOR_NO_CURRENT_SLUGS[code] for code in sorted(REASON_FOR_NO_CURRENT_SLUGS)
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [EaseeReading(coordinator, desc) for desc in SENSORS]
    entities.append(EaseeStatus(coordinator))
    entities.append(EaseeReasonForNoCurrent(coordinator))
    async_add_entities(entities)


class EaseeReading(EaseeBleReadingEntity, SensorEntity):
    """One named field from the charger's last poll."""

    entity_description: EaseeSensorEntityDescription

    def __init__(
        self,
        coordinator: EaseeBleCoordinator,
        description: EaseeSensorEntityDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"

    @property
    def native_value(self) -> Any:
        """The field's value, or None if the charger did not send it."""
        return (self.coordinator.data or {}).get(self.entity_description.field)


class EaseeStatus(EaseeBleReadingEntity, SensorEntity):
    """The charger operation mode (idle / charging / ready ...)."""

    _attr_translation_key = "charger_op_mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _OP_MODE_OPTIONS

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_charger_op_mode"

    @property
    def native_value(self) -> str | None:
        """The operation mode as a lowercase option string."""
        value = (self.coordinator.data or {}).get("chargerOpMode")
        return None if value is None else _OP_MODE_BY_VALUE.get(int(value))


class EaseeReasonForNoCurrent(EaseeBleReadingEntity, SensorEntity):
    """Why the charger is not delivering current - the second half of "status"."""

    _attr_translation_key = "reason_for_no_current"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _REASON_OPTIONS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_reason_for_no_current"

    @property
    def _code(self) -> int | None:
        value = (self.coordinator.data or {}).get("reasonForNoCurrent")
        return None if value is None else int(value)

    @property
    def native_value(self) -> str | None:
        """The reason slug, or None for a code with no mapping yet."""
        code = self._code
        # An enum sensor may not report a state outside its own options list.
        if code not in REASON_FOR_NO_CURRENT:
            return None
        return reason_for_no_current_slug(code)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The raw code and what is known about it."""
        code = self._code
        return {
            "code": code,
            "known": code in REASON_FOR_NO_CURRENT,
            "confirmed": code in CONFIRMED_REASON_CODES,
            "description": reason_for_no_current(code),
        }
