"""DataUpdateCoordinator for AWEKAS Weather."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LANGUAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

type AwekasConfigEntry = ConfigEntry[AwekasDataUpdateCoordinator]


class AwekasAuthError(ConfigEntryAuthFailed):
    """Fehler bei ungültigem API-Schlüssel."""

    translation_domain = DOMAIN
    translation_key = "invalid_api_key"


class AwekasDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching AWEKAS data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.api_key = entry.data[CONF_API_KEY]
        self.language = entry.data.get(CONF_LANGUAGE, "de")

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    def _validate_response(self, data: dict[str, Any]) -> None:
        """Validiert die API-Antwort auf Fehlercodes."""
        error_val = data.get("error")
        if error_val:
            error_str = str(error_val).lower().strip()
            if error_str not in ("none", "null", ""):
                if "invalid" in error_str or "key" in error_str:
                    # Löst den Re-Auth-Flow in HA aus
                    raise ConfigEntryAuthFailed("Invalid AWEKAS API key")

                raise UpdateFailed(f"AWEKAS API error: {error_val}")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from AWEKAS API."""
        session = async_get_clientsession(self.hass)
        url = (
            f"https://api.awekas.at/current.php?key={self.api_key}&lng={self.language}"
        )

        # 1. Reine Netzwerk- / HTTP-Anfrage (fängt nur aiohttp/Timeout-Fehler ab)
        try:
            async with session.get(url, timeout=10) as response:
                status = response.status
                if status == 200:
                    data = await response.json()
        except Exception as err:
            raise UpdateFailed(f"Error fetching AWEKAS data: {err}") from err

        # 2. HTTP Status Code prüfen
        if status != 200:
            raise UpdateFailed(f"HTTP error fetching AWEKAS data: {status}")

        # 3. Inhaltliche Daten-Validierung (ConfigEntryAuthFailed fliegt direkt ungehindert nach oben)
        self._validate_response(data)

        return data
