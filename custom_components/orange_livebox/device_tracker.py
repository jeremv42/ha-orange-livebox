"""Device tracker for the devices connected to the Orange Livebox."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LiveboxConfigEntry, LiveboxCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Track every device the Livebox knows, adding new ones as they appear."""
    coordinator = entry.runtime_data
    tracked: set[str] = set()

    @callback
    def _async_add_new_devices() -> None:
        new = coordinator.data.devices.keys() - tracked
        tracked.update(new)
        async_add_entities(LiveboxDeviceTracker(coordinator, mac) for mac in new)

    _async_add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_devices))


class LiveboxDeviceTracker(CoordinatorEntity[LiveboxCoordinator], ScannerEntity):
    """A device seen by the Livebox."""

    def __init__(self, coordinator: LiveboxCoordinator, mac: str) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = mac
        self._attr_name = self._device.get("name") or mac

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.data.devices.get(self._mac, {})

    @property
    def mac_address(self) -> str:
        """Return the MAC address."""
        return self._mac

    @property
    def hostname(self) -> str | None:
        """Return the hostname."""
        return self._device.get("name")

    @property
    def ip_address(self) -> str | None:
        """Return the IP address."""
        return self._device.get("ip")

    @property
    def is_connected(self) -> bool:
        """Return True when the device is connected to the Livebox."""
        return bool(self._device.get("active"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra details."""
        device = self._device
        return {
            "device_type": device.get("type"),
            "interface": device.get("interface"),
            "last_connection": device.get("last_connection"),
        }
