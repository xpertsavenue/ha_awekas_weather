"""Tests for the AWEKAS Weather sensors."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)
import voluptuous as vol

from custom_components.awekas_weather.api import AwekasConnectionError
from custom_components.awekas_weather.const import DOMAIN, UPDATE_INTERVAL

from . import get_entity_id, setup_integration

STATION_TIME_ZONE = ZoneInfo("Europe/Vienna")


def _local(*args: int) -> datetime:
    """Return a time in the time zone of the station.

    Home Assistant runs in US/Pacific during the tests, the station of the
    fixture in Europe/Vienna.
    """
    return datetime(*args, tzinfo=STATION_TIME_ZONE)


async def _update(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    client: AsyncMock,
    data: dict[str, Any],
    time: datetime,
) -> None:
    """Let the coordinator fetch new data at the given time."""
    client.async_get_current.return_value = data
    freezer.move_to(time)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _with_daily_precipitation(data: dict[str, Any], value: float) -> dict[str, Any]:
    return {**data, "current": {**data["current"], "precipitation": value}}


@pytest.mark.usefixtures("mock_awekas_client")
@pytest.mark.parametrize(
    ("key", "state", "unit", "state_class"),
    [
        ("temperature", "14.5", "°C", SensorStateClass.MEASUREMENT),
        ("windspeed", "6.4", "km/h", SensorStateClass.MEASUREMENT),
        ("gustspeed", "9.7", "km/h", SensorStateClass.MEASUREMENT),
        ("winddirection", "264", "°", SensorStateClass.MEASUREMENT_ANGLE),
        ("precipitation", "1.2", "mm", SensorStateClass.TOTAL_INCREASING),
        ("precipitation_1h", "0.3", "mm", SensorStateClass.MEASUREMENT),
        ("day_precipitation_24h", "2.0", "mm", SensorStateClass.MEASUREMENT),
        ("tendency", "-1", None, SensorStateClass.MEASUREMENT),
        # Units as documented in the API specification
        ("soilmoisture1", "9", "cbar", SensorStateClass.MEASUREMENT),
        ("brightness", "12000", "lx", SensorStateClass.MEASUREMENT),
        ("suntime", "3.5", "h", SensorStateClass.MEASUREMENT),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    key: str,
    state: str,
    unit: str | None,
    state_class: SensorStateClass,
) -> None:
    """Test values, units and state classes of the sensors."""
    await setup_integration(hass, mock_config_entry)

    sensor = hass.states.get(get_entity_id(hass, mock_config_entry, "sensor", key))
    assert sensor.state == state
    assert sensor.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == unit
    assert sensor.attributes[ATTR_STATE_CLASS] == state_class


@pytest.mark.usefixtures("mock_awekas_client")
@pytest.mark.parametrize(
    ("key", "enabled"),
    [
        ("temperature", True),
        # Sensor status of the station API decides
        ("temp1", False),
        ("airquality_pm1", False),
        ("humidity1", True),
        # No sensor status, a missing value decides
        ("snowheight", False),
        ("brightness", True),
        # Daily statistics are disabled by default
        ("day_temp_max", False),
        ("day_airquality_pm2", False),
        ("day_precipitation_24h", True),
        # Station data
        ("stationsweb_expiry", True),
    ],
)
async def test_enabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    key: str,
    enabled: bool,
) -> None:
    """Test only values the station reports are enabled by default."""
    await setup_integration(hass, mock_config_entry)

    entity_id = get_entity_id(hass, mock_config_entry, "sensor", key)
    assert (entity_registry.async_get(entity_id).disabled_by is None) is enabled


async def test_day_wind_speed_is_read_from_day(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the daily wind statistics read the 'day' section."""
    mock_config_entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{mock_config_entry.entry_id}_day_windspeed_max",
        config_entry=mock_config_entry,
        suggested_object_id="day_windspeed_max",
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get("sensor.day_windspeed_max")
    assert state.state == "20.5"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "km/h"


