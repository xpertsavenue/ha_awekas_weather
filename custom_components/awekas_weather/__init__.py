"""The AWEKAS Weather integration."""

import logging
from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_API_KEY, CONF_LANGUAGE, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    service,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import DEFAULT_TITLE, DOMAIN
from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator
from .sensor import AwekasPrecipitationTotalSensor

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.WEATHER,
]


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SET_PRECIPITATION_TOTAL = "set_precipitation_total"
ATTR_VALUE = "value"

SET_PRECIPITATION_TOTAL_SCHEMA = {
    vol.Required(ATTR_VALUE): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
}


async def _async_set_precipitation_total(entity: Entity, call: ServiceCall) -> None:
    """Set the month or year precipitation total of a sensor."""
    if not isinstance(entity, AwekasPrecipitationTotalSensor):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_a_precipitation_total",
            translation_placeholders={"entity_id": entity.entity_id},
        )
    entity.async_set_total(call.data[ATTR_VALUE])


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the actions of the integration."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SET_PRECIPITATION_TOTAL,
        entity_domain=SENSOR_DOMAIN,
        schema=SET_PRECIPITATION_TOTAL_SCHEMA,
        func=_async_set_precipitation_total,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AwekasConfigEntry) -> bool:
    """Set up AWEKAS Weather from a config entry."""
    coordinator = AwekasDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _async_update_entry_from_station(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    return True


@callback
def _async_update_entry_from_station(
    hass: HomeAssistant,
    entry: AwekasConfigEntry,
    coordinator: AwekasDataUpdateCoordinator,
) -> None:
    """Use the station ID as unique ID and the location as default title.

    Entries created before the station API was used are identified by the
    API key and named after it.
    """
    station = (coordinator.station or {}).get("station") or {}
    if (station_id := station.get("id")) is None:
        return

    updates: dict[str, Any] = {}
    unique_id = str(station_id)
    if entry.unique_id != unique_id and not any(
        other.unique_id == unique_id
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ):
        updates["unique_id"] = unique_id
    if (location := station.get("location")) and (
        entry.title == DEFAULT_TITLE or entry.title.startswith("AWEKAS (")
    ):
        updates["title"] = location
    if updates:
        hass.config_entries.async_update_entry(entry, **updates)


async def async_unload_entry(hass: HomeAssistant, entry: AwekasConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: AwekasConfigEntry) -> bool:
    """Migrate an old config entry."""
    if entry.version > 1:
        # Downgrade from a future version
        return False

    if entry.minor_version < 2:
        # 1.1 -> 1.2: the device and the weather and binary sensor entities
        # used the API key as identifier, now the config entry ID is used.
        api_key: str = entry.data[CONF_API_KEY]

        @callback
        def _migrate_unique_id(
            entity_entry: er.RegistryEntry,
        ) -> dict[str, Any] | None:
            if entity_entry.unique_id == api_key:
                return {"new_unique_id": entry.entry_id}
            if entity_entry.unique_id.startswith(f"{api_key}_"):
                suffix = entity_entry.unique_id.removeprefix(api_key)
                return {"new_unique_id": f"{entry.entry_id}{suffix}"}
            return None

        await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)

        device_registry = dr.async_get(hass)
        if device := device_registry.async_get_device(identifiers={(DOMAIN, api_key)}):
            device_registry.async_update_device(
                device.id, new_identifiers={(DOMAIN, entry.entry_id)}
            )

        hass.config_entries.async_update_entry(entry, minor_version=2)
        _LOGGER.debug("Migrated config entry to version 1.2")

    if entry.minor_version < 3:
        # 1.2 -> 1.3: the language of the forecast texts is not used anymore
        hass.config_entries.async_update_entry(
            entry,
            data={k: v for k, v in entry.data.items() if k != CONF_LANGUAGE},
            minor_version=3,
        )
        _LOGGER.debug("Migrated config entry to version 1.3")

    return True
