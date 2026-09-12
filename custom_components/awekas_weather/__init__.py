"""The AWEKAS Weather integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import AwekasConfigEntry, AwekasDataUpdateCoordinator

_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.WEATHER,
]


async def async_setup_entry(hass: HomeAssistant, entry: AwekasConfigEntry) -> bool:
    """Set up AWEKAS Weather from a config entry."""
    coordinator = AwekasDataUpdateCoordinator(hass, entry)

    # Ersten Datenabruf beim Start durchführen
    await coordinator.async_config_entry_first_refresh()

    # Coordinator im hass.data-Speicher ablegen
    entry.runtime_data = coordinator

    # Sensor-Plattformen laden
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AwekasConfigEntry) -> bool:
    """Unload a config entry."""
    # Bei runtime_data ist kein manuelles Entfernen aus hass.data mehr nötig!
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
