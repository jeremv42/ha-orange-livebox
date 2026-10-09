"""Fixtures for the Orange Livebox tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orange_livebox.api import LiveboxData
from custom_components.orange_livebox.const import DOMAIN
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)

SERIAL = "AN2200000000000"

USER_INPUT = {
    CONF_HOST: "192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
    CONF_SSL: False,
    CONF_VERIFY_SSL: False,
}

DEVICE_INFO = {
    "Manufacturer": "Sagemcom",
    "ModelName": "SagemcomFast5670_LB6",
    "ProductClass": "Livebox 6",
    "SerialNumber": SERIAL,
    "HardwareVersion": "SG_LB6_1.0.0",
    "SoftwareVersion": "SG60-fr-4.67.12.1",
    "BaseMAC": "AA:BB:CC:DD:EE:FF",
    "UpTime": 3600,
    "ExternalIPAddress": "203.0.113.10",
}


def make_data() -> LiveboxData:
    return LiveboxData(
        info=dict(DEVICE_INFO),
        wan={
            "LinkType": "gpon",
            "LinkState": "up",
            "ConnectionState": "Bound",
            "IPAddress": "203.0.113.10",
            "IPv6Address": "2001:db8::1",
        },
        gpon={
            "SignalRxPower": -19500,
            "SignalTxPower": 2300,
            "ONUState": "O5_Operation",
        },
        wan_stats={"RxBytes": 123456789, "TxBytes": 987654},
        wifi={"Enable": True, "Status": True},
        guest_wifi={"Enable": False},
        iptv={"IPTVStatus": "Available"},
        voip_lines=[
            {
                "trunk": "SIP-Trunk",
                "name": "LINE1",
                "enable": "Enabled",
                "status": "Up",
                "directoryNumber": "+33100000000",
            }
        ],
        devices={
            "11:22:33:44:55:66": {
                "mac": "11:22:33:44:55:66",
                "name": "phone",
                "ip": "192.168.1.20",
                "active": True,
                "type": "Mobile",
                "interface": "wl0",
                "last_connection": None,
            },
            "11:22:33:44:55:77": {
                "mac": "11:22:33:44:55:77",
                "name": "laptop",
                "ip": "192.168.1.21",
                "active": False,
                "type": "Computer",
                "interface": "eth1",
                "last_connection": None,
            },
        },
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, title="Livebox 6", unique_id=SERIAL, data=USER_INPUT
    )


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Patch the Livebox client used by the integration and the config flow."""
    with patch(
        "custom_components.orange_livebox.coordinator.LiveboxClient", autospec=True
    ) as client_cls:
        client = client_cls.return_value
        client.async_get_device_info.return_value = dict(DEVICE_INFO)
        client.async_fetch_all.side_effect = make_data
        yield client
