"""GitHub API client for Private HACS."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import GITHUB_API_BASE, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class GitHubError(Exception):
    """Raised on any GitHub API failure."""


class GitHubAuthError(GitHubError):
    """Raised on 401/403 from GitHub."""


class GitHubNotFoundError(GitHubError):
    """Raised on 404 from GitHub."""


class GitHubClient:
    """Thin authenticated wrapper around the GitHub REST API."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }

    async def _get_json(self, url: str) -> Any:
        async with self._session.get(url, headers=self._headers) as resp:
            if resp.status in (401, 403):
                raise GitHubAuthError(
                    f"Auth failed ({resp.status}) for {url}"
                )
            if resp.status == 404:
                raise GitHubNotFoundError(f"Not found: {url}")
            if resp.status >= 400:
                raise GitHubError(f"GitHub error {resp.status} for {url}")
            return await resp.json()

    async def verify_token(self) -> dict[str, Any]:
        """Confirm the token works and return /user payload."""
        return await self._get_json(f"{GITHUB_API_BASE}/user")

    async def get_repo(self, full_name: str) -> dict[str, Any]:
        return await self._get_json(f"{GITHUB_API_BASE}/repos/{full_name}")

    async def get_latest_release(self, full_name: str) -> dict[str, Any] | None:
        try:
            return await self._get_json(
                f"{GITHUB_API_BASE}/repos/{full_name}/releases/latest"
            )
        except GitHubNotFoundError:
            return None

    async def get_tag_commit(self, full_name: str, tag: str) -> str | None:
        tags = await self._get_json(f"{GITHUB_API_BASE}/repos/{full_name}/tags")
        for t in tags:
            if t.get("name") == tag:
                return t.get("commit", {}).get("sha")
        return None

    async def get_branch_commit(self, full_name: str, branch: str) -> str | None:
        try:
            data = await self._get_json(
                f"{GITHUB_API_BASE}/repos/{full_name}/branches/{branch}"
            )
        except GitHubNotFoundError:
            return None
        return data.get("commit", {}).get("sha")

    async def download_tarball(self, full_name: str, ref: str) -> bytes:
        """Download a gzipped tarball for the given ref."""
        url = f"{GITHUB_API_BASE}/repos/{full_name}/tarball/{ref}"
        async with self._session.get(
            url, headers=self._headers, allow_redirects=True
        ) as resp:
            if resp.status in (401, 403):
                raise GitHubAuthError(f"Auth failed downloading {url}")
            if resp.status == 404:
                raise GitHubNotFoundError(f"Tarball not found: {url}")
            if resp.status >= 400:
                raise GitHubError(f"Tarball download failed: HTTP {resp.status}")
            return await resp.read()
