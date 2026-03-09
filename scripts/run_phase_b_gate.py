"""Run a minimal Phase B gate check against the local memory kernel."""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mind.cli import phase_b_gate_main


def main() -> int:
    return phase_b_gate_main()


if __name__ == "__main__":
    raise SystemExit(main())
