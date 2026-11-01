"""Binary sensor platform for AWEKAS Weather integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator
from .entity import AwekasEntity, sensor_active

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AwekasBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an AWEKAS binary sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    # Key in the 'sensorstatus' section of the station API
    status_key: str | None = None


BINARY_SENSOR_TYPES: tuple[AwekasBinarySensorEntityDescription, ...] = (
    AwekasBinarySensorEntityDescription(
        key="itsraining",
        translation_key="itsraining",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda data: (data.get("current") or {}).get("itsraining"),
        status_key="precipitation",
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


class AwekasBinarySensor(AwekasEntity, BinarySensorEntity):
    """Representation of an AWEKAS binary sensor."""

    entity_description: AwekasBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: AwekasDataUpdateCoordinator,
        description: AwekasBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        # Sensors the station does not have are created disabled. Without
        # the sensor status of the station API, a missing value decides.
        active = sensor_active(coordinator, description.status_key)
        if active is False or (
            active is None and description.value_fn(coordinator.data) is None
        ):
            self._attr_entity_registry_enabled_default = False

    @property
    def available(self) -> bool:
        """Return if the station currently reports this value."""
        return (
            super().available
            and not self.coordinator.data_is_stale
            and self.entity_description.value_fn(self.coordinator.data) is not None
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        value = self.entity_description.value_fn(self.coordinator.data)
        return None if value is None else bool(value)
