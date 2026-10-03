"""Sidebar Sites: show any website as a Home Assistant sidebar page."""
from __future__ import annotations

import logging
import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create one sidebar page for every saved site."""
    await _register_static(hass)
    asset_version = await hass.async_add_executor_job(_asset_version)

    paths: list[str] = []
    for site in entry.options.get(CONF_SITES, []):
        path = site[CONF_SLUG]
        try:
            await panel_custom.async_register_panel(
                hass,
                webcomponent_name=COMPONENT_NAME,
                frontend_url_path=path,
                sidebar_title=site[CONF_NAME],
                sidebar_icon=site.get(CONF_ICON) or "mdi:web",
                module_url=f"{STATIC_URL}?v={VERSION}-{asset_version}",
                require_admin=site.get(CONF_ADMIN_ONLY, False),
                config={"site_url": site[CONF_URL], "site_name": site[CONF_NAME]},
            )
        except ValueError as err:
            _LOGGER.warning("Could not add sidebar page %s: %s", path, err)
            continue
        paths.append(path)

    hass.data[DOMAIN][entry.entry_id] = paths
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove every sidebar page this entry made."""
    for path in hass.data[DOMAIN].pop(entry.entry_id, []):
        frontend.async_remove_panel(hass, path)
    return True
