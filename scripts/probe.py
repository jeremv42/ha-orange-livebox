"""Dump what a Livebox answers to the calls used by the integration.

Useful to check which services your model supports and the exact payloads.

    .venv/bin/python scripts/probe.py --password 'xxxx' [--host 192.168.1.1]
    .venv/bin/python scripts/probe.py --password 'xxxx' --call NMC.Wifi get

The output contains personal data (MACs, IPs, serial number): review it
before sharing it anywhere.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime
import importlib.util
import json
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


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="192.168.1.1")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--ssl", action="store_true")
    parser.add_argument(
        "--call",
        nargs="+",
        metavar=("SERVICE", "METHOD"),
        help="raw call: SERVICE METHOD [JSON_PARAMETERS]",
    )
    args = parser.parse_args()

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
        else:
            result = asdict(await client.async_fetch_all())
    print(json.dumps(result, indent=2, ensure_ascii=False, default=_default))


def _default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value))


if __name__ == "__main__":
    asyncio.run(main())
