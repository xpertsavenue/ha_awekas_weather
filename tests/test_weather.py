"""Tests for the AWEKAS Weather weather entity and binary sensor."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_TIME,
    ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_WIND_SPEED,
    DOMAIN as WEATHER_DOMAIN,
    SERVICE_GET_FORECASTS,
    WeatherEntityFeature,
)
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.awekas_weather.const import UPDATE_INTERVAL

from . import get_entity_id, setup_integration


async def test_weather_state(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the current weather."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(get_entity_id(hass, mock_config_entry, "weather", None))
    assert state.state == ATTR_CONDITION_PARTLYCLOUDY
    assert state.attributes[ATTR_WEATHER_TEMPERATURE] == 14.5
    assert state.attributes[ATTR_WEATHER_WIND_SPEED] == 6.4


async def test_daily_forecast(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the daily forecast starts at the local midnight of each day."""
    freezer.move_to(
        datetime(2026, 3, 10, 15, 30, tzinfo=dt_util.get_default_time_zone())
    )
    await setup_integration(hass, mock_config_entry)
    entity_id = get_entity_id(hass, mock_config_entry, "weather", None)

    response = await hass.services.async_call(
        WEATHER_DOMAIN,
        SERVICE_GET_FORECASTS,
        {"entity_id": entity_id, "type": "daily"},
        blocking=True,
        return_response=True,
    )
    forecast = response[entity_id]["forecast"]

    assert len(forecast) == 3
    assert [day[ATTR_FORECAST_TIME] for day in forecast] == [
        dt_util.start_of_local_day(datetime(2026, 3, day)).isoformat()
        for day in (10, 11, 12)
    ]
    assert forecast[1][ATTR_FORECAST_CONDITION] == ATTR_CONDITION_RAINY
    # Unknown condition codes are not guessed
    assert forecast[2].get(ATTR_FORECAST_CONDITION) is None


async def test_forecast_subscription_is_updated(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test forecast subscribers receive new data after a coordinator update."""
    await setup_integration(hass, mock_config_entry)
    entity_id = get_entity_id(hass, mock_config_entry, "weather", None)

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "weather/subscribe_forecast",
            "forecast_type": "daily",
            "entity_id": entity_id,
        }
    )
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["forecast"][0]["temperature"] == 15

    day0 = {**awekas_data["forecast"]["day0"], "fc_temp_max": 17}
    mock_awekas_client.async_get_current.return_value = {
        **awekas_data,
        "forecast": {**awekas_data["forecast"], "day0": day0},
    }
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    update = await client.receive_json()
    assert update["event"]["forecast"][0]["temperature"] == 17


async def test_binary_sensor(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the rain binary sensor."""
    await setup_integration(hass, mock_config_entry)
    entity_id = get_entity_id(hass, mock_config_entry, "binary_sensor", "itsraining")
    assert hass.states.get(entity_id).state == STATE_OFF

    mock_awekas_client.async_get_current.return_value = {
        **awekas_data,
        "current": {**awekas_data["current"], "itsraining": 1},
    }
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_ON


def _with_report(data: dict[str, Any], condition: int) -> dict[str, Any]:
    return {**data, "current": {**data["current"], "condition": condition}}


@pytest.mark.parametrize(
    ("condition", "hour", "expected"),
    [
        # Weather report of the station
        (19, 12, ATTR_CONDITION_LIGHTNING_RAINY),
        (11, 12, ATTR_CONDITION_RAINY),
        (1, 12, ATTR_CONDITION_SUNNY),
        (1, 2, ATTR_CONDITION_CLEAR_NIGHT),
        # No report: today's forecast
        (0, 12, ATTR_CONDITION_PARTLYCLOUDY),
    ],
)
async def test_weather_report(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    condition: int,
    hour: int,
    expected: str,
) -> None:
    """Test the current condition comes from the weather report."""
    freezer.move_to(
        datetime(2026, 6, 10, hour, 0, tzinfo=dt_util.get_default_time_zone())
    )
    mock_awekas_client.async_get_current.return_value = _with_report(
        awekas_data, condition
    )
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(get_entity_id(hass, mock_config_entry, "weather", None))
    assert state.state == expected


async def test_weather_without_forecast(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    awekas_data: dict[str, Any],
) -> None:
    """Test no forecast is offered without Stationsweb subscription."""
    data = {key: value for key, value in awekas_data.items() if key != "forecast"}
    mock_awekas_client.async_get_current.return_value = data
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(get_entity_id(hass, mock_config_entry, "weather", None))
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == 0


async def test_weather_supports_forecast(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the daily forecast is offered and the position is shown."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(get_entity_id(hass, mock_config_entry, "weather", None))
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        WeatherEntityFeature.FORECAST_DAILY
    )
    assert state.attributes[ATTR_LATITUDE] == 47.878335611136543
    assert state.attributes[ATTR_LONGITUDE] == 14.133530512089315
    assert state.attributes["elevation"] == 480
