"""Sensor platform for AWEKAS Weather integration."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Literal, Self

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator
from .entity import AwekasEntity, sensor_active

PARALLEL_UPDATES = 0

ATTR_TIMESTAMP = "timestamp"

type ValueFn = Callable[[dict[str, Any]], Any]


def _value(section: str, key: str) -> ValueFn:
    """Return a function reading one value of a section of an API response."""
    return lambda data: (data.get(section) or {}).get(key)


def _timestamp(section: str, key: str) -> ValueFn:
    """Return a function reading a Unix timestamp as datetime."""

    def _read(data: dict[str, Any]) -> datetime | None:
        value = (data.get(section) or {}).get(key)
        if not isinstance(value, int | float):
            return None
        return dt_util.utc_from_timestamp(value)

    return _read


def _date(data: dict[str, Any]) -> date | None:
    """Return the expiry date of the Stationsweb subscription."""
    stationsweb = data.get("stationsweb") or {}
    if not stationsweb.get("enabled"):
        return None
    try:
        return date.fromisoformat(str(stationsweb.get("period")))
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    """Convert an API value to float."""
    try:
        return float(value)
    except TypeError, ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class AwekasSensorEntityDescription(SensorEntityDescription):
    """Describes an AWEKAS sensor."""

    value_fn: ValueFn
    # Key in the 'sensorstatus' section of the station API
    status_key: str | None = None
    # Time of a daily minimum or maximum, shown as attribute
    timestamp_fn: ValueFn | None = None
    # Response the value is read from: current data or station data
    source: Literal["current", "station"] = "current"
    available_when_stale: bool = False


# Units, device and state classes of the measured quantities
_TEMPERATURE: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
    "device_class": SensorDeviceClass.TEMPERATURE,
    "state_class": SensorStateClass.MEASUREMENT,
}
_HUMIDITY: dict[str, Any] = {
    "native_unit_of_measurement": PERCENTAGE,
    "device_class": SensorDeviceClass.HUMIDITY,
    "state_class": SensorStateClass.MEASUREMENT,
}
_PRESSURE: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfPressure.HPA,
    "device_class": SensorDeviceClass.PRESSURE,
    "state_class": SensorStateClass.MEASUREMENT,
}
# Soil moisture is measured as soil water tension
_SOIL_MOISTURE: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfPressure.CBAR,
    "device_class": SensorDeviceClass.PRESSURE,
    "state_class": SensorStateClass.MEASUREMENT,
}
_WIND_SPEED: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "device_class": SensorDeviceClass.WIND_SPEED,
    "state_class": SensorStateClass.MEASUREMENT,
}
_WIND_DIRECTION: dict[str, Any] = {
    "native_unit_of_measurement": DEGREE,
    "device_class": SensorDeviceClass.WIND_DIRECTION,
    "state_class": SensorStateClass.MEASUREMENT_ANGLE,
}
_PRECIPITATION: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfLength.MILLIMETERS,
    "device_class": SensorDeviceClass.PRECIPITATION,
}
_RAIN_RATE: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
    "device_class": SensorDeviceClass.PRECIPITATION_INTENSITY,
    "state_class": SensorStateClass.MEASUREMENT,
}
_IRRADIANCE: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfIrradiance.WATTS_PER_SQUARE_METER,
    "device_class": SensorDeviceClass.IRRADIANCE,
    "state_class": SensorStateClass.MEASUREMENT,
}
_ILLUMINANCE: dict[str, Any] = {
    "native_unit_of_measurement": LIGHT_LUX,
    "device_class": SensorDeviceClass.ILLUMINANCE,
    "state_class": SensorStateClass.MEASUREMENT,
}
_PARTICULATE: dict[str, Any] = {
    "native_unit_of_measurement": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    "state_class": SensorStateClass.MEASUREMENT,
}
_PLAIN: dict[str, Any] = {"state_class": SensorStateClass.MEASUREMENT}


def _current(
    key: str,
    kind: dict[str, Any],
    status_key: str | None,
    *,
    section: str = "current",
    **kwargs: Any,
) -> AwekasSensorEntityDescription:
    """Describe a current value."""
    return AwekasSensorEntityDescription(
        key=key,
        translation_key=key,
        value_fn=_value(section, key),
        status_key=status_key,
        **kind,
        **kwargs,
    )


def _day(
    api_key: str,
    kind: dict[str, Any],
    status_key: str | None,
    *,
    timestamp_key: str | None = "",
    enabled: bool = False,
    **kwargs: Any,
) -> AwekasSensorEntityDescription:
    """Describe a daily statistic, disabled by default.

    The time of the value is read from '<api_key>_ts' unless another
    timestamp_key is given, None means the value has no time.
    """
    if timestamp_key == "":
        timestamp_key = f"{api_key}_ts"
    return AwekasSensorEntityDescription(
        key=f"day_{api_key}",
        translation_key=f"day_{api_key}",
        value_fn=_value("day", api_key),
        timestamp_fn=_timestamp("day", timestamp_key) if timestamp_key else None,
        status_key=status_key,
        entity_registry_enabled_default=enabled,
        **kind,
        **kwargs,
    )


PRECIPITATION_TODAY = _value("current", "precipitation")

SENSOR_TYPES: tuple[AwekasSensorEntityDescription, ...] = (
    # Temperature / dew point
    _current("temperature", _TEMPERATURE, "temperature"),
    _current("dewpoint", _TEMPERATURE, "temperature"),
    _current("windchill", _TEMPERATURE, "temperature"),
    _current("wetbulbtemperature", _TEMPERATURE, "temperature"),
    _current("indoortemperature", _TEMPERATURE, "indoortemperature"),
    # Humidity
    _current("humidity", _HUMIDITY, "humidity"),
    _current("indoorhumidity", _HUMIDITY, "indoorhumidity"),
    # Air pressure, the tendency is -2 (high falling) ... 2 (high rising)
    _current("airpress_rel", _PRESSURE, "airpressure"),
    _current("tendency", _PLAIN, "airpressure"),
    # Precipitation since midnight station time
    _current(
        "precipitation",
        _PRECIPITATION,
        "precipitation",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    _current("rainrate", _RAIN_RATE, "rainrate"),
    # Rolling window, the value can decrease at any time
    _current(
        "precipitation_1h",
        _PRECIPITATION,
        "precipitation",
        section="1h",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Wind
    _current("windspeed", _WIND_SPEED, "wind"),
    _current("gustspeed", _WIND_SPEED, "wind"),
    _current("winddirection", _WIND_DIRECTION, "wind"),
    # Sun and radiation
    _current("uv", _PLAIN, "uv"),
    _current("solar", _IRRADIANCE, "solar"),
    _current("brightness", _ILLUMINANCE, None),
    _current(
        "suntime",
        _PLAIN,
        None,
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
    ),
    # Snow and additional channels
    _current(
        "snowheight",
        _PLAIN,
        None,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        device_class=SensorDeviceClass.DISTANCE,
    ),
    *(_current(f"temp{i}", _TEMPERATURE, f"soiltemp{i}") for i in range(1, 5)),
    *(_current(f"humidity{i}", _HUMIDITY, f"humidity{i}") for i in range(1, 5)),
    *(
        _current(f"soilmoisture{i}", _SOIL_MOISTURE, f"soilmoisture{i}")
        for i in range(1, 5)
    ),
    *(_current(f"leafwetness{i}", _PLAIN, f"leafwetness{i}") for i in (1, 2)),
    # Air quality
    _current(
        "airquality_pm1", _PARTICULATE, "airquality", device_class=SensorDeviceClass.PM1
    ),
    _current(
        "airquality_pm2",
        _PARTICULATE,
        "airquality",
        device_class=SensorDeviceClass.PM25,
    ),
    _current(
        "airquality_pm10",
        _PARTICULATE,
        "airquality",
        device_class=SensorDeviceClass.PM10,
    ),
    # Daily statistics
    _day("temp_min", _TEMPERATURE, "temperature"),
    _day("temp_max", _TEMPERATURE, "temperature"),
    _day("intemp_min", _TEMPERATURE, "indoortemperature"),
    _day("intemp_max", _TEMPERATURE, "indoortemperature"),
    _day("dewpoint_min", _TEMPERATURE, "temperature"),
    _day("dewpoint_max", _TEMPERATURE, "temperature"),
    _day("hum_min", _HUMIDITY, "humidity"),
    _day("hum_max", _HUMIDITY, "humidity"),
    _day("inhum_min", _HUMIDITY, "indoorhumidity"),
    _day("inhum_max", _HUMIDITY, "indoorhumidity"),
    _day("airp_rel_min", _PRESSURE, "airpressure"),
    _day("airp_rel_max", _PRESSURE, "airpressure"),
    _day("windspeed_min", _WIND_SPEED, "wind"),
    _day("windspeed_max", _WIND_SPEED, "wind"),
    _day("winddir_max", _WIND_DIRECTION, "wind", timestamp_key="windspeed_max_ts"),
    _day("gustspeed_min", _WIND_SPEED, "wind"),
    _day("gustspeed_max", _WIND_SPEED, "wind"),
    _day("gustdir_max", _WIND_DIRECTION, "wind", timestamp_key="gustspeed_max_ts"),
    _day("rainrate_max", _RAIN_RATE, "rainrate", enabled=True),
    # Rolling window, the value can decrease at any time
    _day(
        "precipitation_24h",
        _PRECIPITATION,
        "precipitation",
        timestamp_key=None,
        enabled=True,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _day("solar_max", _IRRADIANCE, "solar"),
    _day("uv_max", _PLAIN, "uv"),
    _day("brightness_max", _ILLUMINANCE, None),
    # 24 hour averages
    _day(
        "airquality_pm1",
        _PARTICULATE,
        "airquality",
        timestamp_key=None,
        device_class=SensorDeviceClass.PM1,
    ),
    _day(
        "airquality_pm2",
        _PARTICULATE,
        "airquality",
        timestamp_key=None,
        device_class=SensorDeviceClass.PM25,
    ),
    _day(
        "airquality_pm10",
        _PARTICULATE,
        "airquality",
        timestamp_key=None,
        device_class=SensorDeviceClass.PM10,
    ),
    # Diagnostics
    AwekasSensorEntityDescription(
        key="datatimestamp",
        translation_key="datatimestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_timestamp("current", "datatimestamp"),
        available_when_stale=True,
    ),
    AwekasSensorEntityDescription(
        key="stationsweb_expiry",
        translation_key="stationsweb_expiry",
        device_class=SensorDeviceClass.DATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_date,
        source="station",
        available_when_stale=True,
    ),
)


@dataclass(frozen=True, kw_only=True)
class AwekasPrecipitationTotalEntityDescription(SensorEntityDescription):
    """Describes a sensor summing up the daily precipitation over a period."""

    period_fn: Callable[[datetime], str]


PRECIPITATION_TOTAL_TYPES: tuple[AwekasPrecipitationTotalEntityDescription, ...] = (
    AwekasPrecipitationTotalEntityDescription(
        key="precipitation_monthly",
        translation_key="precipitation_monthly",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        period_fn=lambda now: f"{now.year}-{now.month:02d}",
    ),
    AwekasPrecipitationTotalEntityDescription(
        key="precipitation_yearly",
        translation_key="precipitation_yearly",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        period_fn=lambda now: str(now.year),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwekasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AWEKAS sensors based on a config entry."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        AwekasSensor(coordinator, description) for description in SENSOR_TYPES
    ]
    entities.extend(
        AwekasPrecipitationTotalSensor(coordinator, description)
        for description in PRECIPITATION_TOTAL_TYPES
    )
    async_add_entities(entities)


class AwekasSensor(AwekasEntity, SensorEntity):
    """Representation of an AWEKAS sensor."""

    entity_description: AwekasSensorEntityDescription

    def __init__(
        self,
        coordinator: AwekasDataUpdateCoordinator,
        description: AwekasSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        # Sensors the station does not have are created disabled. Without
        # the sensor status of the station API, a missing value decides.
        active = sensor_active(coordinator, description.status_key)
        if active is False or (active is None and self.native_value is None):
            self._attr_entity_registry_enabled_default = False

    @property
    def _data(self) -> dict[str, Any]:
        if self.entity_description.source == "station":
            return self.coordinator.station or {}
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """Return if the station currently reports this value."""
        return (
            super().available
            and self.native_value is not None
            and (
                self.entity_description.available_when_stale
                or not self.coordinator.data_is_stale
            )
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the time of a daily minimum or maximum."""
        if self.entity_description.timestamp_fn is None:
            return None
        return {ATTR_TIMESTAMP: self.entity_description.timestamp_fn(self._data)}


