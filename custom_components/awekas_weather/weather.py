"""Weather platform for AWEKAS Integration."""

from datetime import timedelta
from typing import Any

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.sun import is_up
from homeassistant.util import dt as dt_util

from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator
from .entity import AwekasEntity

PARALLEL_UPDATES = 0

FORECAST_DAYS = 6

ATTR_ELEVATION = "elevation"

# AWEKAS uses the condition codes of WeatherAPI.com for its forecast
CONDITION_MAP: dict[int, str] = {
    1000: ATTR_CONDITION_SUNNY,  # Sunny
    1003: ATTR_CONDITION_PARTLYCLOUDY,  # Partly cloudy
    1006: ATTR_CONDITION_CLOUDY,  # Cloudy
    1009: ATTR_CONDITION_CLOUDY,  # Overcast
    1030: ATTR_CONDITION_FOG,  # Mist
    1063: ATTR_CONDITION_RAINY,  # Patchy rain possible
    1066: ATTR_CONDITION_SNOWY,  # Patchy snow possible
    1069: ATTR_CONDITION_SNOWY_RAINY,  # Patchy sleet possible
    1072: ATTR_CONDITION_SNOWY_RAINY,  # Patchy freezing drizzle possible
    1087: ATTR_CONDITION_LIGHTNING,  # Thundery outbreaks possible
    1114: ATTR_CONDITION_SNOWY,  # Blowing snow
    1117: ATTR_CONDITION_SNOWY,  # Blizzard
    1135: ATTR_CONDITION_FOG,  # Fog
    1147: ATTR_CONDITION_FOG,  # Freezing fog
    1150: ATTR_CONDITION_RAINY,  # Patchy light drizzle
    1153: ATTR_CONDITION_RAINY,  # Light drizzle
    1168: ATTR_CONDITION_SNOWY_RAINY,  # Freezing drizzle
    1171: ATTR_CONDITION_SNOWY_RAINY,  # Heavy freezing drizzle
    1180: ATTR_CONDITION_RAINY,  # Patchy light rain
    1183: ATTR_CONDITION_RAINY,  # Light rain
    1186: ATTR_CONDITION_RAINY,  # Moderate rain at times
    1189: ATTR_CONDITION_RAINY,  # Moderate rain
    1192: ATTR_CONDITION_POURING,  # Heavy rain at times
    1195: ATTR_CONDITION_POURING,  # Heavy rain
    1198: ATTR_CONDITION_SNOWY_RAINY,  # Light freezing rain
    1201: ATTR_CONDITION_SNOWY_RAINY,  # Moderate or heavy freezing rain
    1204: ATTR_CONDITION_SNOWY_RAINY,  # Light sleet
    1207: ATTR_CONDITION_SNOWY_RAINY,  # Moderate or heavy sleet
    1210: ATTR_CONDITION_SNOWY,  # Patchy light snow
    1213: ATTR_CONDITION_SNOWY,  # Light snow
    1216: ATTR_CONDITION_SNOWY,  # Patchy moderate snow
    1219: ATTR_CONDITION_SNOWY,  # Moderate snow
    1222: ATTR_CONDITION_SNOWY,  # Patchy heavy snow
    1225: ATTR_CONDITION_SNOWY,  # Heavy snow
    1237: ATTR_CONDITION_HAIL,  # Ice pellets
    1240: ATTR_CONDITION_RAINY,  # Light rain shower
    1243: ATTR_CONDITION_POURING,  # Moderate or heavy rain shower
    1246: ATTR_CONDITION_POURING,  # Torrential rain shower
    1249: ATTR_CONDITION_SNOWY_RAINY,  # Light sleet showers
    1252: ATTR_CONDITION_SNOWY_RAINY,  # Moderate or heavy sleet showers
    1255: ATTR_CONDITION_SNOWY,  # Light snow showers
    1258: ATTR_CONDITION_SNOWY,  # Moderate or heavy snow showers
    1261: ATTR_CONDITION_HAIL,  # Light showers of ice pellets
    1264: ATTR_CONDITION_HAIL,  # Moderate or heavy showers of ice pellets
    1273: ATTR_CONDITION_LIGHTNING_RAINY,  # Patchy light rain with thunder
    1276: ATTR_CONDITION_LIGHTNING_RAINY,  # Moderate or heavy rain with thunder
    1279: ATTR_CONDITION_SNOWY,  # Patchy light snow with thunder
    1282: ATTR_CONDITION_SNOWY,  # Moderate or heavy snow with thunder
}


