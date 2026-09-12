"""Sensor platform for AWEKAS Weather integration."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import timedelta
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    RestoreSensor,
)
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.components.utility_meter.const import DAILY, MONTHLY, YEARLY
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

try:
    from homeassistant.const import UnitOfDensity

    PM_UNIT = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
except ImportError:
    try:
        from homeassistant.const import UnitOfConcentrationMass

        PM_UNIT = UnitOfConcentrationMass.MICROGRAMS_PER_CUBIC_METER
    except ImportError:
        # Sehr alte HA-Versionen
        PM_UNIT = "μg/m³"


@dataclass(frozen=True, kw_only=True)
class AwekasSensorEntityDescription(SensorEntityDescription):
    """Klasse zur Beschreibung von AWEKAS Sensoren."""

    value_fn: Callable[[dict], float | int | str | None]


# Definition aller regulären Sensoren aus 'current', '1h' und 'day'
SENSOR_TYPES: tuple[AwekasSensorEntityDescription, ...] = (
    # --- Temp / Taupunkt ---
    AwekasSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("temperature"),
    ),
    AwekasSensorEntityDescription(
        key="dewpoint",
        translation_key="dewpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("dewpoint"),
    ),
    AwekasSensorEntityDescription(
        key="windchill",
        translation_key="windchill",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("windchill"),
    ),
    AwekasSensorEntityDescription(
        key="wetbulbtemperature",
        translation_key="wetbulbtemperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("wetbulbtemperature"),
    ),
    AwekasSensorEntityDescription(
        key="indoortemperature",
        translation_key="indoortemperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("indoortemperature"),
    ),
    # --- Luftfeuchtigkeit ---
    AwekasSensorEntityDescription(
        key="humidity",
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("humidity"),
    ),
    AwekasSensorEntityDescription(
        key="indoorhumidity",
        translation_key="indoorhumidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("indoorhumidity"),
    ),
    # --- Luftdruck ---
    AwekasSensorEntityDescription(
        key="airpress_rel",
        translation_key="airpress_rel",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("airpress_rel"),
    ),
    AwekasSensorEntityDescription(
        key="tendency",
        translation_key="tendency",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("tendency"),
    ),
    # --- Niederschlag ---
    AwekasSensorEntityDescription(
        key="precipitation",
        translation_key="precipitation",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("current", {}).get("precipitation"),
    ),
    AwekasSensorEntityDescription(
        key="rainrate",
        translation_key="rainrate",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("rainrate"),
    ),
    AwekasSensorEntityDescription(
        key="precipitation_1h",
        translation_key="precipitation_1h",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("1h", {}).get("precipitation_1h"),
    ),
    # --- Wind ---
    AwekasSensorEntityDescription(
        key="windspeed",
        translation_key="windspeed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("windspeed"),
    ),
    AwekasSensorEntityDescription(
        key="gustspeed",
        translation_key="gustspeed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("gustspeed"),
    ),
    AwekasSensorEntityDescription(
        key="winddirection",
        translation_key="winddirection",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("winddirection"),
    ),
    # --- Sonne & Strahlung ---
    AwekasSensorEntityDescription(
        key="uv",
        translation_key="uv",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("uv"),
    ),
    AwekasSensorEntityDescription(
        key="solar",
        translation_key="solar",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("solar"),
    ),
    AwekasSensorEntityDescription(
        key="brightness",
        translation_key="brightness",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("brightness"),
    ),
    AwekasSensorEntityDescription(
        key="suntime",
        translation_key="suntime",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("suntime"),
    ),
    # --- Schnee & Zusatzkanäle (Optional) ---
    AwekasSensorEntityDescription(
        key="snowheight",
        translation_key="snowheight",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("snowheight"),
    ),
    AwekasSensorEntityDescription(
        key="temp1",
        translation_key="temp1",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("temp1"),
    ),
    AwekasSensorEntityDescription(
        key="temp2",
        translation_key="temp2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("temp2"),
    ),
    AwekasSensorEntityDescription(
        key="temp3",
        translation_key="temp3",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("temp3"),
    ),
    AwekasSensorEntityDescription(
        key="temp4",
        translation_key="temp4",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("temp4"),
    ),
    AwekasSensorEntityDescription(
        key="humidity1",
        translation_key="humidity1",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("humidity1"),
    ),
    AwekasSensorEntityDescription(
        key="humidity2",
        translation_key="humidity2",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("humidity2"),
    ),
    AwekasSensorEntityDescription(
        key="humidity3",
        translation_key="humidity3",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("humidity3"),
    ),
    AwekasSensorEntityDescription(
        key="humidity4",
        translation_key="humidity4",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("humidity4"),
    ),
    AwekasSensorEntityDescription(
        key="soilmoisture1",
        translation_key="soilmoisture1",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("soilmoisture1"),
    ),
    AwekasSensorEntityDescription(
        key="soilmoisture2",
        translation_key="soilmoisture2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("soilmoisture2"),
    ),
    AwekasSensorEntityDescription(
        key="soilmoisture3",
        translation_key="soilmoisture3",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("soilmoisture3"),
    ),
    AwekasSensorEntityDescription(
        key="soilmoisture4",
        translation_key="soilmoisture4",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("soilmoisture4"),
    ),
    AwekasSensorEntityDescription(
        key="leafwetness1",
        translation_key="leafwetness1",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("leafwetness1"),
    ),
    AwekasSensorEntityDescription(
        key="leafwetness2",
        translation_key="leafwetness2",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("leafwetness2"),
    ),
    # --- Luftqualität ---
    AwekasSensorEntityDescription(
        key="airquality_pm1",
        translation_key="airquality_pm1",
        native_unit_of_measurement=PM_UNIT,
        device_class=SensorDeviceClass.PM1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("airquality_pm1"),
    ),
    AwekasSensorEntityDescription(
        key="airquality_pm2",
        translation_key="airquality_pm2",
        native_unit_of_measurement=PM_UNIT,
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("airquality_pm2"),
    ),
    AwekasSensorEntityDescription(
        key="airquality_pm10",
        translation_key="airquality_pm10",
        native_unit_of_measurement=PM_UNIT,
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("current", {}).get("airquality_pm10"),
    ),
    # =========================================================================
    # --- Tagesstatistiken (Day Stats) - Standardmäßig DEAKTIVIERT ---
    # =========================================================================
    # --- Temperatur Tag ---
    AwekasSensorEntityDescription(
        key="day_temp_min",
        translation_key="day_temp_min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("temp_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_temp_max",
        translation_key="day_temp_max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("temp_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_intemp_min",
        translation_key="day_intemp_min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("intemp_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_intemp_max",
        translation_key="day_intemp_max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("intemp_max"),
    ),
    # --- Taupunkt Tag ---
    AwekasSensorEntityDescription(
        key="day_dewpoint_min",
        translation_key="day_dewpoint_min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("dewpoint_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_dewpoint_max",
        translation_key="day_dewpoint_max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("dewpoint_max"),
    ),
    # --- Luftfeuchtigkeit Tag ---
    AwekasSensorEntityDescription(
        key="day_hum_min",
        translation_key="day_hum_min",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("hum_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_hum_max",
        translation_key="day_hum_max",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("hum_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_inhum_min",
        translation_key="day_inhum_min",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("inhum_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_inhum_max",
        translation_key="day_inhum_max",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("inhum_max"),
    ),
    # --- Luftdruck Tag ---
    AwekasSensorEntityDescription(
        key="day_airp_rel_min",
        translation_key="day_airp_rel_min",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("airp_rel_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_airp_rel_max",
        translation_key="day_airp_rel_max",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("airp_rel_max"),
    ),
    # --- Wind & Böen Tag ---
    AwekasSensorEntityDescription(
        key="day_windspeed_min",
        translation_key="day_windspeed_min",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("windspeed_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_windspeed_max",
        translation_key="day_windspeed_max",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("windspeed_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_winddir_max",
        translation_key="day_winddir_max",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("winddir_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_gustspeed_min",
        translation_key="day_gustspeed_min",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("gustspeed_min"),
    ),
    AwekasSensorEntityDescription(
        key="day_gustspeed_max",
        translation_key="day_gustspeed_max",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("gustspeed_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_gustdir_max",
        translation_key="day_gustdir_max",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("gustdir_max"),
    ),
    # --- Niederschlag Tag ---
    AwekasSensorEntityDescription(
        key="day_rainrate_max",
        translation_key="day_rainrate_max",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("day", {}).get("rainrate_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_precipitation_24h",
        translation_key="day_precipitation_24h",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("day", {}).get("precipitation_24h"),
    ),
    # --- Sonne / UV Tag ---
    AwekasSensorEntityDescription(
        key="day_solar_max",
        translation_key="day_solar_max",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("solar_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_uv_max",
        translation_key="day_uv_max",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("uv_max"),
    ),
    AwekasSensorEntityDescription(
        key="day_brightness_max",
        translation_key="day_brightness_max",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.get("day", {}).get("brightness_max"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwekasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AWEKAS sensors based on a config entry."""
    coordinator: AwekasDataUpdateCoordinator = entry.runtime_data

    if not coordinator.data:
        return

    entities: list[AwekasSensor] = []
    precipitation_sensor_instance: AwekasSensor | None = None

    # 1. Nur Entitäten anlegen, deren Wert nicht None ist
    for description in SENSOR_TYPES:
        if description.value_fn(coordinator.data) is not None:
            sensor = AwekasSensor(coordinator, description)
            entities.append(sensor)

            # Objekt-Referenz für den Regensensor merken
            if description.key == "precipitation":
                precipitation_sensor_instance = sensor

    # 2. Registry von nicht mehr aktiven Sensoren bereinigen
    ent_reg = er.async_get(hass)
    active_keys = {
        description.key
        for description in SENSOR_TYPES
        if description.value_fn(coordinator.data) is not None
    }

    registered_entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    for reg_entity in registered_entities:
        unique_id_suffix = reg_entity.unique_id.removeprefix(f"{entry.entry_id}_")
        if (
            reg_entity.domain == "sensor"
            and not unique_id_suffix.endswith(("_monthly", "_yearly"))
            and unique_id_suffix not in active_keys
        ):
            ent_reg.async_remove(reg_entity.entity_id)

    # 3. Basissensoren in Home Assistant registrieren
    # WICHTIG: Erst JETZT weist HA den Objekten in 'entities' ihre echte entity_id zu!
    async_add_entities(entities)

    # 4. Utility Meter anlegen, falls der Regensensor aktiv ist
    if precipitation_sensor_instance is not None:
        # Die entity_id wurde von HA beim async_add_entities automatisch am Objekt gesetzt:
        real_entity_id = precipitation_sensor_instance.entity_id

        # Fallback über die Registry, falls HA die entity_id im Objekt noch nicht geschrieben hat
        if not real_entity_id:
            precip_unique_id = f"{entry.entry_id}_precipitation"
            real_entity_id = (
                ent_reg.async_get_entity_id("sensor", DOMAIN, precip_unique_id)
                or f"sensor.{DOMAIN}_precipitation"
            )

        utility_meters = [
            AwekasUtilityMeterSensor(
                coordinator=coordinator,
                meter_type=MONTHLY,
                meter_key="precipitation_monthly",
                name="Niederschlag (Monat)",
                source_entity_id=precipitation_sensor_instance.entity_id,
            ),
            AwekasUtilityMeterSensor(
                coordinator=coordinator,
                meter_type=YEARLY,
                meter_key="precipitation_yearly",
                name="Niederschlag (Jahr)",
                source_entity_id=precipitation_sensor_instance.entity_id,
            ),
        ]

        # Füge die Utility Meter als separaten Schritt hinzu
        async_add_entities(utility_meters)


