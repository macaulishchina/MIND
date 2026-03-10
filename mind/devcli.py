"""Development CLI re-export module.

Provides ``mindtest_main`` as the canonical dev-CLI entry point.
The actual CLI logic lives in :mod:`mind.cli` unchanged.
"""

from __future__ import annotations

from mind.cli import mind_main

mindtest_main = mind_main

__all__ = ["mindtest_main"]
