"""Run the Phase D retrieval/workspace smoke baseline."""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mind.cli import workspace_smoke_main


def main() -> int:
    return workspace_smoke_main()


if __name__ == "__main__":
    raise SystemExit(main())
