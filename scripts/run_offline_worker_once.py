"""CLI wrapper for a single Phase E offline worker batch."""

from __future__ import annotations

import sys

from mind.cli import offline_worker_main

if __name__ == "__main__":
    raise SystemExit(offline_worker_main(sys.argv[1:]))
