"""Sensors for the Orange Livebox integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import LiveboxData
from .coordinator import LiveboxConfigEntry
from .entity import LiveboxEntity

PARALLEL_UPDATES = 0


def _tenths(value: Any) -> float | None:
    """Convert a TR-098 value expressed in 0.1 dB."""
    return round(value / 10, 1) if isinstance(value, (int, float)) else None


def _dbm(value: Any) -> float | None:
    """Convert a GPON optical power, which some firmwares report in 0.001 dBm."""
    if not isinstance(value, (int, float)):
        return None
    return round(value / 1000 if abs(value) > 100 else value, 2)


@dataclass(frozen=True, kw_only=True)
class LiveboxSensorDescription(SensorEntityDescription):
    """Describe a Livebox sensor."""

    value_fn: Callable[[LiveboxData], StateType | datetime]
    exists_fn: Callable[[LiveboxData], bool] = lambda _: True


def _dsl(key: str, convert: Callable[[Any], Any] = lambda v: v):
    return lambda data: convert((data.dsl or {}).get(key))


def _has_dsl(data: LiveboxData) -> bool:
    return data.dsl is not None


def _has_gpon(data: LiveboxData) -> bool:
    return data.gpon is not None


def _has_stats(data: LiveboxData) -> bool:
    return data.wan_stats is not None


def _ipv6(data: LiveboxData) -> str | None:
    return data.wan.get("IPv6Address") or (data.ipv6 or {}).get("IPv6Address") or None


def _missed_calls(data: LiveboxData) -> int:
    return sum(
        call.get("callType") == "missed" and not call.get("viewed")
        for call in data.calls or []
    )


SENSORS: tuple[LiveboxSensorDescription, ...] = (
    LiveboxSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda data: "UpTime" in data.info,
        value_fn=lambda data: data.boot_time,
    ),
    LiveboxSensorDescription(
        key="external_ip",
        translation_key="external_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            data.wan.get("IPAddress") or data.info.get("ExternalIPAddress")
        ),
    ),
    LiveboxSensorDescription(
        key="external_ipv6",
        translation_key="external_ipv6",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        exists_fn=lambda data: "IPv6Address" in data.wan or data.ipv6 is not None,
        value_fn=_ipv6,
    ),
    LiveboxSensorDescription(
        key="link_type",
        translation_key="link_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda data: "LinkType" in data.wan,
        value_fn=lambda data: data.wan.get("LinkType"),
    ),
    LiveboxSensorDescription(
        key="connected_devices",
        translation_key="connected_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(d["active"] for d in data.devices.values()),
    ),
    # Traffic counters
    LiveboxSensorDescription(
        key="wan_received",
        translation_key="wan_received",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        exists_fn=_has_stats,
        value_fn=lambda data: (data.wan_stats or {}).get("rx_bytes"),
    ),
    LiveboxSensorDescription(
        key="wan_sent",
        translation_key="wan_sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        exists_fn=_has_stats,
        value_fn=lambda data: (data.wan_stats or {}).get("tx_bytes"),
    ),
    LiveboxSensorDescription(
        key="download_rate",
        translation_key="download_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        exists_fn=_has_stats,
        value_fn=lambda data: data.download_rate,
    ),
    LiveboxSensorDescription(
        key="upload_rate",
        translation_key="upload_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        exists_fn=_has_stats,
        value_fn=lambda data: data.upload_rate,
    ),
    # xDSL line
    LiveboxSensorDescription(
        key="dsl_downstream_rate",
        translation_key="dsl_downstream_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        exists_fn=_has_dsl,
        value_fn=_dsl("DownstreamCurrRate"),
    ),
    LiveboxSensorDescription(
        key="dsl_upstream_rate",
        translation_key="dsl_upstream_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        exists_fn=_has_dsl,
        value_fn=_dsl("UpstreamCurrRate"),
    ),
    LiveboxSensorDescription(
        key="dsl_downstream_max_rate",
        translation_key="dsl_downstream_max_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        entity_registry_enabled_default=False,
        exists_fn=_has_dsl,
        value_fn=_dsl("DownstreamMaxRate"),
    ),
    LiveboxSensorDescription(
        key="dsl_upstream_max_rate",
        translation_key="dsl_upstream_max_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        entity_registry_enabled_default=False,
        exists_fn=_has_dsl,
        value_fn=_dsl("UpstreamMaxRate"),
    ),
    LiveboxSensorDescription(
        key="dsl_downstream_noise_margin",
        translation_key="dsl_downstream_noise_margin",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_dsl,
        value_fn=_dsl("DownstreamNoiseMargin", _tenths),
    ),
    LiveboxSensorDescription(
        key="dsl_upstream_noise_margin",
        translation_key="dsl_upstream_noise_margin",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_dsl,
        value_fn=_dsl("UpstreamNoiseMargin", _tenths),
    ),
    LiveboxSensorDescription(
        key="dsl_downstream_attenuation",
        translation_key="dsl_downstream_attenuation",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_dsl,
        value_fn=_dsl("DownstreamAttenuation", _tenths),
    ),
    LiveboxSensorDescription(
        key="dsl_upstream_attenuation",
        translation_key="dsl_upstream_attenuation",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_dsl,
        value_fn=_dsl("UpstreamAttenuation", _tenths),
    ),
    # Fiber (GPON) line
    LiveboxSensorDescription(
        key="fiber_rx_power",
        translation_key="fiber_rx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_gpon,
        value_fn=lambda data: _dbm((data.gpon or {}).get("SignalRxPower")),
    ),
    LiveboxSensorDescription(
        key="fiber_tx_power",
        translation_key="fiber_tx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_gpon,
        value_fn=lambda data: _dbm((data.gpon or {}).get("SignalTxPower")),
    ),
    LiveboxSensorDescription(
        key="fiber_onu_state",
        translation_key="fiber_onu_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_gpon,
        value_fn=lambda data: (
            (data.gpon or {}).get("OnuState")
            or (data.gpon or {}).get("ONUState")
            or data.wan.get("GponState")
        ),
    ),
    LiveboxSensorDescription(
        key="fiber_temperature",
        translation_key="fiber_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda data: "Temperature" in (data.gpon or {}),
        value_fn=lambda data: (data.gpon or {}).get("Temperature"),
    ),
    # Telephony and security
    LiveboxSensorDescription(
        key="missed_calls",
        translation_key="missed_calls",
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=lambda data: data.calls is not None,
        value_fn=_missed_calls,
    ),
    LiveboxSensorDescription(
        key="firewall_level",
        translation_key="firewall_level",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda data: data.firewall_level is not None,
        value_fn=lambda data: data.firewall_level,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LiveboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Livebox sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        LiveboxSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(coordinator.data)
    )


class LiveboxSensor(LiveboxEntity, SensorEntity):
    """A Livebox sensor."""

    entity_description: LiveboxSensorDescription

    def __init__(self, coordinator, description: LiveboxSensorDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
