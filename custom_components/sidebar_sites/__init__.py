"""Sidebar Sites: show any website as a Home Assistant sidebar page.

Every sidebar page is its own entry (its own service) in the integration list.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import homeassistant.helpers.config_validation as cv
from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.typing import ConfigType

from .const import (
    COMPONENT_NAME,
    CONF_ADMIN_ONLY,
    CONF_ICON,
    CONF_NAME,
    CONF_SITES,
    CONF_SLUG,
    CONF_URL,
    DOMAIN,
    STATIC_URL,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _asset_version() -> str:
    """Short fingerprint of panel.js, so a changed file is never served from cache."""
    path = Path(__file__).parent / "frontend" / "panel.js"
    return hashlib.sha1(path.read_bytes()).hexdigest()[:10]


async def _register_static(hass: HomeAssistant) -> None:
    """Serve the panel JavaScript once."""
    if hass.data.get(DOMAIN, {}).get("static"):
        return
    path = Path(__file__).parent / "frontend" / "panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(path), False)]
    )
    hass.data.setdefault(DOMAIN, {})["static"] = True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Move an old single entry (all sites in one) into one entry per site."""
    legacy = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if CONF_SITES in {**entry.data, **entry.options}
    ]
    if legacy:
        hass.async_create_task(_migrate_legacy(hass, legacy))
    return True


async def _migrate_legacy(hass: HomeAssistant, legacy: list[ConfigEntry]) -> None:
    for entry in legacy:
        sites = {**entry.data, **entry.options}.get(CONF_SITES, [])
        for site in sites:
            await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=site
            )
        await hass.config_entries.async_remove(entry.entry_id)
        _LOGGER.info("Moved %d site(s) into their own entries", len(sites))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create the sidebar page for this one site."""
    conf = {**entry.data, **entry.options}
    if CONF_SITES in conf:
        return True  # old entry, about to be replaced by one entry per site

    await _register_static(hass)
    asset_version = await hass.async_add_executor_job(_asset_version)
    domain_data = hass.data.setdefault(DOMAIN, {})

    name = conf[CONF_NAME]
    slug = conf[CONF_SLUG]
    if entry.title != name:
        hass.config_entries.async_update_entry(entry, title=name)

    try:
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name=COMPONENT_NAME,
            frontend_url_path=slug,
            sidebar_title=name,
            sidebar_icon=conf.get(CONF_ICON) or "mdi:web",
            module_url=f"{STATIC_URL}?v={VERSION}-{asset_version}",
            require_admin=conf.get(CONF_ADMIN_ONLY, False),
            config={"site_url": conf[CONF_URL], "site_name": name},
        )
    except ValueError as err:
        _LOGGER.warning("Could not add sidebar page %s: %s", slug, err)
        return False
    domain_data[entry.entry_id] = slug

    url = conf[CONF_URL]
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, slug)},
        name=name,
        manufacturer="Sidebar Sites",
        model="Sidebar page",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=url if url.lower().startswith(("http://", "https://")) else None,
    )

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the sidebar page this entry made."""
    slug = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if slug:
        frontend.async_remove_panel(hass, slug)
    return True
