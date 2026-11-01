"""DataUpdateCoordinator for AWEKAS Weather."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone, tzinfo
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    AwekasAuthError,
    AwekasClient,
    AwekasConnectionError,
    AwekasError,
    AwekasPlusNotActiveError,
    AwekasQuotaError,
)
from .const import (
    DOMAIN,
    QUOTA_RETRY_AFTER,
    STALE_AFTER,
    STATION_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type AwekasConfigEntry = ConfigEntry[AwekasDataUpdateCoordinator]


class AwekasDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the current data every minute and the station data once a day."""

    config_entry: AwekasConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AwekasConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = AwekasClient(
            async_get_clientsession(hass),
            entry.data[CONF_API_KEY],
        )
        # Response of the station API, None until it was fetched once
        self.station: dict[str, Any] | None = None
        self.station_timezone: tzinfo | None = None
        self._station_updated: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the AWEKAS API."""
        data = await _async_call(self.client.async_get_current)
        await self._async_update_station()
        return data

    async def _async_update_station(self) -> None:
        """Fetch the station data once a day.

        The station data is optional, so errors only keep the old data.
        """
        now = dt_util.utcnow()
        if (
            self._station_updated is not None
            and now - self._station_updated < STATION_UPDATE_INTERVAL
        ):
            return
        try:
            station = await self.client.async_get_station()
        except AwekasError as err:
            _LOGGER.debug("Could not fetch the station data: %s", err)
            return

        self.station = station
        self._station_updated = now
        name = (station.get("station") or {}).get("timezone")
        self.station_timezone = (
            await dt_util.async_get_time_zone(name) if name else None
        )

    @property
    def data_timestamp(self) -> datetime | None:
        """Return when the station measured the current data."""
        timestamp = (self.data.get("current") or {}).get("datatimestamp")
        if not isinstance(timestamp, int | float):
            return None
        return dt_util.utc_from_timestamp(timestamp)

    @property
    def data_is_stale(self) -> bool:
        """Return if the station has not uploaded data for a while."""
        timestamp = self.data_timestamp
        return timestamp is not None and dt_util.utcnow() - timestamp > STALE_AFTER

    def station_time(self) -> datetime:
        """Return the time of the current data in the time zone of the station."""
        when = self.data_timestamp or dt_util.utcnow()
        if self.station_timezone is not None:
            return when.astimezone(self.station_timezone)
        offset = (self.data.get("current") or {}).get("timeoffset")
        if isinstance(offset, int):
            return when.astimezone(timezone(timedelta(seconds=offset)))
        return dt_util.as_local(when)


async def _async_call[T](request: Callable[[], Awaitable[T]]) -> T:
    """Run an API request and convert its errors for the coordinator."""
    try:
        return await request()
    except AwekasAuthError as err:
        raise ConfigEntryAuthFailed(
            f"The AWEKAS API rejected the API key: {err}",
            translation_domain=DOMAIN,
            translation_key="invalid_api_key",
            translation_placeholders={"error": str(err)},
        ) from err
    except AwekasPlusNotActiveError as err:
        raise ConfigEntryError(
            "AWEKAS plus is not activated in the AWEKAS user profile",
            translation_domain=DOMAIN,
            translation_key="awekas_plus_not_active",
        ) from err
    except AwekasQuotaError as err:
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="quota_exceeded",
            retry_after=QUOTA_RETRY_AFTER.total_seconds(),
        ) from err
    except AwekasConnectionError as err:
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err
    except AwekasError as err:
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="api_error",
            translation_placeholders={"error": str(err)},
        ) from err
