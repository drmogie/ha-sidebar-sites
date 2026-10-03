"""Config flow for Sidebar Sites. One entry is one sidebar page."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ADMIN_ONLY,
    CONF_ICON,
    CONF_NAME,
    CONF_SLUG,
    CONF_URL,
    DOMAIN,
)

_PROXY_RE = re.compile(r"^proxy://[A-Za-z0-9._~-]{1,64}$")


def _valid_address(url: str) -> bool:
    """A normal web address, or proxy://<site-name-with-dashes> for a site of the Sidebar Proxy add-on."""
    return url.lower().startswith(("http://", "https://")) or bool(_PROXY_RE.match(url))


def _schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Required(CONF_URL): selector.TextSelector(),
            vol.Optional(CONF_ICON, default="mdi:web"): selector.IconSelector(),
            vol.Optional(CONF_ADMIN_ONLY, default=False): selector.BooleanSelector(),
        }
    )


def _check(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Clean the form values and find mistakes."""
    errors: dict[str, str] = {}
    name = user_input[CONF_NAME].strip()
    url = user_input[CONF_URL].strip()
    if not name or not slugify(name):
        errors[CONF_NAME] = "invalid_name"
    if not _valid_address(url):
        errors[CONF_URL] = "invalid_url"
    data = {
        CONF_NAME: name,
        CONF_URL: url,
        CONF_ICON: user_input.get(CONF_ICON) or "mdi:web",
        CONF_ADMIN_ONLY: user_input.get(CONF_ADMIN_ONLY, False),
    }
    return data, errors


class SidebarSitesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one site. Every site is its own entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _check(user_input)
            if not errors:
                slug = "site-" + slugify(data[CONF_NAME], separator="-")
                if any(e.unique_id == slug for e in self._async_current_entries()):
                    errors[CONF_NAME] = "duplicate_name"
                else:
                    data[CONF_SLUG] = slug
                    await self.async_set_unique_id(slug)
                    return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input),
            errors=errors,
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Used to move sites out of the old single entry."""
        slug = user_input[CONF_SLUG]
        await self.async_set_unique_id(slug)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user_input[CONF_NAME], data=dict(user_input))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return SidebarSitesOptionsFlow()


class SidebarSitesOptionsFlow(OptionsFlow):
    """Change this site. The sidebar address stays the same."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _check(user_input)
            if not errors:
                return self.async_create_entry(data=data)
        suggested = user_input or {
            CONF_NAME: current[CONF_NAME],
            CONF_URL: current[CONF_URL],
            CONF_ICON: current.get(CONF_ICON, "mdi:web"),
            CONF_ADMIN_ONLY: current.get(CONF_ADMIN_ONLY, False),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_schema(), suggested),
            errors=errors,
        )
