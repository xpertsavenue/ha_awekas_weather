"""Tests for setting up the AWEKAS Weather integration."""

from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_LANGUAGE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.awekas_weather.api import (
    AwekasAuthError,
    AwekasConnectionError,
    AwekasPlusNotActiveError,
    AwekasQuotaError,
)
from custom_components.awekas_weather.const import (
    DEFAULT_TITLE,
    DOMAIN,
    QUOTA_RETRY_AFTER,
    STATION_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
)

from . import get_entity_id, setup_integration
from .conftest import API_KEY, STATION_ID, STATION_LOCATION


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setting up and unloading a config entry."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("side_effect", "state"),
    [
        (AwekasConnectionError("TimeoutError"), ConfigEntryState.SETUP_RETRY),
        (AwekasQuotaError("maximum quota exceeded"), ConfigEntryState.SETUP_RETRY),
        (AwekasAuthError("invalid key"), ConfigEntryState.SETUP_ERROR),
        (
            AwekasPlusNotActiveError("AWEKAS plus not active"),
            ConfigEntryState.SETUP_ERROR,
        ),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    side_effect: Exception,
    state: ConfigEntryState,
) -> None:
    """Test errors during the first refresh."""
    mock_awekas_client.async_get_current.side_effect = side_effect
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is state


async def test_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a rejected API key starts the re-authentication flow."""
    mock_awekas_client.async_get_current.side_effect = AwekasAuthError("invalid key")
    await setup_integration(hass, mock_config_entry)

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH


async def test_update_interval_and_quota_pause(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test polling every minute and pausing after an exceeded quota."""
    await setup_integration(hass, mock_config_entry)
    assert mock_awekas_client.async_get_current.call_count == 1

    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_awekas_client.async_get_current.call_count == 2

    mock_awekas_client.async_get_current.side_effect = AwekasQuotaError("quota")
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_awekas_client.async_get_current.call_count == 3
    temperature = get_entity_id(hass, mock_config_entry, "sensor", "temperature")
    assert hass.states.get(temperature).state == STATE_UNAVAILABLE

    # No requests during the pause
    freezer.tick(QUOTA_RETRY_AFTER - timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_awekas_client.async_get_current.call_count == 3

    mock_awekas_client.async_get_current.side_effect = None
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_awekas_client.async_get_current.call_count == 4
    assert hass.states.get(temperature).state == "14.5"


async def test_migrate_api_key_identifiers(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test migrating identifiers based on the API key to the entry ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=API_KEY,
        data={CONF_API_KEY: API_KEY, CONF_LANGUAGE: "de"},
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, API_KEY)}
    )
    weather = entity_registry.async_get_or_create(
        "weather", DOMAIN, API_KEY, config_entry=entry, device_id=device.id
    )
    raining = entity_registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{API_KEY}_itsraining",
        config_entry=entry,
        device_id=device.id,
    )
    temperature = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_temperature",
        config_entry=entry,
        device_id=device.id,
    )

    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 3
    assert entry.data == {CONF_API_KEY: API_KEY}
    assert entity_registry.async_get(weather.entity_id).unique_id == entry.entry_id
    assert (
        entity_registry.async_get(raining.entity_id).unique_id
        == f"{entry.entry_id}_itsraining"
    )
    assert (
        entity_registry.async_get(temperature.entity_id).unique_id
        == f"{entry.entry_id}_temperature"
    )
    assert device_registry.async_get(device.id).identifiers == {
        (DOMAIN, entry.entry_id)
    }
    # No second device was created
    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 1


async def test_reauth_keeps_identifiers(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a new API key does not create new devices or entities."""
    await setup_integration(hass, mock_config_entry)
    entities_before = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    }

    result = await mock_config_entry.start_reauth_flow(hass)
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new_key"}
    )
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    entities_after = {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    }
    assert entities_after == entities_before
    assert (
        len(
            dr.async_entries_for_config_entry(
                device_registry, mock_config_entry.entry_id
            )
        )
        == 1
    )


@pytest.mark.parametrize("title", [DEFAULT_TITLE, "AWEKAS (abcde)"])
async def test_entry_updated_from_station(
    hass: HomeAssistant, mock_awekas_client: AsyncMock, title: str
) -> None:
    """Test entries identified by the API key get station ID and location."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=API_KEY,
        data={CONF_API_KEY: API_KEY},
        minor_version=3,
    )
    await setup_integration(hass, entry)

    assert entry.unique_id == STATION_ID
    assert entry.title == STATION_LOCATION


async def test_entry_custom_title_kept(
    hass: HomeAssistant, mock_awekas_client: AsyncMock
) -> None:
    """Test a title set by the user is not replaced."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Garden",
        unique_id=API_KEY,
        data={CONF_API_KEY: API_KEY},
        minor_version=3,
    )
    await setup_integration(hass, entry)

    assert entry.unique_id == STATION_ID
    assert entry.title == "Garden"


async def test_entry_unique_id_of_other_entry(
    hass: HomeAssistant, mock_awekas_client: AsyncMock
) -> None:
    """Test the station ID is not used twice."""
    MockConfigEntry(domain=DOMAIN, unique_id=STATION_ID).add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=API_KEY,
        data={CONF_API_KEY: API_KEY},
        minor_version=3,
    )
    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == API_KEY


async def test_device_info(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the device is described by the station data."""
    await setup_integration(hass, mock_config_entry)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.entry_id)}
    )
    assert device.name == STATION_LOCATION
    assert device.model == "Davis Vantage Pro 2 (Plus)"
    assert device.sw_version == "AWEKAS Bridge Direct Link"
    assert device.serial_number == STATION_ID
    assert device.configuration_url == "https://stationsweb.awekas.at/index.php?id=5"


async def test_station_api_unavailable(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the integration works without the station data."""
    mock_awekas_client.async_get_station.side_effect = AwekasConnectionError(
        "TimeoutError"
    )
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.entry_id)}
    )
    assert device.name == mock_config_entry.title
    temperature = get_entity_id(hass, mock_config_entry, "sensor", "temperature")
    assert hass.states.get(temperature).state == "14.5"


async def test_station_data_fetched_daily(
    hass: HomeAssistant,
    mock_awekas_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the station data is only fetched once a day."""
    await setup_integration(hass, mock_config_entry)
    assert mock_awekas_client.async_get_station.call_count == 1

    for _ in range(3):
        freezer.tick(UPDATE_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert mock_awekas_client.async_get_current.call_count == 4
    assert mock_awekas_client.async_get_station.call_count == 1

    freezer.tick(STATION_UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_awekas_client.async_get_station.call_count == 2


async def test_migrate_removes_language(
    hass: HomeAssistant, mock_awekas_client: AsyncMock
) -> None:
    """Test the language of the forecast texts is removed from the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=STATION_ID,
        data={CONF_API_KEY: API_KEY, CONF_LANGUAGE: "en"},
        version=1,
        minor_version=2,
    )
    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 3
    assert entry.data == {CONF_API_KEY: API_KEY}


async def test_downgrade_from_future_version(
    hass: HomeAssistant, mock_awekas_client: AsyncMock
) -> None:
    """Test an entry of a newer major version is not loaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=STATION_ID,
        data={CONF_API_KEY: API_KEY},
        version=2,
    )
    await setup_integration(hass, entry)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
