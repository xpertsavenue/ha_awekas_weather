"""Client for the AWEKAS station API (version 2.1)."""

from typing import Any
from urllib.parse import unquote

import aiohttp

from .const import API_URL, REQUEST_TIMEOUT, STATION_API_URL


class AwekasError(Exception):
    """Base class for AWEKAS API errors."""


class AwekasConnectionError(AwekasError):
    """The API could not be reached or answered with an HTTP error."""


class AwekasAuthError(AwekasError):
    """The API key was rejected."""


class AwekasQuotaError(AwekasError):
    """The request quota of the API key is exhausted."""


class AwekasPlusNotActiveError(AwekasError):
    """AWEKAS plus is not activated in the user profile."""


class AwekasResponseError(AwekasError):
    """The API reported an unknown error or returned an unexpected payload."""


# The 'error' values documented in the API specification
_API_ERRORS: dict[str, type[AwekasError]] = {
    "invalid key": AwekasAuthError,
    "maximum quota exceeded": AwekasQuotaError,
    "awekas plus not active": AwekasPlusNotActiveError,
}


class AwekasClient:
    """Fetch the data of an AWEKAS station."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        # AWEKAS hands out keys that are already URL encoded (e.g. "%2B").
        # Decode them once, aiohttp encodes the query parameters again.
        self._api_key = unquote(api_key.strip())

    async def async_get_current(self) -> dict[str, Any]:
        """Return the current values, daily statistics and forecast."""
        return await self._async_request(API_URL, {"key": self._api_key})

    async def async_get_station(self) -> dict[str, Any]:
        """Return the station data, Stationsweb status and sensor status."""
        return await self._async_request(STATION_API_URL, {"key": self._api_key})

    async def _async_request(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status != 200:
                    raise AwekasConnectionError(f"HTTP status {response.status}")
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            # Only pass on the error type: aiohttp messages can contain the
            # request URL and with it the API key.
            raise AwekasConnectionError(type(err).__name__) from err
        except ValueError as err:
            raise AwekasResponseError("Response is not valid JSON") from err

        if not isinstance(data, dict):
            raise AwekasResponseError("Unexpected response format")

        _raise_for_api_error(data.get("error"))
        return data


def _raise_for_api_error(error: Any) -> None:
    """Raise the matching exception for the 'error' field of a response."""
    if not error:
        return

    message = str(error).strip()
    if message.lower() in ("", "none", "null"):
        return

    raise _API_ERRORS.get(message.lower(), AwekasResponseError)(message)
