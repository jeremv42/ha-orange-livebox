"""Tests for the Orange Livebox setup and entities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.orange_livebox.api import LiveboxAuthError, LiveboxData
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_HOME,
    STATE_NOT_HOME,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .conftest import make_data


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_entities(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.livebox_connected_devices").state == "1"
    assert hass.states.get("sensor.livebox_external_ip").state == "203.0.113.10"
    assert hass.states.get("sensor.livebox_fiber_received_power").state == "-19.5"
    assert hass.states.get("sensor.livebox_fiber_transmitted_power").state == "2.3"
    assert (
        hass.states.get("binary_sensor.livebox_internet_connection").state == STATE_ON
    )
    assert hass.states.get("binary_sensor.livebox_tv_service").state == STATE_ON
    assert (
        hass.states.get("binary_sensor.livebox_phone_line_33100000000").state
        == STATE_ON
    )
    assert hass.states.get("switch.livebox_wi_fi").state == STATE_ON
    assert hass.states.get("sensor.livebox_fiber_onu_state").state == "O5_Operation"
    assert hass.states.get("sensor.livebox_fiber_module_temperature").state == "51"
    assert hass.states.get("sensor.livebox_missed_calls").state == "1"
    assert hass.states.get("sensor.livebox_firewall_level").state == "Low"
    assert hass.states.get("sensor.livebox_data_received").state == "0.123456789"
    # No DSL line on a fiber box.
    assert hass.states.get("sensor.livebox_dsl_download_rate") is None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_device_trackers(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    await _setup(hass, mock_config_entry)

    # Router trackers are disabled by default, like in core integrations.
    for entity_id in ("device_tracker.phone", "device_tracker.laptop"):
        assert entity_registry.async_get(entity_id).disabled_by is not None
        entity_registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("device_tracker.phone").state == STATE_HOME
    assert hass.states.get("device_tracker.laptop").state == STATE_NOT_HOME


async def test_switch_and_button(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)

    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: "switch.livebox_guest_wi_fi"},
        blocking=True,
    )
    mock_client.async_set_guest_wifi.assert_awaited_once_with(False)

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.livebox_restart"}, blocking=True
    )
    mock_client.async_reboot.assert_awaited_once()


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_client.async_fetch_all.side_effect = LiveboxAuthError
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_brand_images(hass: HomeAssistant) -> None:
    integration = await async_get_integration(hass, "orange_livebox")
    assert integration.has_branding


async def test_wan_speed(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    t0 = datetime(2026, 10, 9, 21, 0, tzinfo=UTC)
    readings = iter(
        [
            (t0, 1_000_000, 500_000),
            # +12.5 MB down / +1.25 MB up in 10 s: 10 Mbit/s / 1 Mbit/s
            (t0 + timedelta(seconds=10), 13_500_000, 1_750_000),
            # The box has not refreshed its counters: keep the last speed
            (t0 + timedelta(seconds=10), 13_500_000, 1_750_000),
            # Counters went back to zero (Livebox restart)
            (t0 + timedelta(seconds=40), 2_000, 1_000),
        ]
    )

    def fetch() -> LiveboxData:
        updated, rx, tx = next(readings)
        data = make_data()
        data.wan_stats = {"rx_bytes": rx, "tx_bytes": tx, "updated": updated}
        return data

    mock_client.async_fetch_all.side_effect = fetch
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    def speeds() -> tuple[str, str]:
        return (
            hass.states.get("sensor.livebox_download_speed").state,
            hass.states.get("sensor.livebox_upload_speed").state,
        )

    assert speeds() == (STATE_UNKNOWN, STATE_UNKNOWN)
    for expected in (
        ("10.0", "1.0"),
        ("10.0", "1.0"),
        (STATE_UNKNOWN, STATE_UNKNOWN),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert speeds() == expected