class AwekasSensor(CoordinatorEntity[AwekasDataUpdateCoordinator], SensorEntity):
    """Representation of an AWEKAS Sensor."""

    entity_description: AwekasSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AwekasDataUpdateCoordinator,
        description: AwekasSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api_key)},
            name=f"AWEKAS ({coordinator.api_key[:5]})",
            manufacturer="AWEKAS",
            model="Weather Station",
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class AwekasAccumulatedSensor(RestoreSensor, SensorEntity):
    """Accumulated Awekas precipitation sensor using native RestoreSensor and LTS support."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_native_unit_of_measurement = "mm"

    def __init__(
        self,
        coordinator,
        sensor_key: str,
        name: str,
        source_entity_id: str,
        reset_period: str,
    ) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._source_entity_id = source_entity_id
        self._reset_period = reset_period

        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{sensor_key}"
        self._attr_native_value = Decimal("0")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api_key)},
            name=f"AWEKAS ({coordinator.api_key[:5]})",
            manufacturer="AWEKAS",
            model="Weather Station",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to Home Assistant."""
        await super().async_added_to_hass()

        # Hier wird der native Sensor-Wert (inkl. Typ und Einheit) aus dem Recorder geholt
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_sensor_data.native_value
            self._attr_native_unit_of_measurement = (
                last_sensor_data.native_unit_of_measurement
            )
        elif (last_state := await self.async_get_last_state()) is not None:
            # Fallback falls keine Sensordaten vorliegen
            try:
                self._attr_native_value = float(last_state.state)
            except ValueError:
                self._attr_native_value = None

        # Event-Listener für den Quell-Sensor registrieren
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source_entity_id], self._async_source_changed
            )
        )

    async def _async_source_changed(self, event) -> None:
        """Handle source updates and accumulate precipitation."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or new_state.state in (None, "unknown", "unavailable"):
            return

        try:
            current_source_val = Decimal(new_state.state)
        except InvalidOperation, TypeError:
            return

        old_source_val = Decimal("0")
        if old_state is not None and old_state.state not in (
            None,
            "unknown",
            "unavailable",
        ):
            try:
                old_source_val = Decimal(old_state.state)
            except InvalidOperation, TypeError:
                pass

        if current_source_val < old_source_val:
            delta = current_source_val
        else:
            delta = current_source_val - old_source_val

        if delta > 0:
            if self._attr_native_value is None:
                self._attr_native_value = Decimal("0")

            self._attr_native_value += delta
            self.async_write_ha_state()


class AwekasUtilityMeterSensor(UtilityMeterSensor):
    """Representation of an AWEKAS Utility Meter Sensor."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "mm"
    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: AwekasDataUpdateCoordinator,
        meter_type: str,
        meter_key: str,
        name: str,
        source_entity_id: str,
    ) -> None:
        """Initialize the utility meter sensor."""
        # WICHTIG: Die Mutterklasse erwartet exakt self._sensor_source_id
        self._sensor_source_id = source_entity_id

        super().__init__(
            cron_pattern=None,
            delta_values=False,
            meter_offset=timedelta(seconds=0),
            meter_type=meter_type,
            name=name,
            net_consumption=False,
            parent_meter=None,
            periodically_resetting=True,
            sensor_always_available=False,
            source_entity=source_entity_id,
            tariff=None,
            tariff_entity=None,
            unique_id=f"{coordinator.config_entry.entry_id}_{meter_key}",
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api_key)},
            name=f"AWEKAS ({coordinator.api_key[:5]})",
            manufacturer="AWEKAS",
            model="Weather Station",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to Home Assistant."""
        await super().async_added_to_hass()

        # Prüfen, ob nach dem Wiederherstellen (Restore) ein gültiger Wert vorliegt.
        # Falls nicht oder falls der Zustand 'unavailable'/'unknown'/None ist, auf 0 setzen.
        if self._attr_native_value is None:
            self._attr_native_value = Decimal(0)
        else:
            try:
                self._attr_native_value = Decimal(str(self._attr_native_value))
            except InvalidOperation, TypeError:
                self._attr_native_value = Decimal(0)

        # Optional: Prüfen, ob der Status in der State Machine ebenfalls ungültig ist
        if self.state in (None, "unknown", "unavailable"):
            self._attr_native_value = Decimal(0)
            self.async_write_ha_state()
