"""Data update coordinator for the Orange Livebox integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
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
        # (time, rx_bytes, tx_bytes) of the last counters reading
        self._last_counters: tuple[datetime, int, int] | None = None

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

        self._update_rates(data)
        return data

    def _update_rates(self, data: LiveboxData) -> None:
        """Compute the WAN speed from two readings of the traffic counters."""
        if (stats := data.wan_stats) is None:
            return
        sample = (
            stats.get("updated") or dt_util.utcnow(),
            stats["rx_bytes"],
            stats["tx_bytes"],
        )
        previous, self._last_counters = self._last_counters, sample
        if previous is None:
            return
        if sample[0] == previous[0]:
            # The box did not refresh its counters since the last poll.
            if self.data:
                data.download_rate = self.data.download_rate
                data.upload_rate = self.data.upload_rate
            return
        elapsed = (sample[0] - previous[0]).total_seconds()
        received = sample[1] - previous[1]
        sent = sample[2] - previous[2]
        rebooted = self.data is not None and self.data.boot_time != data.boot_time
        if elapsed <= 0 or received < 0 or sent < 0 or rebooted:
            # Counters reset (Livebox restart): wait for the next reading.
            return
        data.download_rate = round(received * 8 / elapsed / 1000, 1)
        data.upload_rate = round(sent * 8 / elapsed / 1000, 1)
