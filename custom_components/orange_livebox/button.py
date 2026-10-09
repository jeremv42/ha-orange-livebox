"""Buttons for the Orange Livebox integration."""

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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LiveboxClient, LiveboxData, LiveboxError
from .const import DOMAIN
from .coordinator import LiveboxConfigEntry, LiveboxCoordinator
from .entity import LiveboxEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LiveboxButtonDescription(ButtonEntityDescription):
    """Describe a Livebox button."""

    press_fn: Callable[[LiveboxClient], Awaitable[None]]
    exists_fn: Callable[[LiveboxData], bool] = lambda _: True


BUTTONS: tuple[LiveboxButtonDescription, ...] = (
    LiveboxButtonDescription(
        key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.async_reboot(),
    ),
    LiveboxButtonDescription(
        key="ring_phone",
        translation_key="ring_phone",
        exists_fn=lambda data: bool(data.voip_lines),
        press_fn=lambda client: client.async_ring_phone(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Livebox buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        LiveboxButton(coordinator, description)
        for description in BUTTONS
        if description.exists_fn(coordinator.data)
    )


class LiveboxButton(LiveboxEntity, ButtonEntity):
    """A Livebox button."""

    entity_description: LiveboxButtonDescription

    def __init__(
        self, coordinator: LiveboxCoordinator, description: LiveboxButtonDescription
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Press the button."""
        try:
            await self.entity_description.press_fn(self.coordinator.client)
        except LiveboxError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"error": str(err)},
            ) from err