@dataclass
class PrecipitationTotalStoredData(ExtraStoredData):
    """Data needed to continue a precipitation total after a restart."""

    total: float
    last_daily: float | None
    period: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the data."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self | None:
        """Initialize the stored data from a dict."""
        try:
            return cls(
                total=float(data["total"]),
                last_daily=_as_float(data["last_daily"]),
                period=data["period"],
            )
        except KeyError, TypeError, ValueError:
            return None


class AwekasPrecipitationTotalSensor(AwekasEntity, RestoreEntity, SensorEntity):
    """Sum of the daily precipitation of the station over a month or year.

    The station only reports the precipitation since midnight station time.
    Every increase of that value is added to the total, which starts again
    from zero when a new period begins in the time zone of the station.
    """

    entity_description: AwekasPrecipitationTotalEntityDescription

    def __init__(
        self,
        coordinator: AwekasDataUpdateCoordinator,
        description: AwekasPrecipitationTotalEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._total: float | None = None
        self._last_daily: float | None = None
        self._period: str | None = None
        active = sensor_active(coordinator, "precipitation")
        if active is False or (
            active is None and PRECIPITATION_TODAY(coordinator.data) is None
        ):
            self._attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        """Restore the total and process the current data."""
        await super().async_added_to_hass()

        if (extra := await self.async_get_last_extra_data()) and (
            stored := PrecipitationTotalStoredData.from_dict(extra.as_dict())
        ):
            self._total = stored.total
            self._last_daily = stored.last_daily
            self._period = stored.period
        elif (state := await self.async_get_last_state()) and (
            total := _as_float(state.state)
        ) is not None:
            # State of the former utility meter based sensor: it already
            # contains today's precipitation, so only count from now on.
            self._total = total
            self._period = self.entity_description.period_fn(
                dt_util.as_local(state.last_changed)
            )

        self._accumulate()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Add the new precipitation and write the state."""
        self._accumulate()
        super()._handle_coordinator_update()

    def _accumulate(self) -> None:
        """Add the precipitation since the last update to the total."""
        daily = _as_float(PRECIPITATION_TODAY(self.coordinator.data))
        if daily is None:
            return

        period = self.entity_description.period_fn(self.coordinator.station_time())
        if self._total is None:
            # First start: include what already fell today
            self._total = daily
        else:
            if period != self._period:
                self._total = 0.0
            if self._last_daily is None:
                increase = 0.0
            elif daily >= self._last_daily:
                increase = daily - self._last_daily
            else:
                # The daily value was reset at midnight
                increase = daily
            self._total = round(self._total + increase, 2)

        self._period = period
        self._last_daily = daily

    @callback
    def async_set_total(self, value: float) -> None:
        """Set the total, e.g. to correct it afterwards.

        The total continues from this value. Rain that the station reported
        before is not added again.
        """
        self._total = round(value, 2)
        self._period = self.entity_description.period_fn(
            self.coordinator.station_time()
        )
        self._last_daily = _as_float(PRECIPITATION_TODAY(self.coordinator.data))
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        """Return the precipitation total."""
        return self._total

    @property
    def extra_restore_state_data(self) -> PrecipitationTotalStoredData | None:
        """Return the data to restore after a restart."""
        if self._total is None:
            return None
        return PrecipitationTotalStoredData(
            total=self._total, last_daily=self._last_daily, period=self._period
        )
