"""Tests for the AWEKAS API client."""

from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.awekas_weather.api import (
    AwekasAuthError,
    AwekasClient,
    AwekasConnectionError,
    AwekasPlusNotActiveError,
    AwekasQuotaError,
    AwekasResponseError,
)
from custom_components.awekas_weather.const import API_URL, STATION_API_URL

from .conftest import API_KEY


def _client(hass: HomeAssistant) -> AwekasClient:
    return AwekasClient(async_get_clientsession(hass), API_KEY)


async def test_get_current(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    awekas_data: dict[str, Any],
) -> None:
    """Test a successful request only sends the API key."""
    aioclient_mock.get(API_URL, json=awekas_data)

    assert await _client(hass).async_get_current() == awekas_data

    _, url, _, _ = aioclient_mock.mock_calls[0]
    assert dict(url.query) == {"key": API_KEY}


@pytest.mark.parametrize(
    ("api_key", "query_string"),
    [
        # Keys from AWEKAS are already URL encoded and must not be encoded twice
        ("ab%2Bcd%2Fef%3D%3D", "key=ab%2Bcd/ef%3D%3D"),
        ("ab+cd/ef==", "key=ab%2Bcd/ef%3D%3D"),
        (" abc123\n", "key=abc123"),
    ],
)
async def test_api_key_encoding(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    awekas_data: dict[str, Any],
    api_key: str,
    query_string: str,
) -> None:
    """Test encoded and plain API keys result in the same request."""
    aioclient_mock.get(API_URL, json=awekas_data)

    client = AwekasClient(async_get_clientsession(hass), api_key)
    await client.async_get_current()

    _, url, _, _ = aioclient_mock.mock_calls[0]
    assert url.raw_query_string == query_string


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        # The errors documented in the API specification
        ("maximum quota exceeded", AwekasQuotaError),
        ("invalid key", AwekasAuthError),
        ("AWEKAS plus not active", AwekasPlusNotActiveError),
        ("something else", AwekasResponseError),
        # Only exact messages are known errors
        ("key expired", AwekasResponseError),
    ],
)
@pytest.mark.parametrize(
    ("url", "request_name"),
    [(API_URL, "async_get_current"), (STATION_API_URL, "async_get_station")],
)
async def test_api_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    url: str,
    request_name: str,
    error: str,
    expected: type[Exception],
) -> None:
    """Test errors reported in the response body of both APIs."""
    aioclient_mock.get(url, json={"error": error})

    with pytest.raises(expected):
        await getattr(_client(hass), request_name)()


async def test_get_station(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    station_data: dict[str, Any],
) -> None:
    """Test the station request only sends the API key."""
    aioclient_mock.get(STATION_API_URL, json=station_data)

    assert await _client(hass).async_get_station() == station_data

    _, url, _, _ = aioclient_mock.mock_calls[0]
    assert dict(url.query) == {"key": API_KEY}


@pytest.mark.parametrize("error", [None, "", "none", "null"])
async def test_empty_error_field(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, error: str | None
) -> None:
    """Test empty values of the error field are no errors."""
    aioclient_mock.get(API_URL, json={"current": {}, "error": error})

    assert await _client(hass).async_get_current() == {"current": {}, "error": error}


async def test_http_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test an HTTP error status."""
    aioclient_mock.get(API_URL, status=500)

    with pytest.raises(AwekasConnectionError, match="HTTP status 500"):
        await _client(hass).async_get_current()


@pytest.mark.parametrize("exc", [TimeoutError(), aiohttp.ClientError()])
async def test_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: Exception
) -> None:
    """Test network errors do not leak the API key in the message."""
    aioclient_mock.get(API_URL, exc=exc)

    with pytest.raises(AwekasConnectionError) as err:
        await _client(hass).async_get_current()
    assert API_KEY not in str(err.value)


@pytest.mark.parametrize("text", ["no json", "[1, 2]"])
async def test_invalid_response(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, text: str
) -> None:
    """Test a response that is no JSON object."""
    aioclient_mock.get(API_URL, text=text)

    with pytest.raises(AwekasResponseError):
        await _client(hass).async_get_current()
