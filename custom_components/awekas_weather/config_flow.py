"""Config flow for the AWEKAS Weather integration."""

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_LANGUAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN, LANGUAGES

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_LANGUAGE, default="de"): SelectSelector(
            SelectSelectorConfig(
                options=LANGUAGES,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="language",
            )
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validiert den API-Key durch einen Test-Aufruf an die AWEKAS API."""

    session = async_get_clientsession(hass)

    api_key = data[CONF_API_KEY]
    lang = data.get(CONF_LANGUAGE, "de")
    url = f"https://api.awekas.at/current.php?key={api_key}&lng={lang}"

    try:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                raise CannotConnect

            res_data = await response.json()

            # 1. 'error'-Key sicher abrufen. Wenn nicht vorhanden oder None/0/False/"" -> error_val ist None/Falsy
            error_val = res_data.get("error")

            # 2. Nur wenn 'error' tatsächlich Inhalt hat (also nicht None, False oder leer ist)
            if error_val:
                error_str = str(error_val).lower().strip()

                # Falls der Wert doch mal aus Versehen als String 'none' oder 'null' geliefert wird
                if error_str not in ("none", "null", ""):
                    _LOGGER.warning("AWEKAS API meldet Fehler: %s", error_val)

                    # Prüfung auf ungültigen Key
                    if "invalid" in error_str or "key" in error_str:
                        raise InvalidAuth

                    raise CannotConnect

    except aiohttp.ClientError as err:
        # Fängt Netzwerkfehler (DNS, Offline, Timeout) ab
        raise CannotConnect from err

    # Titel aus den ersten 5 Zeichen des API-Keys generieren
    api_prefix = api_key[:5]
    return {"title": f"AWEKAS ({api_prefix})"}


class AwekasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AWEKAS Weather."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Erster Schritt bei der manuellen Einrichtung durch den Nutzer."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_API_KEY])
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unerwarteter Fehler bei der Validierung")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Startet den Re-Auth-Flow."""
        return await self.async_step_reauth_confirm(entry_data)

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Behandelt die erneute Eingabe des API-Keys bei Re-Authentifizierung."""
        errors = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                # Kombiniere alte Daten mit neuem API-Key
                test_data = {**reauth_entry.data, **user_input}
                await validate_input(self.hass, test_data)

                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data=test_data,
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unerwarteter Fehler bei Re-Auth")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
