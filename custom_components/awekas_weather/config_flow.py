"""Config flow for the AWEKAS Weather integration."""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import (
    AwekasAuthError,
    AwekasClient,
    AwekasConnectionError,
    AwekasError,
    AwekasPlusNotActiveError,
    AwekasQuotaError,
)
from .const import DEFAULT_TITLE, DOMAIN

_LOGGER = logging.getLogger(__name__)

API_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): API_KEY_SELECTOR})

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): API_KEY_SELECTOR})


class AwekasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AWEKAS Weather."""

    VERSION = 1
    MINOR_VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match({CONF_API_KEY: user_input[CONF_API_KEY]})

            errors, station = await self._async_validate_input(user_input)
            if station is not None:
                await self.async_set_unique_id(str(station["id"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=station.get("location") or DEFAULT_TITLE, data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start the re-authentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for a new API key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            errors, station = await self._async_validate_input(
                {**reauth_entry.data, **user_input}
            )
            if station is not None:
                unique_id = str(station["id"])
                # Entries created before the station API was used are
                # identified by their API key
                identified_by_key = (
                    reauth_entry.unique_id == reauth_entry.data[CONF_API_KEY]
                )
                if not identified_by_key and reauth_entry.unique_id != unique_id:
                    return self.async_abort(reason="wrong_station")
                if any(
                    entry.unique_id == unique_id
                    and entry.entry_id != reauth_entry.entry_id
                    for entry in self._async_current_entries(include_ignore=False)
                ):
                    return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(
                    reauth_entry, unique_id=unique_id, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )

    async def _async_validate_input(
        self, data: Mapping[str, Any]
    ) -> tuple[dict[str, str], dict[str, Any] | None]:
        """Test the API key and return the form errors and the station data."""
        client = AwekasClient(
            async_get_clientsession(self.hass),
            data[CONF_API_KEY],
        )
        try:
            await client.async_get_current()
            station = (await client.async_get_station()).get("station") or {}
        except AwekasAuthError:
            return {"base": "invalid_auth"}, None
        except AwekasPlusNotActiveError:
            return {"base": "awekas_plus_not_active"}, None
        except AwekasQuotaError:
            return {"base": "quota_exceeded"}, None
        except AwekasConnectionError:
            return {"base": "cannot_connect"}, None
        except AwekasError as err:
            _LOGGER.warning("AWEKAS API reported an error: %s", err)
            return {"base": "cannot_connect"}, None
        except Exception:
            _LOGGER.exception("Unexpected error while validating the API key")
            return {"base": "unknown"}, None

        if "id" not in station:
            _LOGGER.warning("The AWEKAS station API returned no station ID")
            return {"base": "cannot_connect"}, None
        return {}, station