async def test_value_disappears(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a sensor becomes unavailable instead of being removed."""
    await setup_integration(hass, mock_config_entry)
    entity_id = get_entity_id(hass, mock_config_entry, "sensor", "dewpoint")

    data = {**awekas_data, "current": {**awekas_data["current"], "dewpoint": None}}
    await _update(
        hass, freezer, mock_awekas_client, data, dt_util.now() + UPDATE_INTERVAL
    )

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


async def test_precipitation_totals(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test summing up the daily precipitation over a month and a year."""
    freezer.move_to(_local(2026, 1, 31, 12, 0))
    await setup_integration(hass, mock_config_entry)
    monthly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_monthly")
    yearly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_yearly")

    # First start counts what already fell today
    assert hass.states.get(monthly).state == "1.2"
    assert hass.states.get(yearly).state == "1.2"

    # Rain later that day
    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 3.0),
        _local(2026, 1, 31, 18, 0),
    )
    assert hass.states.get(monthly).state == "3.0"
    assert hass.states.get(yearly).state == "3.0"

    # Midnight: the daily value resets and a new month begins
    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 0.4),
        _local(2026, 2, 1, 0, 30),
    )
    assert hass.states.get(monthly).state == "0.4"
    assert hass.states.get(yearly).state == "3.4"

    # Next day within the same month
    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 0.0),
        _local(2026, 2, 2, 0, 5),
    )
    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 1.1),
        _local(2026, 2, 2, 8, 0),
    )
    assert hass.states.get(monthly).state == "1.5"
    assert hass.states.get(yearly).state == "4.5"


async def test_precipitation_total_restore(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the total continues after a restart."""
    freezer.move_to(_local(2026, 1, 15, 12, 0))
    mock_config_entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{mock_config_entry.entry_id}_precipitation_monthly",
        config_entry=mock_config_entry,
        suggested_object_id="precipitation_month",
    )
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.precipitation_month", "10.0"),
                {"total": 10.0, "last_daily": 1.0, "period": "2026-01"},
            )
        ],
    )

    await setup_integration(hass, mock_config_entry)

    # Only the 0.2 mm since the last update before the restart are added
    assert hass.states.get("sensor.precipitation_month").state == "10.2"


async def test_precipitation_total_restore_legacy_state(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test taking over the state of the former utility meter sensor."""
    freezer.move_to(_local(2026, 1, 15, 12, 0))
    mock_config_entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{mock_config_entry.entry_id}_precipitation_monthly",
        config_entry=mock_config_entry,
        suggested_object_id="precipitation_month",
    )
    mock_restore_cache(
        hass,
        [
            State(
                "sensor.precipitation_month",
                "11.6",
                last_changed=_local(2026, 1, 15, 11, 0),
            )
        ],
    )

    await setup_integration(hass, mock_config_entry)
    # Today's precipitation is already part of the restored value
    assert hass.states.get("sensor.precipitation_month").state == "11.6"

    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 1.7),
        _local(2026, 1, 15, 13, 0),
    )
    assert hass.states.get("sensor.precipitation_month").state == "12.1"


async def _enable(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    key: str,
) -> str:
    """Register a sensor that is disabled by default as enabled."""
    entry.add_to_hass(hass)
    return entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_{key}",
        config_entry=entry,
        suggested_object_id=key,
    ).entity_id


