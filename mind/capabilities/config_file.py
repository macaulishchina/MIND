"""Load user configuration from ``mind.toml``.

The file is optional. When present it provides defaults that sit between
CLI arguments (highest priority) and environment variables::

    CLI flags  >  mind.toml  >  env vars  >  code defaults

Only the ``[provider]`` and ``[evaluation]`` sections are read.
Unknown keys are silently ignored so the file stays forward-compatible.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

_SEARCH_MARKERS: tuple[str, ...] = ("pyproject.toml", ".git")


def load_mind_toml(
    search_from: str | Path | None = None,
) -> dict[str, Any]:
    """Locate and parse ``mind.toml``, returning the raw dict.

    Walks upward from *search_from* (default: cwd) until a directory that
    contains a repository marker (``pyproject.toml`` or ``.git``) is found,
    then looks for ``mind.toml`` in that directory.

    Returns an empty dict when the file does not exist or cannot be parsed.
    """

    root = _find_repo_root(search_from)
    if root is None:
        return {}
    config_path = root / "mind.toml"
    if not config_path.is_file():
        return {}
    try:
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — never crash on bad config
        return {}


def get_provider_config(toml: dict[str, Any]) -> dict[str, Any]:
    """Return the ``[provider]`` section as a flat dict (may be empty)."""
    section = toml.get("provider")
    if isinstance(section, dict):
        return dict(section)
    return {}


def get_evaluation_config(toml: dict[str, Any]) -> dict[str, Any]:
    """Return the ``[evaluation]`` section as a flat dict (may be empty)."""
    section = toml.get("evaluation")
    if isinstance(section, dict):
        return dict(section)
    return {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_repo_root(search_from: str | Path | None) -> Path | None:
    current = Path(search_from).resolve() if search_from else Path.cwd()
    for directory in (current, *current.parents):
        if any((directory / marker).exists() for marker in _SEARCH_MARKERS):
            return directory
    return None
