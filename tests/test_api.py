"""Tests for the Livebox API client against a fake /ws endpoint."""

from __future__ import annotations

import json

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from custom_components.orange_livebox.api import (
    CONTENT_TYPE,
    LiveboxApiError,
    LiveboxAuthError,
    LiveboxClient,
)

pytestmark = pytest.mark.enable_socket


class FakeLivebox:
    """Very small emulation of the sysbus endpoint."""

    def __init__(self) -> None:
        self.password = "secret"
        self.contexts: set[str] = set()
        self.logins = 0
        self.calls: list[tuple[str, str]] = []

    async def handle(self, request: web.Request) -> web.Response:
        assert request.content_type == CONTENT_TYPE
        body = json.loads(await request.text())
        if request.headers.get("Authorization") == "X-Sah-Login":
            self.logins += 1
            if body["parameters"]["password"] != self.password:
                return web.json_response({"status": None, "data": {}})
            context = f"ctx{self.logins}"
            self.contexts.add(context)
            resp = web.json_response(
                {"status": 0, "data": {"contextID": context, "username": "admin"}}
            )
            resp.set_cookie("sessid", context)
            return resp

        context = request.headers.get("X-Context")
        if context not in self.contexts or request.cookies.get("sessid") != context:
            return web.json_response(
                {
                    "result": {
                        "errors": [{"error": 13, "description": "Permission denied"}]
                    }
                }
            )
        self.calls.append((body["service"], body["method"]))
        match body["service"], body["method"]:
            case "DeviceInfo", "get":
                return web.json_response(
                    {"status": {"SerialNumber": "SN", "UpTime": 10}}
                )
            case "NMC", "getWANStatus":
                return web.json_response(
                    {"status": True, "data": {"LinkType": "vdsl", "LinkState": "up"}}
                )
            case "NeMo.Intf.data", "getMIBs":
                return web.json_response(
                    {"status": {"dsl": {"dsl0": {"DownstreamCurrRate": 50000}}}}
                )
            case "Devices", "get":
                return web.json_response(
                    {
                        "status": [
                            {
                                "Key": "AA:BB:CC:00:00:01",
                                "PhysAddress": "AA:BB:CC:00:00:01",
                                "Name": "tv",
                                "Active": True,
                            },
                            {"Key": "self", "Name": "ignored"},
                        ]
                    }
                )
        return web.json_response(
            {
                "result": {
                    "errors": [
                        {
                            "error": 196618,
                            "description": "Object or parameter not found",
                        }
                    ]
                }
            }
        )


@pytest.fixture
async def fake_box():
    box = FakeLivebox()
    app = web.Application()
    app.router.add_post("/ws", box.handle)
    server = TestServer(app)
    await server.start_server()
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    ) as session:
        yield box, session, f"{server.host}:{server.port}"
    await server.close()


async def test_fetch_all(fake_box) -> None:
    box, session, host = fake_box
    client = LiveboxClient(session, host, "admin", "secret")

    data = await client.async_fetch_all()

    assert data.info["SerialNumber"] == "SN"
    assert data.wan["LinkType"] == "vdsl"
    assert data.dsl == {"DownstreamCurrRate": 50000}
    assert data.gpon is None
    assert data.wifi is None
    assert list(data.devices) == ["aa:bb:cc:00:00:01"]
    assert data.devices["aa:bb:cc:00:00:01"]["active"] is True

    # Unsupported calls are not retried on the next refresh.
    calls_before = len(box.calls)
    await client.async_fetch_all()
    assert ("NMC.Wifi", "get") not in box.calls[calls_before:]
    assert box.logins == 1


async def test_relogin_when_session_expires(fake_box) -> None:
    box, session, host = fake_box
    client = LiveboxClient(session, host, "admin", "secret")
    await client.async_get_device_info()

    box.contexts.clear()
    assert (await client.async_get_device_info())["SerialNumber"] == "SN"
    assert box.logins == 2


async def test_bad_password(fake_box) -> None:
    _, session, host = fake_box
    client = LiveboxClient(session, host, "admin", "wrong")
    with pytest.raises(LiveboxAuthError):
        await client.async_get_device_info()


async def test_api_error(fake_box) -> None:
    _, session, host = fake_box
    client = LiveboxClient(session, host, "admin", "secret")
    with pytest.raises(LiveboxApiError):
        await client.async_call("Nope", "get")
