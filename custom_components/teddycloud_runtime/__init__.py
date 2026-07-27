"""TeddyCloud Runtime integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TeddyCloudClient
from .const import (
    CONF_RULES,
    DOMAIN,
    PLATFORMS,
    SERVICE_CLEAR_CACHE,
    SERVICE_MARK_COMPLETE,
    SERVICE_RESET_PROGRESS,
    SERVICE_RETRY_ASSIGNMENT,
    SERVICE_REFRESH_RUNTIME,
    SERVICE_RELOAD_LIBRARY,
)
from .coordinator import TeddyCloudRuntimeCoordinator
from .playback import PlaybackManager
from .rules import migrate_rules, stored_rules

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional("audio_id"): cv.string,
        vol.Optional("ruid"): cv.string,
    }
)
SERVICE_BOX_SCHEMA = vol.Schema({vol.Required("box_id"): cv.string})


async def async_migrate_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Migrate legacy Custom-Tonie rules without losing configuration."""
    if entry.version < 2:
        options = dict(entry.options)
        rules = migrate_rules(stored_rules(entry))
        if rules:
            options[CONF_RULES] = rules
        hass.config_entries.async_update_entry(
            entry,
            options=options,
            version=2,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TeddyCloud Runtime from a config entry."""
    client = TeddyCloudClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
    )
    coordinator = TeddyCloudRuntimeCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    playback = PlaybackManager(hass, entry, coordinator)
    coordinator.playback = playback
    await playback.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a TeddyCloud Runtime config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.data[DOMAIN][entry.entry_id].playback.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_RELOAD_LIBRARY,
                SERVICE_REFRESH_RUNTIME,
                SERVICE_CLEAR_CACHE,
                SERVICE_MARK_COMPLETE,
                SERVICE_RESET_PROGRESS,
                SERVICE_RETRY_ASSIGNMENT,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


def _coordinator(hass: HomeAssistant) -> TeddyCloudRuntimeCoordinator:
    """Return the coordinator for this single-entry integration."""
    return next(iter(hass.data[DOMAIN].values()))


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_RELOAD_LIBRARY):
        return

    async def reload_library(call: ServiceCall) -> None:
        await _coordinator(hass).async_request_refresh()

    async def refresh_runtime(call: ServiceCall) -> None:
        await _coordinator(hass).async_refresh_runtime(
            call.data.get("audio_id") or call.data.get("ruid")
        )

    async def clear_cache(call: ServiceCall) -> None:
        await _coordinator(hass).async_clear_cache()

    async def mark_complete(call: ServiceCall) -> None:
        await _coordinator(hass).playback.async_mark_complete(call.data["box_id"])

    async def reset_progress(call: ServiceCall) -> None:
        await _coordinator(hass).playback.async_reset_progress(call.data["box_id"])

    async def retry_assignment(call: ServiceCall) -> None:
        await _coordinator(hass).playback.async_retry_assignments()

    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD_LIBRARY, reload_library, schema=vol.Schema({})
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_RUNTIME,
        refresh_runtime,
        schema=SERVICE_REFRESH_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_CACHE, clear_cache, schema=vol.Schema({})
    )
    hass.services.async_register(
        DOMAIN, SERVICE_MARK_COMPLETE, mark_complete, schema=SERVICE_BOX_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_PROGRESS, reset_progress, schema=SERVICE_BOX_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RETRY_ASSIGNMENT,
        retry_assignment,
        schema=vol.Schema({}),
    )
