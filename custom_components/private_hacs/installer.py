"""Tarball extraction into HA's custom_components/ folder."""
from __future__ import annotations

import io
import logging
import shutil
import tarfile
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class InstallerError(Exception):
    """Raised on extraction problems."""


def _is_within(base: Path, target: Path) -> bool:
    """Reject paths that escape `base` after resolution."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def list_integrations(tarball_bytes: bytes) -> list[str]:
    """Return integration directory names found under custom_components/."""
    with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tf:
        members = tf.getmembers()
        top_dirs = {m.name.split("/", 1)[0] for m in members if m.name}
        if len(top_dirs) != 1:
            raise InstallerError("Unexpected tarball structure")
        (top,) = top_dirs

        cc_prefix = f"{top}/custom_components/"
        names: set[str] = set()
        for m in members:
            if not m.name.startswith(cc_prefix):
                continue
            rel = m.name[len(cc_prefix):]
            if not rel:
                continue
            first = rel.split("/", 1)[0]
            if first:
                names.add(first)
        return sorted(names)


def install_from_tarball(
    tarball_bytes: bytes,
    dest_root: Path,
    integration_name: str | None,
) -> tuple[str, Path]:
    """Extract `custom_components/<integration_name>/` into dest_root.

    If integration_name is None, the repo must contain exactly one integration.

    Returns (integration_name, dest_path).
    """
    with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tf:
        members = tf.getmembers()
        top_dirs = {m.name.split("/", 1)[0] for m in members if m.name}
        if len(top_dirs) != 1:
            raise InstallerError("Unexpected tarball structure")
        (top,) = top_dirs

        cc_prefix = f"{top}/custom_components/"
        cc_members = [m for m in members if m.name.startswith(cc_prefix)]
        if not cc_members:
            raise InstallerError(
                "Repo has no custom_components/ folder"
            )

        names: set[str] = set()
        for m in cc_members:
            rel = m.name[len(cc_prefix):]
            if not rel:
                continue
            first = rel.split("/", 1)[0]
            if first:
                names.add(first)

        if integration_name and integration_name not in names:
            raise InstallerError(
                f"Integration '{integration_name}' not found in repo "
                f"(found: {sorted(names)})"
            )

        if not integration_name:
            if len(names) != 1:
                raise InstallerError(
                    f"Repo has {len(names)} integrations: {sorted(names)}; "
                    "specify integration_name"
                )
            integration_name = next(iter(names))

        target_prefix = f"{cc_prefix}{integration_name}/"
        dest_path = dest_root / integration_name

        if not _is_within(dest_root, dest_path):
            raise InstallerError("Refusing to install outside dest_root")

        if dest_path.exists():
            shutil.rmtree(dest_path)
        dest_path.mkdir(parents=True)

        for m in members:
            if not m.name.startswith(target_prefix):
                continue
            rel = m.name[len(target_prefix):]
            if not rel:
                continue
            out = dest_path / rel
            if not _is_within(dest_path, out):
                raise InstallerError(f"Path traversal blocked: {m.name}")
            if m.isdir():
                out.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                out.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    continue
                with open(out, "wb") as w:
                    w.write(src.read())
            elif m.issym() or m.islnk():
                # Skip symlinks for safety.
                continue

        return integration_name, dest_path


def remove_integration(dest_root: Path, integration_name: str) -> bool:
    target = dest_root / integration_name
    if not _is_within(dest_root, target):
        raise InstallerError("Refusing to remove outside dest_root")
    if target.exists():
        shutil.rmtree(target)
        return True
    return False
