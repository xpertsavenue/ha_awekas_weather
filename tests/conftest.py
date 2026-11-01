"""Fixtures for AWEKAS Weather tests."""

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_API_KEY
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.awekas_weather.const import DOMAIN

API_KEY = "abcdef123456"
STATION_ID = "5"
STATION_LOCATION = "Micheldorf Test"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of custom integrations in all tests."""


@pytest.fixture
def awekas_data() -> dict[str, Any]:
    """Return a response of the AWEKAS API."""
    path = Path(__file__).parent / "fixtures" / "current.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def station_data() -> dict[str, Any]:
    """Return a response of the AWEKAS station API."""
    path = Path(__file__).parent / "fixtures" / "station.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def mock_awekas_client(
    awekas_data: dict[str, Any], station_data: dict[str, Any]
) -> Generator[AsyncMock]:
    """Mock the AWEKAS API client used by the coordinator and config flow."""
    with (
        patch(
            "custom_components.awekas_weather.coordinator.AwekasClient",
            autospec=True,
        ) as client_cls,
        patch("custom_components.awekas_weather.config_flow.AwekasClient", client_cls),
    ):
        client = client_cls.return_value
        client.async_get_current.return_value = awekas_data
        client.async_get_station.return_value = station_data
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip setting up the integration after a config flow."""
    with patch(
        "custom_components.awekas_weather.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=STATION_LOCATION,
        unique_id=STATION_ID,
        data={CONF_API_KEY: API_KEY},
        version=1,
        minor_version=3,
    )
