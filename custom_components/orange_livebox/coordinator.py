"""Data update coordinator for the Orange Livebox integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import LiveboxAuthError, LiveboxClient, LiveboxData, LiveboxError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Uptime is sampled with a few seconds of jitter: only move the boot time
# when it really changed (i.e. after a reboot).
BOOT_TIME_TOLERANCE = timedelta(minutes=2)

type LiveboxConfigEntry = ConfigEntry[LiveboxCoordinator]


def async_create_client(hass: HomeAssistant, data: Mapping[str, Any]) -> LiveboxClient:
    """Create a client with its own cookie jar (the Livebox session is a cookie)."""
    session = async_create_clientsession(
        hass,
        verify_ssl=data.get(CONF_VERIFY_SSL, False),
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    return LiveboxClient(
        session,
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        ssl=data.get(CONF_SSL, False),
        verify_ssl=data.get(CONF_VERIFY_SSL, False),
    )


class LiveboxCoordinator(DataUpdateCoordinator[LiveboxData]):
    """Poll the Livebox."""

    config_entry: LiveboxConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: LiveboxConfigEntry, client: LiveboxClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> LiveboxData:
        try:
            data = await self.client.async_fetch_all()
        except LiveboxAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except LiveboxError as err:
            raise UpdateFailed(str(err)) from err

        if isinstance(uptime := data.info.get("UpTime"), int):
            boot_time = (dt_util.utcnow() - timedelta(seconds=uptime)).replace(
                microsecond=0
            )
            previous = self.data.boot_time if self.data else None
            if previous and abs(boot_time - previous) < BOOT_TIME_TOLERANCE:
                boot_time = previous
            data.boot_time = boot_time
        elif self.data:
            data.boot_time = self.data.boot_time
        return data
