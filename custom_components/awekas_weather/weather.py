"""Weather platform for AWEKAS Integration."""

from datetime import timedelta
import logging

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

# Mapping von AWEKAS fc_code / Text zu Home Assistant Wetter-Zuständen
CONDITION_MAP = {
    1000: "sunny",
    1003: "partlycloudy",
    1006: "cloudy",
    1009: "cloudy",
    1063: "rainy",
    1183: "rainy",
    1189: "rainy",
    1195: "pouring",
    1273: "lightning-rainy",
}


def _map_condition(fc_code: int | None, fc_text: str | None) -> str | None:
    """Mappt den AWEKAS Wetter-Code auf Home Assistant Standard-Zustände."""
    if fc_code in CONDITION_MAP:
        return CONDITION_MAP[fc_code]

    if fc_text:
        text = fc_text.lower()
        if "regen" in text:
            return "rainy"
        if "sonnig" in text or "heiter" in text:
            return "sunny"
        if "bedeckt" in text or "bewölkt" in text:
            return "cloudy"

    return "cloudy"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwekasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AWEKAS weather entity based on config entry."""
    coordinator = entry.runtime_data
    async_add_entities([AwekasWeather(coordinator)])


class AwekasWeather(CoordinatorEntity[AwekasDataUpdateCoordinator], WeatherEntity):
    """Representation of an AWEKAS Weather entity."""

    _attr_has_entity_name = True
    _attr_name = None  # Verwendet den Namen des Geräts als Hauptnamen
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    def __init__(self, coordinator: AwekasDataUpdateCoordinator) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.api_key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api_key)},
            name=f"AWEKAS ({coordinator.api_key[:5]})",
            manufacturer="AWEKAS",
            model="Weather Station",
        )

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        if not self.coordinator.data:
            return None

        # Falls Vorhersage für Tag 0 da ist, als aktuellen Zustand nutzen
        day0 = self.coordinator.data.get("forecast", {}).get("day0", {})
        return _map_condition(day0.get("fc_code"), day0.get("fc_text"))

    @property
    def native_temperature(self) -> float | None:
        """Return current temperature."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("current", {}).get("temperature")

    @property
    def humidity(self) -> float | None:
        """Return current humidity."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("current", {}).get("humidity")

    @property
    def native_pressure(self) -> float | None:
        """Return current pressure."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("current", {}).get("airpress_rel")

    @property
    def native_wind_speed(self) -> float | None:
        """Return current wind speed."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("current", {}).get("windspeed")

    @property
    def wind_bearing(self) -> float | None:
        """Return current wind bearing."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("current", {}).get("winddirection")

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast in modern Home Assistant format."""
        if not self.coordinator.data or "forecast" not in self.coordinator.data:
            return None

        forecast_data = self.coordinator.data["forecast"]
        daily_forecast: list[Forecast] = []

        # Heutiges Datum als Startpunkt
        now = dt_util.utcnow()

        for i in range(6):
            day_key = f"day{i}"
            if day_key not in forecast_data:
                continue

            day_info = forecast_data[day_key]
            if not day_info:
                continue

            # Datum für Tag 0, Tag 1, Tag 2... berechnen
            forecast_date = (now + timedelta(days=i)).isoformat()

            forecast_item: Forecast = {
                "datetime": forecast_date,
                "native_templow": day_info.get("fc_temp_min"),
                "native_temperature": day_info.get("fc_temp_max"),
                "native_precipitation": day_info.get("fc_rainsum"),
                "precipitation_probability": day_info.get("fc_rain_possibility"),
                "condition": _map_condition(
                    day_info.get("fc_code"), day_info.get("fc_text")
                ),
            }
            daily_forecast.append(forecast_item)

        return daily_forecast
