"""Repository management — shared by services and the OptionsFlow."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    REF_TYPE_BRANCH,
    REF_TYPE_COMMIT,
    REF_TYPE_RELEASE,
    REF_TYPE_TAG,
)
from .github import GitHubClient, GitHubError, GitHubNotFoundError
from .installer import (
    InstallerError,
    install_from_tarball,
    remove_integration,
)
from .repository import Repository
from .store import RepositoryStore

_LOGGER = logging.getLogger(__name__)

# Matches "owner/repo", "github.com/owner/repo", "https://github.com/owner/repo[.git]",
# "git@github.com:owner/repo[.git]". Trailing slashes / .git tolerated.
_REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:github\.com[:/])?"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)"
    r"/"
    r"(?P<repo>[A-Za-z0-9._-]+?)"
    r"(?:\.git)?/?$"
)


class PrivateHacsManager:
    """Operations on the repository registry + custom_components/ directory."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GitHubClient,
        store: RepositoryStore,
    ) -> None:
        self.hass = hass
        self.client = client
        self.store = store

    @property
    def _custom_components_dir(self) -> Path:
        return Path(self.hass.config.path("custom_components"))

    @staticmethod
    def parse_repo_input(value: str) -> str:
        """Normalize user-supplied repo references to 'owner/repo'."""
        cleaned = value.strip()
        match = _REPO_URL_RE.match(cleaned)
        if not match:
            raise HomeAssistantError(
                f"Could not parse repository reference: {value!r}"
            )
        return f"{match.group('owner')}/{match.group('repo')}"

    async def add_repository(
        self,
        full_name_or_url: str,
        ref_type: str = REF_TYPE_BRANCH,
        ref: str | None = "main",
        integration_name: str | None = None,
    ) -> Repository:
        full_name = self.parse_repo_input(full_name_or_url)

        if ref_type in (REF_TYPE_TAG, REF_TYPE_BRANCH, REF_TYPE_COMMIT) and not ref:
            raise HomeAssistantError(
                f"A ref is required when ref_type is '{ref_type}'"
            )

        if self.store.get(full_name):
            raise HomeAssistantError(f"{full_name} is already tracked")

        try:
            await self.client.get_repo(full_name)
        except GitHubNotFoundError as err:
            raise HomeAssistantError(
                f"Cannot access {full_name} on GitHub: repository not found "
                "or your token has no access to it. If you're using a "
                "fine-grained PAT, make sure this repository is in its "
                "'Repository access' list."
            ) from err
        except GitHubError as err:
            raise HomeAssistantError(
                f"Cannot access {full_name} on GitHub: {err}"
            ) from err

        repo = Repository(
            full_name=full_name,
            ref_type=ref_type,
            ref=ref,
            integration_name=integration_name,
        )
        self.store.upsert(repo)
        await self.store.async_save()
        return repo

    async def remove_repository(
        self, full_name_or_url: str, *, delete_files: bool = True
    ) -> None:
        full_name = self.parse_repo_input(full_name_or_url)
        repo = self.store.get(full_name)
        if not repo:
            raise HomeAssistantError(f"{full_name} is not tracked")

        if delete_files and repo.integration_name:
            try:
                await self.hass.async_add_executor_job(
                    remove_integration,
                    self._custom_components_dir,
                    repo.integration_name,
                )
            except InstallerError as err:
                _LOGGER.warning("Could not delete integration files: %s", err)

        self.store.remove(full_name)
        await self.store.async_save()

    async def install_or_update(self, full_name_or_url: str) -> Repository:
        full_name = self.parse_repo_input(full_name_or_url)
        repo = self.store.get(full_name)
        if not repo:
            raise HomeAssistantError(f"{full_name} is not tracked")

        ref = await self._resolve_ref(repo)
        if not ref:
            raise HomeAssistantError(
                f"Could not resolve ref for {full_name} "
                f"({repo.ref_type}={repo.ref!r})"
            )

        try:
            tarball = await self.client.download_tarball(repo.full_name, ref)
        except GitHubError as err:
            raise HomeAssistantError(f"Download failed: {err}") from err

        dest_root = self._custom_components_dir
        await self.hass.async_add_executor_job(_ensure_dir, dest_root)

        try:
            integration_name, _ = await self.hass.async_add_executor_job(
                install_from_tarball,
                tarball,
                dest_root,
                repo.integration_name,
            )
        except InstallerError as err:
            raise HomeAssistantError(f"Install failed: {err}") from err

        repo.integration_name = integration_name
        repo.installed_sha = await self._commit_for_ref(repo, ref)
        repo.installed_version = (
            ref if repo.ref_type != REF_TYPE_COMMIT else ref[:7]
        )
        self.store.upsert(repo)
        await self.store.async_save()

        _LOGGER.info(
            "Installed %s into custom_components/%s — restart HA to load",
            full_name,
            integration_name,
        )

        version_label = repo.installed_version or (
            repo.installed_sha[:7] if repo.installed_sha else "?"
        )
        persistent_notification.async_create(
            self.hass,
            (
                f"**{repo.full_name}** has been installed as "
                f"`custom_components/{integration_name}/` "
                f"(version: `{version_label}`).\n\n"
                "**Restart Home Assistant** to load the new integration. "
                "Until you restart, the files are on disk but not yet active."
            ),
            title=f"Private HACS: {integration_name} ready",
            notification_id=f"{DOMAIN}_pending_restart_{integration_name}",
        )

        return repo

    async def _resolve_ref(self, repo: Repository) -> str | None:
        if repo.ref_type == REF_TYPE_RELEASE:
            release = await self.client.get_latest_release(repo.full_name)
            return release.get("tag_name") if release else None
        if repo.ref_type in (REF_TYPE_TAG, REF_TYPE_BRANCH, REF_TYPE_COMMIT):
            return repo.ref
        return None

    async def _commit_for_ref(self, repo: Repository, ref: str) -> str | None:
        if repo.ref_type == REF_TYPE_BRANCH:
            return await self.client.get_branch_commit(repo.full_name, ref)
        if repo.ref_type in (REF_TYPE_RELEASE, REF_TYPE_TAG):
            return await self.client.get_tag_commit(repo.full_name, ref)
        if repo.ref_type == REF_TYPE_COMMIT:
            return ref
        return None


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_manager(hass: HomeAssistant) -> PrivateHacsManager:
    """Return the manager for the (single) configured Private HACS entry."""
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        raise HomeAssistantError("Private HACS is not configured")
    return next(iter(domain_data.values()))["manager"]
