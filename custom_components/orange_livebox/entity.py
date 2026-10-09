"""Base entity for the Orange Livebox integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_SSL
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LiveboxCoordinator


class LiveboxEntity(CoordinatorEntity[LiveboxCoordinator]):
    """An entity attached to the Livebox device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LiveboxCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        info = coordinator.data.info
        assert entry.unique_id is not None
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        scheme = "https" if entry.data.get(CONF_SSL) else "http"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            connections=(
                {(CONNECTION_NETWORK_MAC, format_mac(mac))}
                if (mac := info.get("BaseMAC"))
                else set()
            ),
            manufacturer=info.get("Manufacturer") or "Orange",
            model=info.get("ProductClass") or info.get("ModelName"),
            model_id=info.get("ModelName"),
            name="Livebox",
            serial_number=info.get("SerialNumber"),
            sw_version=info.get("SoftwareVersion"),
            hw_version=info.get("HardwareVersion"),
            configuration_url=f"{scheme}://{entry.data[CONF_HOST]}",
        )
