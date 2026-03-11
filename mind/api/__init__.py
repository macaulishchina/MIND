"""REST API exports.

Keep server-only dependencies lazy so runtime images without the `api` extra can
still import ``mind.api.client`` and the product CLI.
"""

from __future__ import annotations

from typing import Any

from mind.api.client import MindAPIClient

__all__ = ["MindAPIClient", "create_app", "run_server"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from mind.api.app import create_app

        return create_app
    if name == "run_server":
        from mind.api.app import run_server

        return run_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
