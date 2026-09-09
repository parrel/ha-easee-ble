"""Poll one charger over BLE and cache the result for the entities."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from bleak.exc import BleakError
from easee_ble import (
    BtEnableMode,
    EaseeCharger,
    EaseeCommandRefused,
    EaseeConnectionError,
    EaseeError,
    JPakeError,
    PhaseMode,
    Request,
    Session,
)
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_PIN, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COMMAND_TIMEOUT,
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_LINK_AGE,
    REFRESH_COOLDOWN,
    UPDATE_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class ChargerUnavailable(HomeAssistantError):
    """The charger is not in range or not advertising."""

    def __init__(self, serial: str, address: str) -> None:
        """Say which charger could not be found."""
        super().__init__(
            f"charger {serial} ({address}) is not in range / not advertising",
            translation_domain=DOMAIN,
            translation_key="not_in_range",
            translation_placeholders={"serial": serial, "address": address},
        )


class EaseeBleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll one charger over BLE, over a connection held open for good."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator for one configured charger."""
        # Before super(), which hooks async_shutdown onto the entry: raising after
        # that leaves a half-built coordinator for HA to shut down.
        self.address: str = entry.data[CONF_ADDRESS]
        self.serial: str = entry.data[CONF_SERIAL]
        self._pin: str = entry.data[CONF_PIN]
        self._charger: EaseeCharger | None = None
        self._connected_at: float = 0.0
        # Polls and commands share one link, and only one write may be in flight.
        self._lock = asyncio.Lock()
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.serial}",
            update_interval=self._interval(entry),
            # The stock 10s debounce assumes an expensive refresh; a poll is 0.4s.
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REFRESH_COOLDOWN, immediate=True
            ),
        )

    @staticmethod
    def _interval(entry: ConfigEntry) -> timedelta:
        """The poll interval currently configured on the entry."""
        return timedelta(
            seconds=entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds()
            )
        )

    @property
    def link_lost(self) -> bool:
        """Whether a link we are holding has gone away under us."""
        charger = self._charger
        return charger is not None and not charger.connected

    @property
    def charger(self) -> EaseeCharger | None:
        """The live connection, if there is one. For diagnostics."""
        return self._charger

    def _device(self):
        """The BLEDevice for this charger, or raise if it is not in range."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise ChargerUnavailable(self.serial, self.address)
        return device

    async def _ready(self, *, retire_stale: bool = False) -> EaseeCharger:
        """The connected charger, reconnecting if the link is gone."""
        charger = self._charger
        if charger is not None and charger.connected:
            age = self.hass.loop.time() - self._connected_at
            if not retire_stale or age < MAX_LINK_AGE:
                return charger
            _LOGGER.info(
                "charger %s: retiring the link at %.0fs old and reconnecting",
                self.serial,
                age,
            )
        await self._drop()
        charger = EaseeCharger(
            self._device(), self._pin, self.serial, on_disconnect=self._on_link_lost
        )
        await charger.connect()
        # Never adopt a charger already disconnected: a drop during connect is lost.
        if not charger.connected:
            await charger.disconnect()
            raise EaseeConnectionError(
                f"charger {self.serial}: the link was reported lost during connect"
            )
        _LOGGER.info("charger %s: connected via %s", self.serial, charger.radio)
        self._charger = charger
        self._connected_at = self.hass.loop.time()
        return charger

    def _on_link_lost(self, charger: EaseeCharger) -> None:
        """The backend says the link went; start recovering now, not next cycle."""
        if charger is not self._charger:
            return
        _LOGGER.info("charger %s: the link dropped; reconnecting", self.serial)
        self.config_entry.async_create_background_task(
            self.hass,
            self.async_request_refresh(),
            name=f"{DOMAIN} {self.serial} reconnect",
            eager_start=False,
        )

    async def _drop(self) -> None:
        """Disconnect and forget, releasing the charger's connection slot."""
        charger, self._charger = self._charger, None
        if charger is not None:
            await asyncio.shield(charger.disconnect())

    async def _async_update_data(self) -> dict[str, Any]:
        """Read the charger, reconnecting first if needed."""
        # Connecting is inside the try: failing there is ordinary and transient.
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT), self._lock:
                try:
                    charger = await self._ready(retire_stale=True)
                    return await charger.poll()
                except ChargerUnavailable as exc:
                    # Nothing connected and nothing in range: no link to drop.
                    raise UpdateFailed(str(exc)) from exc
                except JPakeError as exc:
                    # Retrying a rejected handshake will not help; ask for a new PIN.
                    await self._drop()
                    raise ConfigEntryAuthFailed(
                        f"charger {self.serial} rejected the PIN: {exc}"
                    ) from exc
                except (EaseeError, BleakError) as exc:
                    # A malformed reply is a link problem too; rebuild the connection.
                    await self._drop()
                    raise UpdateFailed(str(exc)) from exc
        except TimeoutError as exc:
            # Dropping outside the lock: whoever holds it is stuck and must be freed.
            _LOGGER.warning(
                "charger %s: update stalled past %.0fs; dropping the connection",
                self.serial,
                UPDATE_TIMEOUT,
            )
            await self._drop()
            raise UpdateFailed(
                f"charger {self.serial}: update stalled past {UPDATE_TIMEOUT:.0f}s"
            ) from exc

    async def _apply(self, make_request: Callable[[Session], Request]) -> None:
        """Send one command over the held connection, then refresh."""
        try:
            async with asyncio.timeout(COMMAND_TIMEOUT), self._lock:
                try:
                    charger = await self._ready()
                    await charger.perform(make_request)
                except EaseeCommandRefused as exc:
                    # The charger replied and said no, so the link is fine.
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="command_refused",
                        translation_placeholders={
                            "serial": self.serial,
                            "error": str(exc),
                        },
                    ) from exc
                except (EaseeError, BleakError) as exc:
                    await self._drop()
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="command_failed",
                        translation_placeholders={
                            "serial": self.serial,
                            "error": str(exc),
                        },
                    ) from exc
        except TimeoutError as exc:
            await self._drop()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_timeout",
                translation_placeholders={
                    "serial": self.serial,
                    "timeout": f"{COMMAND_TIMEOUT:.0f}",
                },
            ) from exc
        # Outside the lock: refreshing takes it again.
        await self.async_request_refresh()

    async def async_apply_options(self) -> None:
        """Re-read the entry's options; cheaper than the reload HA would do."""
        self.update_interval = self._interval(self.config_entry)

    async def async_shutdown(self) -> None:
        """Release the charger's connection slot when Home Assistant is done."""
        await super().async_shutdown()
        await self._drop()

    async def async_set_led_brightness(self, percent: int) -> None:
        """Set the status LED brightness, 0-100%."""
        await self._apply(lambda s: s.set_led_brightness(percent))

    async def async_set_max_charger_current(self, amperes: int) -> None:
        """Set the charger's maximum current."""
        await self._apply(lambda s: s.set_max_charger_current(amperes))

    async def async_set_dynamic_charger_current(self, amperes: int) -> None:
        """Set the charger's dynamic current limit."""
        await self._apply(lambda s: s.set_dynamic_charger_current(amperes))

    async def async_set_phase_mode(self, mode: PhaseMode) -> None:
        """Set the phase mode."""
        await self._apply(lambda s: s.set_phase_mode(mode))

    async def async_set_charger_enabled(self, enabled: bool) -> None:
        """Switch the charger on or off."""
        await self._apply(lambda s: s.set_charger_enabled(enabled))

    async def async_set_cable_locked(self, locked: bool) -> None:
        """Lock or unlock the cable permanently."""
        await self._apply(lambda s: s.set_cable_locked(locked))

    async def async_set_bt_enable_mode(self, mode: BtEnableMode) -> None:
        """Set how the charger's Bluetooth radio behaves."""
        await self._apply(lambda s: s.set_bt_enable_mode(mode))
