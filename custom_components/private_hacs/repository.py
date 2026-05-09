"""Repository data model."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .const import REF_TYPE_RELEASE


@dataclass
class Repository:
    """A tracked GitHub repository providing a custom integration."""

    full_name: str
    ref_type: str = REF_TYPE_RELEASE
    ref: str | None = None
    integration_name: str | None = None
    installed_version: str | None = None
    installed_sha: str | None = None

    @property
    def key(self) -> str:
        return self.full_name.lower()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Repository":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})
