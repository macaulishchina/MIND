from __future__ import annotations

import time


def test_timing_probe_fast_case() -> None:
    assert True


def test_timing_probe_slow_case() -> None:
    time.sleep(0.02)
    assert True
