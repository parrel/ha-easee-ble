"""The charger's status LED strip, modelled as a dimmable light."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EaseeBleConfigEntry
from .coordinator import EaseeBleCoordinator
from .entity import EaseeBleEntity

PARALLEL_UPDATES = 0

_DEFAULT_BRIGHTNESS_PCT = 100


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EaseeBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LED light."""
    async_add_entities([EaseeLedLight(entry.runtime_data)])


class EaseeLedLight(EaseeBleEntity, LightEntity):
    """Easee's ledStripBrightness, a single 0-100 setting with no on/off flag."""

    _attr_translation_key = "led"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: EaseeBleCoordinator) -> None:
        """Initialise the light."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_led_brightness"
        self._last_brightness_pct = _DEFAULT_BRIGHTNESS_PCT

    @property
    def _brightness_pct(self) -> int | None:
        value = (self.coordinator.data or {}).get("ledStripBrightness")
        return None if value is None else int(value)

    @property
    def is_on(self) -> bool | None:
        """Whether the LED strip is lit at all."""
        pct = self._brightness_pct
        return None if pct is None else pct > 0

    @property
    def brightness(self) -> int | None:
        """Brightness on Home Assistant's 0-255 scale."""
        pct = self._brightness_pct
        return None if pct is None else round(pct * 255 / 100)

    def _remember_brightness(self) -> None:
        """Keep the last non-zero level, so turning back on can restore it."""
        if pct := self._brightness_pct:
            self._last_brightness_pct = pct

    async def async_added_to_hass(self) -> None:
        """Seed the remembered level from the poll that set us up."""
        self._remember_brightness()
        await super().async_added_to_hass()

    def _handle_coordinator_update(self) -> None:
        self._remember_brightness()
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the LED strip on, at the given or last-used brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        else:
            pct = self._last_brightness_pct
        await self.coordinator.async_set_led_brightness(pct)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED strip off."""
        await self.coordinator.async_set_led_brightness(0)
