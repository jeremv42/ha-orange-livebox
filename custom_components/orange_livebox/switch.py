"""Switches for the Orange Livebox integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LiveboxClient, LiveboxData, LiveboxError
from .const import DOMAIN
from .coordinator import LiveboxConfigEntry, LiveboxCoordinator
from .entity import LiveboxEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LiveboxSwitchDescription(SwitchEntityDescription):
    """Describe a Livebox switch."""

    state_fn: Callable[[LiveboxData], dict[str, Any] | None]
    set_fn: Callable[[LiveboxClient, bool], Awaitable[None]]


SWITCHES: tuple[LiveboxSwitchDescription, ...] = (
    LiveboxSwitchDescription(
        key="wifi",
        translation_key="wifi",
        state_fn=lambda data: data.wifi,
        set_fn=lambda client, enable: client.async_set_wifi(enable),
    ),
    LiveboxSwitchDescription(
        key="guest_wifi",
        translation_key="guest_wifi",
        state_fn=lambda data: data.guest_wifi,
        set_fn=lambda client, enable: client.async_set_guest_wifi(enable),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Livebox switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        LiveboxSwitch(coordinator, description)
        for description in SWITCHES
        if description.state_fn(coordinator.data) is not None
    )


class LiveboxSwitch(LiveboxEntity, SwitchEntity):
    """A Livebox switch."""

    entity_description: LiveboxSwitchDescription

    def __init__(
        self, coordinator: LiveboxCoordinator, description: LiveboxSwitchDescription
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the switch state."""
        state = self.entity_description.state_fn(self.coordinator.data)
        return None if state is None else bool(state.get("Enable"))

    async def _async_set(self, enable: bool) -> None:
        try:
            await self.entity_description.set_fn(self.coordinator.client, enable)
        except LiveboxError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set(False)