# Weather report of the station ('condition', table 4 of the API specification)
REPORT_CONDITION_MAP: dict[int, str] = {
    # 0: no report
    1: ATTR_CONDITION_SUNNY,  # clear
    2: ATTR_CONDITION_SUNNY,  # sunny sky
    3: ATTR_CONDITION_PARTLYCLOUDY,  # partly cloudy
    4: ATTR_CONDITION_CLOUDY,  # cloudy
    5: ATTR_CONDITION_CLOUDY,  # heavy cloudy
    6: ATTR_CONDITION_CLOUDY,  # overcast sky
    7: ATTR_CONDITION_FOG,  # fog
    8: ATTR_CONDITION_RAINY,  # rain showers
    9: ATTR_CONDITION_POURING,  # heavy rain showers
    10: ATTR_CONDITION_RAINY,  # light rain
    11: ATTR_CONDITION_RAINY,  # rain
    12: ATTR_CONDITION_POURING,  # heavy rain
    13: ATTR_CONDITION_SNOWY,  # light snow
    14: ATTR_CONDITION_SNOWY,  # snow
    15: ATTR_CONDITION_SNOWY,  # light snow showers
    16: ATTR_CONDITION_SNOWY,  # snow showers
    17: ATTR_CONDITION_SNOWY_RAINY,  # sleet
    18: ATTR_CONDITION_HAIL,  # hail
    19: ATTR_CONDITION_LIGHTNING_RAINY,  # thunderstorm
    20: ATTR_CONDITION_WINDY,  # storm
    21: ATTR_CONDITION_SNOWY_RAINY,  # freezing rain
    23: ATTR_CONDITION_RAINY,  # drizzle
    24: ATTR_CONDITION_SNOWY,  # heavy snow
    25: ATTR_CONDITION_SNOWY,  # heavy snow showers
    31: ATTR_CONDITION_WINDY,  # storm > 8 Bft warning
    32: ATTR_CONDITION_POURING,  # heavy rain warning
    33: ATTR_CONDITION_FOG,  # heavy fog warning
    34: ATTR_CONDITION_EXCEPTIONAL,  # extreme heat > 35 °C warning
    35: ATTR_CONDITION_EXCEPTIONAL,  # extreme cold < -20 °C warning
    36: ATTR_CONDITION_SNOWY_RAINY,  # glaze warning
    37: ATTR_CONDITION_SNOWY,  # heavy snowfall warning
    38: ATTR_CONDITION_SNOWY,  # snowdrift warning
    39: ATTR_CONDITION_WINDY,  # squalls warning
    40: ATTR_CONDITION_EXCEPTIONAL,  # hurricane / tornado > 11 Bft warning
    41: ATTR_CONDITION_RAINY,  # constant rain warning
    42: ATTR_CONDITION_EXCEPTIONAL,  # flooding warning
    43: ATTR_CONDITION_SNOWY_RAINY,  # sleet warning
    44: ATTR_CONDITION_HAIL,  # hail warning
}


def _map_condition(
    code: Any, condition_map: dict[int, str] = CONDITION_MAP
) -> str | None:
    """Map an AWEKAS condition code to a Home Assistant condition."""
    try:
        return condition_map.get(int(code))
    except TypeError, ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwekasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AWEKAS weather entity based on config entry."""
    async_add_entities([AwekasWeather(entry.runtime_data)])


class AwekasWeather(
    AwekasEntity, SingleCoordinatorWeatherEntity[AwekasDataUpdateCoordinator]
):
    """Representation of an AWEKAS weather entity."""

    _attr_name = None  # Use the device name
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def _current(self) -> dict[str, Any]:
        return self.coordinator.data.get("current") or {}

    @property
    def _forecast(self) -> dict[str, Any]:
        return self.coordinator.data.get("forecast") or {}

    @property
    def available(self) -> bool:
        """Return if the station uploaded data recently."""
        return super().available and not self.coordinator.data_is_stale

    @property
    def supported_features(self) -> WeatherEntityFeature:
        """Offer a forecast only if the station has one.

        The forecast requires an active AWEKAS Stationsweb subscription.
        """
        if self._forecast:
            return WeatherEntityFeature.FORECAST_DAILY
        return WeatherEntityFeature(0)

    @property
    def condition(self) -> str | None:
        """Return the current condition.

        Uses the weather report of the station, or today's forecast if there
        is no report.
        """
        condition = _map_condition(self._current.get("condition"), REPORT_CONDITION_MAP)
        if condition is None:
            return _map_condition((self._forecast.get("day0") or {}).get("fc_code"))
        if condition == ATTR_CONDITION_SUNNY and not is_up(self.hass):
            return ATTR_CONDITION_CLEAR_NIGHT
        return condition

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the position of the station."""
        station = (self.coordinator.station or {}).get("station") or {}
        attributes = {
            ATTR_LATITUDE: station.get("latdec"),
            ATTR_LONGITUDE: station.get("londec"),
            ATTR_ELEVATION: station.get("elevation"),
        }
        return {key: value for key, value in attributes.items() if value is not None}

    @property
    def native_temperature(self) -> float | None:
        """Return current temperature."""
        return self._current.get("temperature")

    @property
    def humidity(self) -> float | None:
        """Return current humidity."""
        return self._current.get("humidity")

    @property
    def native_pressure(self) -> float | None:
        """Return current pressure."""
        return self._current.get("airpress_rel")

    @property
    def native_wind_speed(self) -> float | None:
        """Return current wind speed."""
        return self._current.get("windspeed")

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return current wind gust speed."""
        return self._current.get("gustspeed")

    @property
    def wind_bearing(self) -> float | None:
        """Return current wind bearing."""
        return self._current.get("winddirection")

    @property
    def native_dew_point(self) -> float | None:
        """Return current dew point."""
        return self._current.get("dewpoint")

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        today = dt_util.now().date()
        forecasts: list[Forecast] = []

        for day in range(FORECAST_DAYS):
            if not (day_info := self._forecast.get(f"day{day}")):
                continue
            forecasts.append(
                Forecast(
                    datetime=dt_util.start_of_local_day(
                        today + timedelta(days=day)
                    ).isoformat(),
                    native_templow=day_info.get("fc_temp_min"),
                    native_temperature=day_info.get("fc_temp_max"),
                    native_precipitation=day_info.get("fc_rainsum"),
                    precipitation_probability=day_info.get("fc_rain_possibility"),
                    condition=_map_condition(day_info.get("fc_code")),
                )
            )

        return forecasts or None
