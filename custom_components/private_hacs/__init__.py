"""Private HACS — install custom integrations from private GitHub repos."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_FULL_NAME,
    CONF_GITHUB_TOKEN,
    CONF_INTEGRATION_NAME,
    CONF_REF,
    CONF_REF_TYPE,
    DOMAIN,
    REF_TYPE_BRANCH,
    SERVICE_ADD_REPOSITORY,
    SERVICE_INSTALL,
    SERVICE_REMOVE_REPOSITORY,
    SERVICE_UPDATE,
    VALID_REF_TYPES,
)
from .github import GitHubAuthError, GitHubClient, GitHubError
from .manager import PrivateHacsManager, get_manager
from .store import RepositoryStore

_LOGGER = logging.getLogger(__name__)

ADD_REPO_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FULL_NAME): cv.string,
        vol.Optional(CONF_REF_TYPE, default=REF_TYPE_BRANCH): vol.In(
            VALID_REF_TYPES
        ),
        vol.Optional(CONF_REF, default="main"): cv.string,
        vol.Optional(CONF_INTEGRATION_NAME): cv.string,
    }
)

REMOVE_REPO_SCHEMA = vol.Schema({vol.Required(CONF_FULL_NAME): cv.string})

INSTALL_SCHEMA = vol.Schema({vol.Required(CONF_FULL_NAME): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Private HACS from a config entry."""
    token: str = entry.data[CONF_GITHUB_TOKEN]
    session = async_get_clientsession(hass)
    client = GitHubClient(session, token)

    try:
        await client.verify_token()
    except GitHubAuthError as err:
        raise ConfigEntryAuthFailed("GitHub token rejected") from err
    except GitHubError as err:
        _LOGGER.warning("GitHub API unavailable at startup: %s", err)

    store = RepositoryStore(hass)
    await store.async_load()

    manager = PrivateHacsManager(hass, client, store)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "store": store,
        "manager": manager,
    }

    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        for svc in (
            SERVICE_ADD_REPOSITORY,
            SERVICE_REMOVE_REPOSITORY,
            SERVICE_INSTALL,
            SERVICE_UPDATE,
        ):
            if hass.services.has_service(DOMAIN, svc):
                hass.services.async_remove(DOMAIN, svc)
    return True


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ADD_REPOSITORY):
        return

    async def add_repository(call: ServiceCall) -> None:
        await get_manager(hass).add_repository(
            full_name_or_url=call.data[CONF_FULL_NAME],
            ref_type=call.data.get(CONF_REF_TYPE, REF_TYPE_BRANCH),
            ref=call.data.get(CONF_REF, "main"),
            integration_name=call.data.get(CONF_INTEGRATION_NAME),
        )

    async def remove_repository(call: ServiceCall) -> None:
        await get_manager(hass).remove_repository(call.data[CONF_FULL_NAME])

    async def install_or_update(call: ServiceCall) -> None:
        await get_manager(hass).install_or_update(call.data[CONF_FULL_NAME])

    hass.services.async_register(
        DOMAIN, SERVICE_ADD_REPOSITORY, add_repository, schema=ADD_REPO_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_REPOSITORY,
        remove_repository,
        schema=REMOVE_REPO_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_INSTALL, install_or_update, schema=INSTALL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE, install_or_update, schema=INSTALL_SCHEMA
    )
