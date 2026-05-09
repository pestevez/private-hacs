"""Persistent storage for tracked repositories."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .repository import Repository


class RepositoryStore:
    """Wraps HA's Store with a list[Repository] view."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._repos: dict[str, Repository] = {}
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        data: dict[str, Any] | None = await self._store.async_load()
        repos: list[dict] = (data or {}).get("repositories", [])
        self._repos = {}
        for raw in repos:
            try:
                repo = Repository.from_dict(raw)
            except TypeError:
                continue
            self._repos[repo.key] = repo
        self._loaded = True

    async def async_save(self) -> None:
        await self._store.async_save(
            {"repositories": [r.to_dict() for r in self._repos.values()]}
        )

    def all(self) -> list[Repository]:
        return list(self._repos.values())

    def get(self, full_name: str) -> Repository | None:
        return self._repos.get(full_name.lower())

    def upsert(self, repo: Repository) -> None:
        self._repos[repo.key] = repo

    def remove(self, full_name: str) -> bool:
        return self._repos.pop(full_name.lower(), None) is not None