async def test_day_statistic_timestamp(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the time of a daily maximum is shown as attribute."""
    entity_id = await _enable(hass, entity_registry, mock_config_entry, "day_temp_max")
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(entity_id)
    assert state.state == "16.2"
    assert state.attributes["timestamp"] == datetime(2026, 1, 1, 13, tzinfo=UTC)


async def test_day_airquality_average(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the 24 hour average of the particulate matter."""
    entity_id = await _enable(
        hass, entity_registry, mock_config_entry, "day_airquality_pm2"
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(entity_id)
    assert state.state == "12.1"
    assert "timestamp" not in state.attributes


@pytest.mark.usefixtures("mock_awekas_client")
async def test_stationsweb_expiry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the expiry date of the Stationsweb subscription."""
    await setup_integration(hass, mock_config_entry)

    entity_id = get_entity_id(hass, mock_config_entry, "sensor", "stationsweb_expiry")
    assert hass.states.get(entity_id).state == "2027-12-31"


async def test_stale_data(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test measurements become unavailable when the station stops uploading."""
    measured = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    freezer.move_to(measured + timedelta(minutes=2))
    mock_awekas_client.async_get_current.return_value = {
        **awekas_data,
        "current": {**awekas_data["current"], "datatimestamp": measured.timestamp()},
    }
    await setup_integration(hass, mock_config_entry)
    temperature = get_entity_id(hass, mock_config_entry, "sensor", "temperature")
    timestamp = get_entity_id(hass, mock_config_entry, "sensor", "datatimestamp")
    raining = get_entity_id(hass, mock_config_entry, "binary_sensor", "itsraining")
    assert hass.states.get(temperature).state == "14.5"
    assert hass.states.get(timestamp).state == "2026-03-10T12:00:00+00:00"

    # The API keeps returning the same old measurement
    freezer.move_to(measured + timedelta(hours=1, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(temperature).state == STATE_UNAVAILABLE
    assert hass.states.get(raining).state == STATE_UNAVAILABLE
    # The time of the last measurement stays visible
    assert hass.states.get(timestamp).state == "2026-03-10T12:00:00+00:00"


async def test_precipitation_period_from_time_offset(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the time offset of the data is used without station data.

    Home Assistant still has January 31 when the station, one hour ahead
    of UTC, already has February 1.
    """
    mock_awekas_client.async_get_station.side_effect = AwekasConnectionError(
        "TimeoutError"
    )

    def data_at(when: datetime, daily: float) -> dict[str, Any]:
        current = {
            **awekas_data["current"],
            "precipitation": daily,
            "datatimestamp": when.timestamp(),
            "timeoffset": 3600,
        }
        return {**awekas_data, "current": current}

    january = datetime(2026, 1, 31, 20, 0, tzinfo=UTC)
    freezer.move_to(january)
    mock_awekas_client.async_get_current.return_value = data_at(january, 5.0)
    await setup_integration(hass, mock_config_entry)
    monthly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_monthly")
    assert hass.states.get(monthly).state == "5.0"

    # 23:30 UTC = 00:30 station time on February 1
    february = datetime(2026, 1, 31, 23, 30, tzinfo=UTC)
    await _update(hass, freezer, mock_awekas_client, data_at(february, 0.4), february)
    assert dt_util.now().month == 1
    assert hass.states.get(monthly).state == "0.4"


async def _set_total(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_precipitation_total",
        {"entity_id": entity_id, "value": value},
        blocking=True,
    )


async def test_set_precipitation_total(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test correcting the month total, the sensor counts on from there."""
    freezer.move_to(_local(2026, 1, 15, 12, 0))
    await setup_integration(hass, mock_config_entry)
    monthly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_monthly")
    yearly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_yearly")
    assert hass.states.get(monthly).state == "1.2"

    await _set_total(hass, monthly, 42.5)

    # Only the selected sensor changes, today's 1.2 mm are not added again
    assert hass.states.get(monthly).state == "42.5"
    assert hass.states.get(yearly).state == "1.2"

    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 2.0),
        _local(2026, 1, 15, 13, 0),
    )
    assert hass.states.get(monthly).state == "43.3"
    assert hass.states.get(yearly).state == "2.0"


async def test_set_precipitation_total_continues_after_month_change(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the corrected total is reset at the end of the period."""
    freezer.move_to(_local(2026, 1, 31, 12, 0))
    await setup_integration(hass, mock_config_entry)
    monthly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_monthly")
    await _set_total(hass, monthly, 80)

    await _update(
        hass,
        freezer,
        mock_awekas_client,
        _with_daily_precipitation(awekas_data, 0.4),
        _local(2026, 2, 1, 0, 30),
    )

    assert hass.states.get(monthly).state == "0.4"


async def test_set_precipitation_total_survives_restart(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the corrected total is stored for the next start."""
    freezer.move_to(_local(2026, 1, 15, 12, 0))
    await setup_integration(hass, mock_config_entry)
    monthly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_monthly")
    await _set_total(hass, monthly, 42.5)

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(monthly).state == "42.5"


@pytest.mark.usefixtures("mock_awekas_client")
@pytest.mark.parametrize("value", [-1, "text", 100001])
async def test_set_precipitation_total_invalid_value(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, value: Any
) -> None:
    """Test values that are no precipitation amount are refused."""
    await setup_integration(hass, mock_config_entry)
    monthly = get_entity_id(hass, mock_config_entry, "sensor", "precipitation_monthly")

    with pytest.raises(vol.Invalid):
        await _set_total(hass, monthly, value)

    assert hass.states.get(monthly).state == "1.2"


@pytest.mark.usefixtures("mock_awekas_client")
async def test_set_precipitation_total_wrong_sensor(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the action refuses sensors that are no precipitation total."""
    await setup_integration(hass, mock_config_entry)
    temperature = get_entity_id(hass, mock_config_entry, "sensor", "temperature")

    with pytest.raises(ServiceValidationError, match=temperature):
        await _set_total(hass, temperature, 10)

    assert hass.states.get(temperature).state == "14.5"
