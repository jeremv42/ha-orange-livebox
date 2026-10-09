"""Binary sensors for the Orange Livebox integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LiveboxData
from .coordinator import LiveboxConfigEntry, LiveboxCoordinator
from .entity import LiveboxEntity

PARALLEL_UPDATES = 0


def _wan_connected(data: LiveboxData) -> bool | None:
    if state := data.wan.get("ConnectionState"):
        return state in ("Bound", "Connected")
    if state := data.wan.get("LinkState"):
        return state == "up"
    return None


@dataclass(frozen=True, kw_only=True)
class LiveboxBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Livebox binary sensor."""

    value_fn: Callable[[LiveboxData], bool | None]
    exists_fn: Callable[[LiveboxData], bool] = lambda _: True


BINARY_SENSORS: tuple[LiveboxBinarySensorDescription, ...] = (
    LiveboxBinarySensorDescription(
        key="wan",
        translation_key="wan",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        exists_fn=lambda data: bool(data.wan),
        value_fn=_wan_connected,
    ),
    LiveboxBinarySensorDescription(
        key="iptv",
        translation_key="iptv",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        exists_fn=lambda data: data.iptv is not None,
        value_fn=lambda data: (data.iptv or {}).get("IPTVStatus") == "Available",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Livebox binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        LiveboxBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.exists_fn(coordinator.data)
    ]
    entities.extend(
        LiveboxPhoneLineSensor(coordinator, line)
        for line in coordinator.data.voip_lines
        if line.get("name")
    )
    async_add_entities(entities)


class LiveboxBinarySensor(LiveboxEntity, BinarySensorEntity):
    """A Livebox binary sensor."""

    entity_description: LiveboxBinarySensorDescription

    def __init__(
        self,
        coordinator: LiveboxCoordinator,
        description: LiveboxBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)


class LiveboxPhoneLineSensor(LiveboxEntity, BinarySensorEntity):
    """Registration state of a telephony line."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "phone_line"

    def __init__(self, coordinator: LiveboxCoordinator, line: dict[str, Any]) -> None:
        """Initialize the phone line sensor."""
        self._line_name: str = line["name"]
        super().__init__(coordinator, f"voip_{self._line_name}")
        self._attr_translation_placeholders = {
            "line": line.get("directoryNumber") or self._line_name
        }

    @property
    def _line(self) -> dict[str, Any] | None:
        return next(
            (
                line
                for line in self.coordinator.data.voip_lines
                if line.get("name") == self._line_name
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return if the line is still reported."""
        return super().available and self._line is not None

    @property
    def is_on(self) -> bool | None:
        """Return True when the line is registered."""
        return (self._line or {}).get("status") == "Up"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return line details."""
        line = self._line or {}
        return {
            "directory_number": line.get("directoryNumber"),
            "enabled": line.get("enable"),
            "status": line.get("status"),
        }
