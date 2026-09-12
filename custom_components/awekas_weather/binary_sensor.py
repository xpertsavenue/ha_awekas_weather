"""Binary sensor platform for AWEKAS Weather integration."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AwekasBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Klasse zur Beschreibung von AWEKAS Binary Sensoren."""

    value_fn: Callable[[dict], bool | None]


# Definition aller Binary-Sensoren
BINARY_SENSOR_TYPES: tuple[AwekasBinarySensorEntityDescription, ...] = (
    AwekasBinarySensorEntityDescription(
        key="itsraining",
        translation_key="itsraining",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda data: data.get("current", {}).get("itsraining"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AwekasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AWEKAS binary sensors based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        AwekasBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_TYPES
    )


class AwekasBinarySensor(
    CoordinatorEntity[AwekasDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of an AWEKAS Binary Sensor."""

    entity_description: AwekasBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AwekasDataUpdateCoordinator,
        description: AwekasBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description

        # Eindeutige ID pro Entität (z. B. api_key_itsraining)
        self._attr_unique_id = f"{coordinator.api_key}_{description.key}"

        # Gruppierung aller Entitäten unter einem gemeinsamen Gerät
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api_key)},
            name=f"AWEKAS ({coordinator.api_key[:5]})",
            manufacturer="AWEKAS",
            model="Weather Station",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
