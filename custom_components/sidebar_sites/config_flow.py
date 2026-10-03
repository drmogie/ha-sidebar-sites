"""Config flow for Sidebar Sites."""
from __future__ import annotations

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
    CONF_SITES,
    CONF_SLUG,
    CONF_URL,
    DOMAIN,
)


class SidebarSitesConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry holds all the sites."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Sidebar Sites", data={}, options={CONF_SITES: []}
            )
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return SidebarSitesOptionsFlow()


class SidebarSitesOptionsFlow(OptionsFlow):
    """Add, change and remove sites."""

    _edit_slug: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        menu = ["add_site"]
        if self.config_entry.options.get(CONF_SITES):
            menu.extend(["edit_site", "remove_site"])
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_site(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        sites = list(self.config_entry.options.get(CONF_SITES, []))

        if user_input is not None:
            url = user_input[CONF_URL].strip()
            name = user_input[CONF_NAME].strip()
            slug = "site-" + slugify(name, separator="-")
            if not url.lower().startswith(("http://", "https://")):
                errors[CONF_URL] = "invalid_url"
            elif not name or slug == "site-":
                errors[CONF_NAME] = "invalid_name"
            elif any(s[CONF_SLUG] == slug for s in sites):
                errors[CONF_NAME] = "duplicate_name"
            else:
                sites.append(
                    {
                        CONF_NAME: name,
                        CONF_URL: url,
                        CONF_ICON: user_input.get(CONF_ICON) or "mdi:web",
                        CONF_ADMIN_ONLY: user_input.get(CONF_ADMIN_ONLY, False),
                        CONF_SLUG: slug,
                    }
                )
                return self.async_create_entry(data={CONF_SITES: sites})

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_URL): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Optional(CONF_ICON, default="mdi:web"): selector.IconSelector(),
                vol.Optional(CONF_ADMIN_ONLY, default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="add_site",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_edit_site(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which site to change."""
        sites = list(self.config_entry.options.get(CONF_SITES, []))
        if user_input is not None:
            self._edit_slug = user_input["site"]
            return await self.async_step_edit_site_form()

        options = [
            selector.SelectOptionDict(value=s[CONF_SLUG], label=s[CONF_NAME])
            for s in sites
        ]
        schema = vol.Schema(
            {
                vol.Required("site"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(step_id="edit_site", data_schema=schema)

    async def async_step_edit_site_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the details of one site. The sidebar path stays the same."""
        errors: dict[str, str] = {}
        sites = list(self.config_entry.options.get(CONF_SITES, []))
        index = next(
            (i for i, s in enumerate(sites) if s[CONF_SLUG] == self._edit_slug), None
        )
        if index is None:
            return self.async_abort(reason="site_missing")
        current = sites[index]

        if user_input is not None:
            url = user_input[CONF_URL].strip()
            name = user_input[CONF_NAME].strip()
            if not url.lower().startswith(("http://", "https://")):
                errors[CONF_URL] = "invalid_url"
            elif not name:
                errors[CONF_NAME] = "invalid_name"
            elif any(
                s[CONF_NAME].lower() == name.lower() and s[CONF_SLUG] != self._edit_slug
                for s in sites
            ):
                errors[CONF_NAME] = "duplicate_name"
            else:
                sites[index] = {
                    **current,
                    CONF_NAME: name,
                    CONF_URL: url,
                    CONF_ICON: user_input.get(CONF_ICON) or "mdi:web",
                    CONF_ADMIN_ONLY: user_input.get(CONF_ADMIN_ONLY, False),
                }
                return self.async_create_entry(data={CONF_SITES: sites})

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_URL): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Optional(CONF_ICON): selector.IconSelector(),
                vol.Optional(CONF_ADMIN_ONLY): selector.BooleanSelector(),
            }
        )
        suggested = user_input or {
            CONF_NAME: current[CONF_NAME],
            CONF_URL: current[CONF_URL],
            CONF_ICON: current.get(CONF_ICON, "mdi:web"),
            CONF_ADMIN_ONLY: current.get(CONF_ADMIN_ONLY, False),
        }
        return self.async_show_form(
            step_id="edit_site_form",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )

    async def async_step_remove_site(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        sites = list(self.config_entry.options.get(CONF_SITES, []))
        if user_input is not None:
            drop = set(user_input["remove"])
            kept = [s for s in sites if s[CONF_SLUG] not in drop]
            return self.async_create_entry(data={CONF_SITES: kept})

        options = [
            selector.SelectOptionDict(value=s[CONF_SLUG], label=s[CONF_NAME])
            for s in sites
        ]
        schema = vol.Schema(
            {
                vol.Required("remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="remove_site", data_schema=schema)
