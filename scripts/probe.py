"""Dump what a Livebox answers to the calls used by the integration.

Useful to check which services your model supports and the exact payloads.

    .venv/bin/python scripts/probe.py [--host 192.168.1.1] > probe-full.json
    .venv/bin/python scripts/probe.py --raw > probe-raw.json
    .venv/bin/python scripts/probe.py --call NMC.Wifi get

The password is read from $LIVEBOX_PASSWORD, or asked interactively.

The output contains personal data (MACs, IPs, serial number): review it
before sharing it anywhere.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime
import getpass
import importlib.util
import json
import os
from pathlib import Path
import sys

import aiohttp

API_PATH = (
    Path(__file__).parent.parent / "custom_components" / "orange_livebox" / "api.py"
)
# Load api.py directly so the integration package (which imports HA) is not needed.
_spec = importlib.util.spec_from_file_location("livebox_api", API_PATH)
api = importlib.util.module_from_spec(_spec)
sys.modules["livebox_api"] = api
_spec.loader.exec_module(api)

# Calls known on various Livebox models, tried one by one by --raw.
RAW_CALLS: list[tuple[str, str, dict | None]] = [
    ("DeviceInfo", "get", None),
    ("NMC", "get", None),
    ("NMC", "getWANStatus", None),
    ("NMC.Wifi", "get", None),
    ("NMC.Guest", "get", None),
    ("NMC.OrangeTV", "getIPTVStatus", None),
    ("NMC.IPv6", "get", None),
    ("NeMo.Intf.data", "getMIBs", {"mibs": "dsl"}),
    ("NeMo.Intf.data", "getNetDevStats", None),
    ("NeMo.Intf.data", "getMIBs", None),
    ("NeMo.Intf.veip0", "getMIBs", {"mibs": "gpon"}),
    ("NeMo.Intf.veip0", "getNetDevStats", None),
    ("NeMo.Intf.dsl0", "getDSLStats", None),
    ("NeMo.Intf.lan", "getMIBs", {"mibs": "base wlanvap"}),
    ("HomeLan", "getWANCounters", None),
    ("HomeLan", "getResults", None),
    ("Devices", "get", {"expression": "physical and !self and !voice"}),
    ("Hosts", "getDevices", None),
    ("VoiceService.VoiceApplication", "listTrunks", None),
    ("VoiceService.VoiceApplication", "getCallList", None),
    ("Firewall", "getFirewallLevel", None),
    ("Firewall", "getFirewallIPv6Level", None),
    ("DHCPv4.Server.Pool.default", "getStaticLeases", None),
    ("Time", "getTime", None),
    ("UPnP-IGD", "get", None),
    ("DynDNS", "getHosts", None),
    ("Scheduler", "getCompleteSchedules", {"type": "WLAN"}),
    ("SpeedTest", "getWANResults", None),
    ("Diagnostics", "get", None),
    ("UserInterface", "getState", None),
    ("TopologyDiagnostics", "buildTopology", {"SendXmlFile": False}),
]


async def raw_dump(client) -> dict:
    """Try every RAW_CALLS entry, recording the reply or the error."""
    results = {}
    for service, method, params in RAW_CALLS:
        key = f"{service}.{method}" + (f" {json.dumps(params)}" if params else "")
        try:
            results[key] = await client.async_call(service, method, params)
        except api.LiveboxError as err:
            results[key] = {"error": f"{type(err).__name__}: {err}"}
        print(f"{key}: {'error' if 'error' in results[key] else 'ok'}", file=sys.stderr)
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="192.168.1.1")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.environ.get("LIVEBOX_PASSWORD"))
    parser.add_argument("--ssl", action="store_true")
    parser.add_argument(
        "--call",
        nargs="+",
        metavar=("SERVICE", "METHOD"),
        help="raw call: SERVICE METHOD [JSON_PARAMETERS]",
    )
    parser.add_argument(
        "--raw", action="store_true", help="try all known calls, keep raw replies"
    )
    args = parser.parse_args()
    if not args.password:
        args.password = getpass.getpass("Livebox admin password: ")

    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    ) as session:
        client = api.LiveboxClient(
            session, args.host, args.username, args.password, ssl=args.ssl
        )
        if args.call:
            service, method, *params = args.call
            result = await client.async_call(
                service, method, json.loads(params[0]) if params else None
            )
        elif args.raw:
            result = await raw_dump(client)
        else:
            result = asdict(await client.async_fetch_all())
    print(json.dumps(result, indent=2, ensure_ascii=False, default=_default))


def _default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value))


if __name__ == "__main__":
    asyncio.run(main())
