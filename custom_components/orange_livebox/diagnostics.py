"""Diagnostics for the Orange Livebox integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import LiveboxConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "SerialNumber",
    "BaseMAC",
    "MACAddress",
    "ExternalIPAddress",
    "IPAddress",
    "IPv6Address",
    "IPv6DelegatedPrefix",
    "RemoteGateway",
    "directoryNumber",
    "RegistrationID",
    "devices",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LiveboxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = asdict(entry.runtime_data.data)
    data["device_count"] = len(data["devices"])
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(data, TO_REDACT),
    }
