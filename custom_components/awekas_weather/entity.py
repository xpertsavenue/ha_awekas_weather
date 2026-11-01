"""Base entity for the AWEKAS Weather integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AwekasDataUpdateCoordinator


class AwekasEntity(CoordinatorEntity[AwekasDataUpdateCoordinator]):
    """Common base of all AWEKAS entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: AwekasDataUpdateCoordinator, key: str | None = None
    ) -> None:
        """Initialize the entity.

        Unique IDs are based on the config entry, never on the API key, so
        they stay stable when the key is replaced during re-authentication.
        """
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = (
            entry.entry_id if key is None else f"{entry.entry_id}_{key}"
        )

        station = (coordinator.station or {}).get("station") or {}
        stationsweb = (coordinator.station or {}).get("stationsweb") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=station.get("location") or entry.title,
            manufacturer="AWEKAS",
            model=station.get("hardware") or "Weather Station",
            sw_version=station.get("software") or None,
            serial_number=str(station["id"]) if "id" in station else None,
            configuration_url=(
                stationsweb.get("weblink") if stationsweb.get("enabled") else None
            )
            or station.get("weblink")
            or None,
        )


def sensor_active(
    coordinator: AwekasDataUpdateCoordinator, status_key: str | None
) -> bool | None:
    """Return if the station has the sensor, None if this is unknown.

    Uses the 'sensorstatus' section of the station API.
    """
    if status_key is None or coordinator.station is None:
        return None
    status = (coordinator.station.get("sensorstatus") or {}).get(status_key)
    if status is None:
        return None
    return bool(status)
