"""Config flow + options flow.

The config flow runs once during initial setup (token entry).
The options flow ("Configure" button) is the day-to-day UI for managing repos.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_FULL_NAME,
    CONF_GITHUB_TOKEN,
    CONF_INTEGRATION_NAME,
    CONF_REF,
    CONF_REF_TYPE,
    DOMAIN,
    REF_TYPE_BRANCH,
    REF_TYPE_RELEASE,
    VALID_REF_TYPES,
)
from .github import GitHubAuthError, GitHubClient, GitHubError
from .manager import get_manager

_LOGGER = logging.getLogger(__name__)

CLASSIC_PAT_URL = (
    "https://github.com/settings/tokens/new?scopes=repo&description=Private+HACS"
)
FINE_GRAINED_PAT_URL = "https://github.com/settings/personal-access-tokens/new"
TOKEN_PLACEHOLDERS = {
    "classic_url": CLASSIC_PAT_URL,
    "fine_url": FINE_GRAINED_PAT_URL,
}


class PrivateHacsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: collect a GitHub PAT."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            token = user_input[CONF_GITHUB_TOKEN].strip()
            session = async_get_clientsession(self.hass)
            client = GitHubClient(session, token)
            try:
                user = await client.verify_token()
            except GitHubAuthError:
                errors["base"] = "invalid_auth"
            except GitHubError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Private HACS ({user.get('login', 'github')})",
                    data={CONF_GITHUB_TOKEN: token},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_GITHUB_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=TOKEN_PLACEHOLDERS,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_GITHUB_TOKEN].strip()
            session = async_get_clientsession(self.hass)
            client = GitHubClient(session, token)
            try:
                await client.verify_token()
            except GitHubAuthError:
                errors["base"] = "invalid_auth"
            except GitHubError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_GITHUB_TOKEN: token}
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_GITHUB_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders=TOKEN_PLACEHOLDERS,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return PrivateHacsOptionsFlow()


class PrivateHacsOptionsFlow(OptionsFlow):
    """Configure-button UI: add/remove/install/update repos, change token."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_repository",
                "manage_repository",
                "update_token",
            ],
        )

    # --- Add ----------------------------------------------------------------

    async def async_step_add_repository(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            manager = get_manager(self.hass)
            try:
                repo = await manager.add_repository(
                    full_name_or_url=user_input[CONF_FULL_NAME],
                    ref_type=user_input[CONF_REF_TYPE],
                    ref=(user_input.get(CONF_REF) or None),
                    integration_name=(
                        user_input.get(CONF_INTEGRATION_NAME) or None
                    ),
                )
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "add_repository failed for %r: %s",
                    user_input.get(CONF_FULL_NAME),
                    err,
                )
                errors["base"] = "add_failed"
                self._error_detail = str(err)
            else:
                if user_input.get("install_now", True):
                    try:
                        await manager.install_or_update(repo.full_name)
                    except HomeAssistantError as err:
                        _LOGGER.warning(
                            "install_or_update failed for %s: %s",
                            repo.full_name,
                            err,
                        )
                        errors["base"] = "install_failed"
                        self._error_detail = str(err)
                    else:
                        self._installed_repo_name = repo.full_name
                        return await self.async_step_installed_confirmation()
                if not errors:
                    # install_now was unchecked — repo registered, no install
                    return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_FULL_NAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Required(
                    CONF_REF_TYPE, default=REF_TYPE_BRANCH
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=v, label=v)
                            for v in VALID_REF_TYPES
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_REF, default="main"): str,
                vol.Optional(CONF_INTEGRATION_NAME, default=""): str,
                vol.Optional("install_now", default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="add_repository",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "detail": getattr(self, "_error_detail", "")
            },
        )

    # --- Manage existing ----------------------------------------------------

    async def async_step_manage_repository(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        manager = get_manager(self.hass)
        repos = manager.store.all()

        if not repos:
            return self.async_abort(reason="no_repositories")

        if user_input is not None:
            self._selected_full_name = user_input[CONF_FULL_NAME]
            return await self.async_step_repository_action()

        schema = vol.Schema(
            {
                vol.Required(CONF_FULL_NAME): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=r.full_name,
                                label=_repo_label(r),
                            )
                            for r in repos
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="manage_repository", data_schema=schema
        )

    async def async_step_repository_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        manager = get_manager(self.hass)
        full_name: str = self._selected_full_name

        if user_input is not None:
            action = user_input["action"]
            try:
                if action == "install_or_update":
                    await manager.install_or_update(full_name)
                elif action == "remove":
                    await manager.remove_repository(full_name)
            except HomeAssistantError as err:
                errors["base"] = "action_failed"
                self._error_detail = str(err)
            else:
                if action == "install_or_update":
                    self._installed_repo_name = full_name
                    return await self.async_step_installed_confirmation()
                return self.async_create_entry(title="", data={})

        repo = manager.store.get(full_name)
        title_label = _repo_label(repo) if repo else full_name
        schema = vol.Schema(
            {
                vol.Required("action", default="install_or_update"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value="install_or_update",
                                label="Install / update",
                            ),
                            SelectOptionDict(
                                value="remove",
                                label="Remove (delete files + stop tracking)",
                            ),
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="repository_action",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "repo": title_label,
                "detail": getattr(self, "_error_detail", ""),
            },
        )

    # --- Post-install confirmation -----------------------------------------

    async def async_step_installed_confirmation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        full_name: str = getattr(self, "_installed_repo_name", "")
        repo = get_manager(self.hass).store.get(full_name) if full_name else None
        return self.async_show_form(
            step_id="installed_confirmation",
            data_schema=vol.Schema({}),
            description_placeholders={
                "repo": full_name or "?",
                "integration": (repo.integration_name if repo else "?") or "?",
                "version": (
                    repo.installed_version
                    or (repo.installed_sha[:7] if repo and repo.installed_sha else "?")
                ) if repo else "?",
            },
            last_step=True,
        )

    # --- Token rotation -----------------------------------------------------

    async def async_step_update_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_GITHUB_TOKEN].strip()
            session = async_get_clientsession(self.hass)
            client = GitHubClient(session, token)
            try:
                await client.verify_token()
            except GitHubAuthError:
                errors["base"] = "invalid_auth"
            except GitHubError:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_GITHUB_TOKEN: token},
                )
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_GITHUB_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="update_token", data_schema=schema, errors=errors
        )


def _repo_label(repo) -> str:
    if not repo:
        return "?"
    parts = [repo.full_name]
    if repo.ref_type != REF_TYPE_RELEASE or repo.ref:
        parts.append(f"({repo.ref_type}{':' + repo.ref if repo.ref else ''})")
    if repo.installed_version:
        parts.append(f"@ {repo.installed_version}")
    return " ".join(parts)
