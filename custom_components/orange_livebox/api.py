"""Async client for the Orange Livebox local API (sysbus JSON-RPC over ``/ws``).

This module deliberately has no Home Assistant dependency so it can be used
standalone (see ``scripts/probe.py``) to explore what a given box exposes.

Protocol summary:
  * Every call is a POST to ``/ws`` with content type
    ``application/x-sah-ws-4-call+json`` and a body
    ``{"service": ..., "method": ..., "parameters": {...}}``.
  * Login is ``sah.Device.Information.createContext`` with the header
    ``Authorization: X-Sah-Login``; it returns a ``contextID`` and sets a
    session cookie. Later calls send ``Authorization: X-Sah <contextID>`` and
    ``X-Context: <contextID>`` and must reuse the cookie jar.
  * Replies look like ``{"status": ..., "data": ...}`` (sometimes wrapped in
    ``{"result": ...}``), with an ``errors`` list on failure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

CONTENT_TYPE = "application/x-sah-ws-4-call+json"
ERROR_PERMISSION_DENIED = 13

DEVICES_EXPRESSION = "physical and !self and !voice"


class LiveboxError(Exception):
    """Base class for Livebox errors."""


class LiveboxConnectionError(LiveboxError):
    """The Livebox could not be reached or sent an unreadable reply."""


class LiveboxAuthError(LiveboxError):
    """The credentials were rejected or the session expired."""


class LiveboxApiError(LiveboxError):
    """The Livebox rejected a call (e.g. service not available on this model)."""


@dataclass(slots=True)
class LiveboxData:
    """Snapshot of everything read from the Livebox in one refresh."""

    info: dict[str, Any]
    wan: dict[str, Any] = field(default_factory=dict)
    dsl: dict[str, Any] | None = None
    gpon: dict[str, Any] | None = None
    wan_stats: dict[str, Any] | None = None
    wifi: dict[str, Any] | None = None
    guest_wifi: dict[str, Any] | None = None
    iptv: dict[str, Any] | None = None
    voip_lines: list[dict[str, Any]] = field(default_factory=list)
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    boot_time: datetime | None = None


def _payload(result: dict[str, Any]) -> Any:
    """Return the useful part of a reply (``data`` when filled, else ``status``)."""
    data = result.get("data")
    if isinstance(data, (dict, list)) and data:
        return data
    return result.get("status")


def _first_mib(status: Any, mib: str) -> dict[str, Any] | None:
    """Extract the first interface block of a ``getMIBs`` reply."""
    if not isinstance(status, dict):
        return None
    interfaces = status.get(mib)
    if not isinstance(interfaces, dict) or not interfaces:
        return None
    return next(iter(interfaces.values()))


def _normalize_device(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a ``Devices.get`` or ``Hosts.getDevices`` entry."""
    mac = raw.get("PhysAddress") or raw.get("physAddress") or raw.get("Key")
    if not mac or ":" not in mac:
        return None
    return {
        "mac": mac.lower(),
        "name": raw.get("Name") or raw.get("hostName") or mac,
        "ip": raw.get("IPAddress") or raw.get("ipAddress"),
        "active": bool(raw.get("Active", raw.get("active", False))),
        "type": raw.get("DeviceType") or raw.get("deviceType"),
        "interface": raw.get("Layer2Interface")
        or raw.get("InterfaceName")
        or raw.get("interfaceType"),
        "last_connection": raw.get("LastConnection"),
    }


