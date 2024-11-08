"""The spotify integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import aiohttp
from spotifyaio import Device, SpotifyClient, SpotifyConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .browse_media import async_browse_media
from .const import DOMAIN, LOGGER, SPOTIFY_SCOPES, SERVICE_UPDATE_DEVICES, SERVICE_SEARCH
from .coordinator import SpotifyConfigEntry, SpotifyCoordinator
from .models import SpotifyData
from .util import (
    is_spotify_media_type,
    resolve_spotify_media_type,
    spotify_uri_from_media_browser_url,
)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR]

__all__ = [
    "async_browse_media",
    "DOMAIN",
    "spotify_uri_from_media_browser_url",
    "is_spotify_media_type",
    "resolve_spotify_media_type",
]


async def async_setup_entry(hass: HomeAssistant, entry: SpotifyConfigEntry) -> bool:
    """Set up Spotify from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    session = OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
    except aiohttp.ClientError as err:
        raise ConfigEntryNotReady from err

    spotify = SpotifyClient(async_get_clientsession(hass))

    spotify.authenticate(session.token[CONF_ACCESS_TOKEN])

    async def _refresh_token() -> str:
        await session.async_ensure_token_valid()
        token = session.token[CONF_ACCESS_TOKEN]
        if TYPE_CHECKING:
            assert isinstance(token, str)
        return token

    spotify.refresh_token_function = _refresh_token

    coordinator = SpotifyCoordinator(hass, spotify)

    await coordinator.async_config_entry_first_refresh()

    async def _update_devices() -> list[Device]:
        try:
            return await spotify.get_devices()
        except SpotifyConnectionError as err:
            raise UpdateFailed from err

    device_coordinator: DataUpdateCoordinator[list[Device]] = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=f"{entry.title} Devices",
        config_entry=entry,
        update_interval=timedelta(minutes=5),
        update_method=_update_devices,
    )
    await device_coordinator.async_config_entry_first_refresh()


    async def _handle_update_devices_service(call: ServiceCall) -> None:
        await device_coordinator.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_UPDATE_DEVICES, _handle_update_devices_service)


    async def _handle_search(call: ServiceCall) -> None:
        # query = call.data.get("query")
        results = ["sonuc1", "sonuc2", "sonuc3"]
        await hass.services.async_set_results(call.id, {"results": results})

    hass.services.async_register(DOMAIN, SERVICE_SEARCH, _handle_search)


    # async def _handle_search_service(call: ServiceCall) -> dict:
    #    """Spotify'da arama yapar"""
    #    query = call.data.get("query")
    #    search_type = call.data.get("search_type", "track")
    #    results = await _spotify_search(session.token[CONF_ACCESS_TOKEN], query, search_type)
    #    return results
    
    # hass.services.async_register(DOMAIN, "search", _handle_search_service)

    # async def _spotify_search(access_token: str, query: str, search_type: str):
    #    if search_type is "artist":
    #        type_query = "artist"
    #    else:
    #        type_query = "artist,track,playlist"
    #    url = f"https://api.spotify.com/v1/search?q={query}&type={type_query}&limit=10"
    #    headers = {"Authorization": f"Bearer {access_token}"}
    #    async with aiohttp.ClientSession() as session:
    #        async with session.get(url, headers=headers) as response:
    #            return await response.json()


    entry.runtime_data = SpotifyData(coordinator, session, device_coordinator)

    if not set(session.token["scope"].split(" ")).issuperset(SPOTIFY_SCOPES):
        raise ConfigEntryAuthFailed

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Spotify config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
