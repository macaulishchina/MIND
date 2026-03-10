"""CLI wrapper for the Phase F baseline CI report."""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mind.cli import benchmark_report_main


def main() -> int:
    return benchmark_report_main()


if __name__ == "__main__":
    raise SystemExit(main())