class LiveboxClient:
    """Minimal async client for the Livebox sysbus API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        *,
        ssl: bool = False,
        verify_ssl: bool = False,
        timeout: float = 15.0,
    ) -> None:
        """Initialize the client.

        The session must use a cookie jar that accepts cookies from IP
        addresses (``aiohttp.CookieJar(unsafe=True)``).
        """
        scheme = "https" if ssl else "http"
        self._url = f"{scheme}://{host}/ws"
        self._session = session
        self._username = username
        self._password = password
        self._ssl = verify_ssl if ssl else False
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._context_id: str | None = None
        self._login_lock = asyncio.Lock()
        self._unsupported: set[str] = set()

    async def _post(self, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        try:
            async with self._session.post(
                self._url,
                data=json.dumps(payload),
                headers={"Content-Type": CONTENT_TYPE, **headers},
                ssl=self._ssl,
                timeout=self._timeout,
            ) as resp:
                if resp.status in (401, 403):
                    raise LiveboxAuthError(f"HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except LiveboxError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise LiveboxConnectionError(
                f"Error communicating with {self._url}: {err}"
            ) from err

    async def async_login(self) -> None:
        """Open a new session on the Livebox."""
        async with self._login_lock:
            await self._login()

    async def _login(self) -> None:
        body = await self._post(
            {
                "service": "sah.Device.Information",
                "method": "createContext",
                "parameters": {
                    "applicationName": "webui",
                    "username": self._username,
                    "password": self._password,
                },
            },
            {"Authorization": "X-Sah-Login"},
        )
        context_id = (body.get("data") or {}).get("contextID")
        if body.get("status") != 0 or not context_id:
            raise LiveboxAuthError("Login rejected by the Livebox")
        self._context_id = context_id

    async def _ensure_context(self) -> str:
        async with self._login_lock:
            if self._context_id is None:
                await self._login()
            assert self._context_id is not None
            return self._context_id

    async def async_call(
        self, service: str, method: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call a sysbus method, logging in again once if the session expired."""
        context_id = await self._ensure_context()
        try:
            return await self._call(context_id, service, method, parameters)
        except LiveboxAuthError:
            if self._context_id == context_id:
                self._context_id = None
        context_id = await self._ensure_context()
        return await self._call(context_id, service, method, parameters)

    async def _call(
        self,
        context_id: str,
        service: str,
        method: str,
        parameters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        body = await self._post(
            {"service": service, "method": method, "parameters": parameters or {}},
            {"Authorization": f"X-Sah {context_id}", "X-Context": context_id},
        )
        result = body.get("result", body) if isinstance(body, dict) else {}
        if errors := result.get("errors"):
            if any(
                err.get("error") == ERROR_PERMISSION_DENIED
                or "permission denied" in str(err.get("description", "")).lower()
                for err in errors
            ):
                raise LiveboxAuthError(f"{service}.{method}: {errors}")
            raise LiveboxApiError(f"{service}.{method}: {errors}")
        return result

    async def _optional(
        self, service: str, method: str, parameters: dict[str, Any] | None = None
    ) -> Any:
        """Call a method that may not exist on every model.

        Methods the box rejects are remembered and not called again.
        """
        key = f"{service}.{method}{json.dumps(parameters or {}, sort_keys=True)}"
        if key in self._unsupported:
            return None
        try:
            return _payload(await self.async_call(service, method, parameters))
        except LiveboxApiError as err:
            _LOGGER.debug("Disabling unsupported call %s: %s", key, err)
            self._unsupported.add(key)
            return None

    # Read helpers -----------------------------------------------------------

    async def async_get_device_info(self) -> dict[str, Any]:
        """Return model, serial number, firmware, uptime..."""
        info = _payload(await self.async_call("DeviceInfo", "get"))
        if not isinstance(info, dict):
            raise LiveboxApiError(f"Unexpected DeviceInfo reply: {info!r}")
        return info

    async def async_get_wan_status(self) -> dict[str, Any]:
        """Return WAN link type/state, public IP addresses, DNS servers..."""
        wan = await self._optional("NMC", "getWANStatus")
        return wan if isinstance(wan, dict) else {}

    async def async_get_mib(self, interface: str, mib: str) -> dict[str, Any] | None:
        """Return one MIB block (``dsl``, ``gpon``...) of a NeMo interface."""
        status = await self._optional(
            f"NeMo.Intf.{interface}", "getMIBs", {"mibs": mib}
        )
        return _first_mib(status, mib)

    async def async_get_wan_stats(self) -> dict[str, Any] | None:
        """Return the WAN traffic counters (RxBytes, TxBytes...)."""
        stats = await self._optional("NeMo.Intf.data", "getNetDevStats")
        return stats if isinstance(stats, dict) else None

    async def async_get_wifi(self) -> dict[str, Any] | None:
        """Return the global Wi-Fi state."""
        wifi = await self._optional("NMC.Wifi", "get")
        return wifi if isinstance(wifi, dict) else None

    async def async_get_guest_wifi(self) -> dict[str, Any] | None:
        """Return the guest Wi-Fi state."""
        guest = await self._optional("NMC.Guest", "get")
        return guest if isinstance(guest, dict) else None

    async def async_get_iptv(self) -> dict[str, Any] | None:
        """Return the Orange TV service status."""
        iptv = await self._optional("NMC.OrangeTV", "getIPTVStatus")
        return iptv if isinstance(iptv, dict) else None

    async def async_get_voip_lines(self) -> list[dict[str, Any]]:
        """Return the telephony lines, flattened across trunks."""
        trunks = await self._optional("VoiceService.VoiceApplication", "listTrunks")
        lines: list[dict[str, Any]] = []
        for trunk in trunks if isinstance(trunks, list) else []:
            for line in trunk.get("trunk_lines") or []:
                lines.append({"trunk": trunk.get("name"), **line})
        return lines

    async def async_get_devices(self) -> dict[str, dict[str, Any]]:
        """Return the devices known by the Livebox, keyed by lowercase MAC."""
        raw = await self._optional("Devices", "get", {"expression": DEVICES_EXPRESSION})
        if not isinstance(raw, list):
            raw = await self._optional("Hosts", "getDevices")
        devices: dict[str, dict[str, Any]] = {}
        for entry in raw if isinstance(raw, list) else []:
            if device := _normalize_device(entry):
                devices[device["mac"]] = device
        return devices

    async def async_fetch_all(self) -> LiveboxData:
        """Read everything in one go.

        Calls are sequential on purpose: the Livebox CPU is weak and parallel
        requests tend to time out.
        """
        data = LiveboxData(info=await self.async_get_device_info())
        data.wan = await self.async_get_wan_status()
        link_type = str(data.wan.get("LinkType", "")).lower()
        if "dsl" in link_type:
            data.dsl = await self.async_get_mib("data", "dsl")
        elif link_type in ("gpon", "sfp", "ethernet_fiber") or not link_type:
            data.gpon = await self.async_get_mib("veip0", "gpon")
        data.wan_stats = await self.async_get_wan_stats()
        data.wifi = await self.async_get_wifi()
        data.guest_wifi = await self.async_get_guest_wifi()
        data.iptv = await self.async_get_iptv()
        data.voip_lines = await self.async_get_voip_lines()
        data.devices = await self.async_get_devices()
        return data

    # Actions ----------------------------------------------------------------

    async def async_set_wifi(self, enable: bool) -> None:
        """Enable or disable all Wi-Fi radios."""
        await self.async_call("NMC.Wifi", "set", {"Enable": enable, "Status": enable})

    async def async_set_guest_wifi(self, enable: bool) -> None:
        """Enable or disable the guest Wi-Fi."""
        await self.async_call("NMC.Guest", "set", {"Enable": enable})

    async def async_reboot(self) -> None:
        """Reboot the Livebox."""
        await self.async_call("NMC", "reboot", {"reason": "Home Assistant"})

    async def async_ring_phone(self) -> None:
        """Make the phones plugged into the Livebox ring."""
        await self.async_call("VoiceService.VoiceApplication", "ring")
