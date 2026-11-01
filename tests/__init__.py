"""Tests for the AWEKAS Weather integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.awekas_weather.const import DOMAIN


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration with the given config entry."""
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def get_entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str | None
) -> str:
    """Return the entity ID of the entity with the given description key."""
    unique_id = entry.entry_id if key is None else f"{entry.entry_id}_{key}"
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id
