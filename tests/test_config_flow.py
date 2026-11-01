"""Tests for the AWEKAS Weather config flow."""

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.awekas_weather.api import (
    AwekasAuthError,
    AwekasConnectionError,
    AwekasPlusNotActiveError,
    AwekasQuotaError,
    AwekasResponseError,
)
from custom_components.awekas_weather.const import DOMAIN

from .conftest import API_KEY, STATION_ID, STATION_LOCATION

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_user_flow(hass: HomeAssistant, mock_awekas_client: AsyncMock) -> None:
    """Test the full user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == STATION_LOCATION
    assert result["data"] == {CONF_API_KEY: API_KEY}
    assert result["result"].unique_id == STATION_ID
    assert result["result"].minor_version == 3


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (AwekasAuthError("invalid key"), "invalid_auth"),
        (AwekasQuotaError("maximum quota exceeded"), "quota_exceeded"),
        (
            AwekasPlusNotActiveError("AWEKAS plus not active"),
            "awekas_plus_not_active",
        ),
        (AwekasConnectionError("TimeoutError"), "cannot_connect"),
        (AwekasResponseError("strange"), "cannot_connect"),
        (RuntimeError, "unknown"),
    ],
)
@pytest.mark.parametrize("request_name", ["async_get_current", "async_get_station"])
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    request_name: str,
    side_effect: Exception,
    error: str,
) -> None:
    """Test errors of both API requests and that the flow can recover."""
    getattr(mock_awekas_client, request_name).side_effect = side_effect
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    getattr(mock_awekas_client, request_name).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_station_without_id(
    hass: HomeAssistant, mock_awekas_client: AsyncMock, station_data: dict[str, Any]
) -> None:
    """Test a station response without station ID."""
    mock_awekas_client.async_get_station.return_value = {
        **station_data,
        "station": {},
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_same_api_key(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an API key can only be configured once."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_awekas_client.async_get_current.assert_not_called()


async def test_user_flow_same_station(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a station can only be configured once, even with another key."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "another_key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test re-authentication with a new API key."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    mock_awekas_client.async_get_current.side_effect = AwekasAuthError("invalid key")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_awekas_client.async_get_current.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new_key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data == {CONF_API_KEY: "new_key"}
    assert mock_config_entry.unique_id == STATION_ID


async def test_reauth_flow_entry_identified_by_api_key(
    hass: HomeAssistant, mock_awekas_client: AsyncMock
) -> None:
    """Test re-authentication of an entry created before the station API."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=API_KEY,
        data={CONF_API_KEY: API_KEY},
        minor_version=3,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new_key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == STATION_ID


async def test_reauth_flow_wrong_station(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    station_data: dict[str, Any],
) -> None:
    """Test re-authentication with the API key of another station is refused."""
    mock_config_entry.add_to_hass(hass)
    mock_awekas_client.async_get_station.return_value = {
        **station_data,
        "station": {**station_data["station"], "id": 6},
    }

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "other_key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_station"
    assert mock_config_entry.data[CONF_API_KEY] == API_KEY


async def test_reauth_flow_station_of_other_entry(
    hass: HomeAssistant, mock_awekas_client: AsyncMock
) -> None:
    """Test re-authentication must not take over the station of another entry."""
    MockConfigEntry(
        domain=DOMAIN, unique_id=STATION_ID, data={CONF_API_KEY: "other_key"}
    ).add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=API_KEY,
        data={CONF_API_KEY: API_KEY},
        minor_version=3,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new_key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_API_KEY] == API_KEY
